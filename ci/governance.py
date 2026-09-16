"""Executable PR governance validator.

Standard library only. No network access. No GitHub API calls.

PR metadata always enters as data (arguments and files), never as code.
"""

from __future__ import annotations

import argparse
import re
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


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m ci.governance``."""
    parser = argparse.ArgumentParser(prog="ci.governance")
    subparsers = parser.add_subparsers(dest="command", required=True)
    pr_parser = subparsers.add_parser("pr")
    pr_parser.add_argument("--title", required=True)
    pr_parser.add_argument("--body-file", required=True)
    args = parser.parse_args(argv)
    if args.command == "pr":
        return run_pr(args.title, args.body_file)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
