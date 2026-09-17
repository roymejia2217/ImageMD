"""Executable PR governance validator.

Standard library only. No network access. No GitHub API calls.

PR metadata always enters as data (arguments and files), never as code.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ALLOWED_TYPES = (
    "feat",
    "fix",
    "perf",
    "refactor",
    "test",
    "docs",
    "build",
    "ci",
    "chore",
)

SUBJECT_PATTERN = re.compile(
    r"(feat|fix|perf|refactor|test|docs|build|ci|chore)"
    r"(\([A-Za-z0-9][A-Za-z0-9._-]*\))?"
    r"(!)?"
    r": (.*)"
)

REQUIRED_SECTIONS = ("Summary", "Verification", "Release impact")

REQUIRED_HEADING_PATTERN = re.compile(r"##\s+(Summary|Verification|Release impact)\s*")

HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)

VERIFICATION_REQUIRED_MARKERS = (
    "`Required PR Governance`",
    "`Required CI`",
)

VOLATILE_VERIFICATION_PATTERNS = (
    re.compile(r"\b\d+\s+tests?\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+(?:passed|failed|skipped)\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+vulnerabilit(?:y|ies)\b", re.IGNORECASE),
    re.compile(r"\bworkflow\s+(?:run\s+)?#?\d+\b", re.IGNORECASE),
    re.compile(r"\b[0-9a-f]{40}\b", re.IGNORECASE),
    re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE),
)

GOVERNANCE_MAINTENANCE_HEADING = "Governance maintenance"
GOVERNANCE_MAINTENANCE_MODE = "Mode: governance-maintenance"

TRUSTED_MAINTENANCE_ASSOCIATIONS = (
    "OWNER",
    "MEMBER",
    "COLLABORATOR",
)

GOVERNANCE_MAINTENANCE_TITLE_PATTERN = re.compile(
    r"(ci|test|docs|build|chore)\(governance\)(!)?: .+"
)

MAX_SUBJECT_LENGTH = 72

PROTECTED_GOVERNANCE_PREFIXES = (
    ".github/workflows/",
    ".github/actions/",
    "ci/",
)

PROTECTED_GOVERNANCE_PATHS = (
    ".github/pull_request_template.md",
    "CONTRIBUTING.md",
    "VERSIONING.md",
    "tests/test_architecture_contract.py",
    "tests/test_pr_governance.py",
    "tests/test_pr_governance_workflow.py",
    "tests/test_quality_workflow_contract.py",
    "tests/test_pull_request_template_contract.py",
    "tests/test_version_contract.py",
)


def _is_protected_path(path: str) -> bool:
    """Return True when a repository path belongs to the governance root."""
    if path in PROTECTED_GOVERNANCE_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PROTECTED_GOVERNANCE_PREFIXES)


def _validate_repo_path(value: object) -> str | None:
    """Return an error string for an invalid repo path, else None."""
    if not isinstance(value, str):
        return f"invalid repository path: {value!r}"
    if not value:
        return "repository path must not be empty"
    if value != value.strip():
        return f"repository path must not have surrounding whitespace: {value!r}"
    if value.startswith("/"):
        return f"repository path must be relative: {value!r}"
    parts = value.split("/")
    if "" in parts:
        return f"repository path must not contain empty segments: {value!r}"
    if ".." in parts:
        return f"repository path must not contain traversal: {value!r}"
    if value.startswith("./"):
        return f"repository path must be normalized: {value!r}"
    return None


def _record_paths(record: dict) -> tuple[str, ...]:
    paths = [record["filename"]]
    previous = record.get("previous_filename")

    if isinstance(previous, str):
        paths.append(previous)

    return tuple(paths)


def _records_contain_protected_path(records: list[dict]) -> bool:
    return any(
        _is_protected_path(path) for record in records for path in _record_paths(record)
    )


def validate_governance_changes(
    records: object,
    *,
    maintenance: bool = False,
) -> list[str]:
    """Validate changed-file records; empty means no governance violation."""
    errors: list[str] = []
    if not isinstance(records, list):
        return ["changed-file records must be a list"]
    valid_records: list[dict] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"changed-file record {index + 1} must be an object")
            continue
        if "filename" not in record:
            errors.append(f"changed-file record {index + 1} is missing filename")
            continue
        filename = record["filename"]
        path_error = _validate_repo_path(filename)
        if path_error is not None:
            errors.append(f"changed-file record {index + 1}: {path_error}")
            continue
        previous = record.get("previous_filename")
        if previous is not None:
            previous_error = _validate_repo_path(previous)
            if previous_error is not None:
                errors.append(
                    f"changed-file record {index + 1} previous_filename: "
                    f"{previous_error}"
                )
                continue
        valid_records.append(record)
        candidates = [filename]
        if isinstance(previous, str):
            candidates.append(previous)
        if not maintenance:
            for candidate in candidates:
                if _is_protected_path(candidate):
                    errors.append(f"governance-root path is protected: {candidate}")
                    break
    if maintenance:
        has_protected = any(
            _is_protected_path(path)
            for record in valid_records
            for path in _record_paths(record)
        )
        if not has_protected:
            errors.append("governance maintenance requires a governance-root path")
        for record in valid_records:
            for path in _record_paths(record):
                if not _is_protected_path(path):
                    errors.append(
                        "governance maintenance must not mix protected "
                        f"and ordinary paths: {path}"
                    )
                    break
    return errors


def _read_json_file(path: str) -> tuple[object | None, str | None]:
    """Read a JSON file; return (data, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"cannot read JSON file {path!r}: {exc}"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"malformed JSON in {path!r}: {exc}"


def _parse_commit_subjects(data: object) -> tuple[list[str] | None, list[str]]:
    """Extract commit subjects from trusted JSON; fail closed on bad shape."""
    if not isinstance(data, list):
        return None, ["commit records JSON top level must be an array"]
    if not data:
        return None, ["no commits found in commit records"]
    subjects: list[str] = []
    errors: list[str] = []
    for index, item in enumerate(data):
        label = f"commit record {index + 1}"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        if "sha" not in item or "subject" not in item:
            errors.append(f"{label} is missing required sha/subject fields")
            continue
        sha = item["sha"]
        subject = item["subject"]
        if not isinstance(sha, str) or SHA_PATTERN.fullmatch(sha) is None:
            errors.append(f"{label} has invalid sha: {sha!r}")
            continue
        if not isinstance(subject, str):
            errors.append(f"{label} has invalid subject: {subject!r}")
            continue
        subjects.append(subject)
    if errors:
        return None, errors
    if not subjects:
        return None, ["no commits found in commit records"]
    return subjects, []


def _parse_file_records(data: object) -> tuple[list[dict] | None, list[str]]:
    """Validate changed-file JSON shape; fail closed on bad shape."""
    if not isinstance(data, list):
        return None, ["changed-file records JSON top level must be an array"]
    records: list[dict] = []
    errors: list[str] = []
    for index, item in enumerate(data):
        label = f"changed-file record {index + 1}"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        if "filename" not in item:
            errors.append(f"{label} is missing filename")
            continue
        filename = item["filename"]
        previous = item.get("previous_filename")
        filename_error = _validate_repo_path(filename)
        if filename_error is not None:
            errors.append(f"{label}: {filename_error}")
            continue
        if previous is not None and not isinstance(previous, str):
            errors.append(f"{label} has invalid previous_filename: {previous!r}")
            continue
        if isinstance(previous, str):
            previous_error = _validate_repo_path(previous)
            if previous_error is not None:
                errors.append(f"{label} previous_filename: {previous_error}")
                continue
        records.append({"filename": filename, "previous_filename": previous})
    if errors:
        return None, errors
    return records, []


def run_trusted_pr(
    title: str,
    body_file: str,
    commits_file: str,
    files_file: str,
    context_file: str,
) -> int:
    """Validate a trusted PR from base-revision data files."""
    try:
        body = Path(body_file).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read body file: {exc}", file=sys.stderr)
        return 2
    commits_data, commits_read_error = _read_json_file(commits_file)
    if commits_read_error is not None:
        print(f"error: commit records: {commits_read_error}", file=sys.stderr)
        return 2
    files_data, files_read_error = _read_json_file(files_file)
    if files_read_error is not None:
        print(f"error: changed-file records: {files_read_error}", file=sys.stderr)
        return 2
    context_data, context_read_error = _read_json_file(context_file)
    if context_read_error is not None:
        print(f"error: trusted PR context: {context_read_error}", file=sys.stderr)
        return 2
    subjects, commit_errors = _parse_commit_subjects(commits_data)
    if commit_errors:
        for error in commit_errors:
            print(f"error: commit records: {error}", file=sys.stderr)
        return 2
    file_records, file_errors = _parse_file_records(files_data)
    if file_errors:
        for error in file_errors:
            print(f"error: changed-file records: {error}", file=sys.stderr)
        return 2
    context, context_errors = _parse_trusted_context(context_data)
    if context_errors:
        for error in context_errors:
            print(f"error: trusted PR context: {error}", file=sys.stderr)
        return 2
    assert subjects is not None
    assert file_records is not None
    assert context is not None
    errors = (
        validate_subject(title)
        + validate_pr_body(body)
        + validate_commit_subjects(subjects)
        + validate_trusted_change_policy(
            title,
            body,
            file_records,
            context,
        )
    )
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 2 if errors else 0


def validate_subject(subject: str) -> list[str]:
    """Return human-readable violations for a PR title; empty means valid."""
    errors: list[str] = []
    if "\n" in subject or "\r" in subject:
        errors.append("subject must not contain a newline")
    if len(subject) > MAX_SUBJECT_LENGTH:
        errors.append(f"subject must be at most {MAX_SUBJECT_LENGTH} characters long")
    if subject != subject.strip():
        errors.append("subject must not have leading or trailing whitespace")
    if not subject.strip():
        errors.append("subject must not be blank")
        return errors
    match = SUBJECT_PATTERN.fullmatch(subject)
    if match is None:
        errors.append(
            "subject must match '<type>(<scope>)<optional-!>: <summary>' "
            f"with type in {', '.join(ALLOWED_TYPES)}"
        )
        return errors
    summary = match.group(4)
    if not summary.strip():
        errors.append("subject summary must not be empty")
    elif summary != summary.strip():
        errors.append("subject summary must not have leading or trailing whitespace")
    return errors


def extract_required_sections(body: str) -> dict[str, str]:
    """Map each required H2 section name to its comment-stripped content."""
    cleaned = HTML_COMMENT_PATTERN.sub("", body)
    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current is not None and current not in sections:
            sections[current] = "\n".join(buffer).strip()

    for line in cleaned.splitlines():
        stripped = line.strip()
        if stripped.startswith("##") and not stripped.startswith("###"):
            heading = REQUIRED_HEADING_PATTERN.fullmatch(stripped)
            flush()
            current = heading.group(1) if heading else None
            buffer = []
        elif current is not None:
            buffer.append(line)
    flush()
    return sections


def extract_named_h2_section(body: str, name: str) -> str:
    """Return comment-stripped content of one exact H2 section."""
    cleaned = HTML_COMMENT_PATTERN.sub("", body)
    target = f"## {name}"
    active = False
    buffer: list[str] = []

    for line in cleaned.splitlines():
        stripped = line.strip()
        is_h2 = stripped.startswith("##") and not stripped.startswith("###")

        if is_h2:
            if active:
                break
            active = stripped == target
            continue

        if active:
            buffer.append(line)

    return "\n".join(buffer).strip()


def validate_pr_body(body: str) -> list[str]:
    """Return human-readable violations for a PR body; empty means valid."""
    errors: list[str] = []
    cleaned = HTML_COMMENT_PATTERN.sub("", body)
    counts = {name: 0 for name in REQUIRED_SECTIONS}
    for line in cleaned.splitlines():
        stripped = line.strip()
        if stripped.startswith("##") and not stripped.startswith("###"):
            heading = REQUIRED_HEADING_PATTERN.fullmatch(stripped)
            if heading:
                counts[heading.group(1)] += 1
    sections = extract_required_sections(body)
    for name in REQUIRED_SECTIONS:
        if counts[name] == 0:
            errors.append(f"missing required section: ## {name}")
        elif counts[name] > 1:
            errors.append(f"duplicated required section: ## {name}")
        elif not sections.get(name, ""):
            errors.append(f"empty required section: ## {name}")
    verification = sections.get("Verification", "")

    if verification:
        for marker in VERIFICATION_REQUIRED_MARKERS:
            if marker not in verification:
                errors.append(
                    f"Verification must reference authoritative check {marker}"
                )

        for pattern in VOLATILE_VERIFICATION_PATTERNS:
            match = pattern.search(verification)
            if match is not None:
                errors.append(
                    "Verification contains volatile execution evidence: "
                    f"{match.group(0)!r}"
                )
    return errors


TRUSTED_CONTEXT_FIELDS = (
    "base_ref",
    "head_ref",
    "base_repo",
    "head_repo",
    "author_association",
)


def _parse_trusted_context(
    data: object,
) -> tuple[dict[str, str] | None, list[str]]:
    if not isinstance(data, dict):
        return None, ["trusted PR context must be an object"]

    context: dict[str, str] = {}
    errors: list[str] = []

    for field in TRUSTED_CONTEXT_FIELDS:
        value = data.get(field)

        if not isinstance(value, str):
            errors.append(f"trusted PR context field {field!r} must be a string")
            continue

        if not value or value != value.strip():
            errors.append(f"trusted PR context field {field!r} is invalid")
            continue

        if "\n" in value or "\r" in value:
            errors.append(f"trusted PR context field {field!r} contains a newline")
            continue

        context[field] = value

    if errors:
        return None, errors

    return context, []


def validate_trusted_change_policy(
    title: str,
    body: str,
    records: list[dict],
    context: dict[str, str],
) -> list[str]:
    """Validate ordinary versus governance-maintenance PR boundaries."""
    errors: list[str] = []

    protected_change = _records_contain_protected_path(records)

    maintenance_section = extract_named_h2_section(
        body,
        GOVERNANCE_MAINTENANCE_HEADING,
    )

    maintenance_heading_present = bool(
        re.search(
            r"(?m)^##\s+Governance maintenance\s*$",
            HTML_COMMENT_PATTERN.sub("", body),
        )
    )

    maintenance_mode = (
        maintenance_section.splitlines()[0].strip() if maintenance_section else ""
    )

    if not protected_change:
        errors.extend(
            validate_governance_changes(
                records,
                maintenance=False,
            )
        )

        if maintenance_heading_present:
            errors.append(
                "Governance maintenance section is only valid for "
                "governance-root changes"
            )

        return errors

    errors.extend(
        validate_governance_changes(
            records,
            maintenance=True,
        )
    )

    if not maintenance_heading_present:
        errors.append("protected changes require ## Governance maintenance")
    elif maintenance_mode != GOVERNANCE_MAINTENANCE_MODE:
        errors.append(
            "Governance maintenance section must begin with "
            f"{GOVERNANCE_MAINTENANCE_MODE!r}"
        )

    if GOVERNANCE_MAINTENANCE_TITLE_PATTERN.fullmatch(title) is None:
        errors.append(
            "governance maintenance title must use <type>(governance): <summary>"
        )

    if context["base_ref"] != "main":
        errors.append("governance maintenance base branch must be main")

    head_ref = context["head_ref"]

    if not head_ref.startswith("governance/") or head_ref == "governance/":
        errors.append("governance maintenance head branch must begin with governance/")

    if context["base_repo"] != context["head_repo"]:
        errors.append("governance maintenance must originate from the same repository")

    if context["author_association"] not in TRUSTED_MAINTENANCE_ASSOCIATIONS:
        errors.append("governance maintenance author association is not trusted")

    return errors


def run_pr(title: str, body_file: str) -> int:
    """Validate one PR; 0 means the contract holds, 2 means it is violated."""
    try:
        body = Path(body_file).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read body file: {exc}", file=sys.stderr)
        return 2
    errors = validate_subject(title) + validate_pr_body(body)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 2 if errors else 0


SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40}")


