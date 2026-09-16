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

MAX_SUBJECT_LENGTH = 72

PROTECTED_GOVERNANCE_PREFIXES = (
    ".github/workflows/",
    ".github/actions/",
    "ci/",
)

PROTECTED_GOVERNANCE_PATHS = (
    "tests/test_architecture_contract.py",
    "tests/test_pr_governance.py",
    "tests/test_pr_governance_workflow.py",
    "tests/test_quality_workflow_contract.py",
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


def validate_governance_changes(records: object) -> list[str]:
    """Validate changed-file records; empty means no governance violation."""
    errors: list[str] = []
    if not isinstance(records, list):
        return ["changed-file records must be a list"]
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
        candidates = [filename]
        if isinstance(previous, str):
            candidates.append(previous)
        for candidate in candidates:
            if _is_protected_path(candidate):
                errors.append(f"governance-root path is protected: {candidate}")
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
    title: str, body_file: str, commits_file: str, files_file: str
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
    assert subjects is not None
    assert file_records is not None
    errors = (
        validate_subject(title)
        + validate_pr_body(body)
        + validate_commit_subjects(subjects)
        + validate_governance_changes(file_records)
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
    args = parser.parse_args(argv)
    if args.command == "pr":
        return run_pr(args.title, args.body_file)
    if args.command == "commits":
        return run_commits(args.base, args.head)
    if args.command == "trusted-pr":
        return run_trusted_pr(
            args.title, args.body_file, args.commits_file, args.files_file
        )
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