def validate_commit_subjects(subjects: list[str]) -> list[str]:
    """Validate every commit subject; empty means all subjects are valid."""
    errors: list[str] = []
    for index, subject in enumerate(subjects):
        for violation in validate_subject(subject):
            errors.append(
                f"commit {index + 1} (index {index}) {subject!r}: {violation}"
            )
    return errors


def run_commits(base: str, head: str) -> int:
    """Validate the commit-subject range ``base..head``; 0 means valid."""
    if SHA_PATTERN.fullmatch(base) is None:
        print(f"error: invalid base SHA: {base!r}", file=sys.stderr)
        return 2
    if SHA_PATTERN.fullmatch(head) is None:
        print(f"error: invalid head SHA: {head!r}", file=sys.stderr)
        return 2
    try:
        completed = subprocess.run(
            ["git", "log", "--format=%s", f"{base}..{head}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        print(f"error: git log failed for commit range: {exc}", file=sys.stderr)
        return 2
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()
        print(
            f"error: git log failed for commit range {base}..{head}",
            file=sys.stderr,
        )
        if detail:
            print(f"error: {detail}", file=sys.stderr)
        return 2
    subjects = (completed.stdout or "").splitlines()
    if not subjects:
        print(
            f"error: no commits found in range {base}..{head}",
            file=sys.stderr,
        )
        return 2
    errors = validate_commit_subjects(subjects)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 2 if errors else 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m ci.governance``."""
    parser = argparse.ArgumentParser(prog="ci.governance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    pr_parser = subparsers.add_parser("pr")
    pr_parser.add_argument("--title", required=True)
    pr_parser.add_argument("--body-file", required=True)
    commits_parser = subparsers.add_parser("commits")
    commits_parser.add_argument("--base", required=True)
    commits_parser.add_argument("--head", required=True)
    trusted_parser = subparsers.add_parser("trusted-pr")
    trusted_parser.add_argument("--title", required=True)
    trusted_parser.add_argument("--body-file", required=True)
    trusted_parser.add_argument("--commits-file", required=True)
    trusted_parser.add_argument("--files-file", required=True)
    trusted_parser.add_argument("--context-file", required=True)
    args = parser.parse_args(argv)
    if args.command == "pr":
        return run_pr(args.title, args.body_file)
    if args.command == "commits":
        return run_commits(args.base, args.head)
    if args.command == "trusted-pr":
        return run_trusted_pr(
            args.title,
            args.body_file,
            args.commits_file,
            args.files_file,
            args.context_file,
        )
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
