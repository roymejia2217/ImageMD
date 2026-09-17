"""Validate immutable release-source provenance from protected main."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

STABLE_TAG_PATTERN = re.compile(
    r"^v"
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)$"
)

STABLE_VERSION_PATTERN = re.compile(
    r"^"
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)$"
)


class ReleaseProvenanceError(ValueError):
    """Raised when a release source violates provenance policy."""


def normalize_source_ref(
    value: str,
    *,
    require_tag: bool,
) -> tuple[str, str | None]:
    """Return canonical immutable ref and optional stable tag name."""
    if not isinstance(value, str):
        raise ReleaseProvenanceError("release source ref must be a string")

    if not value or value != value.strip():
        raise ReleaseProvenanceError(
            "release source ref must be non-empty and normalized"
        )

    if value.startswith("refs/tags/"):
        tag_name = value.removeprefix("refs/tags/")

        if STABLE_TAG_PATTERN.fullmatch(tag_name) is None:
            raise ReleaseProvenanceError(
                "release tag must be stable vMAJOR.MINOR.PATCH"
            )

        return value, tag_name

    if STABLE_TAG_PATTERN.fullmatch(value) is not None:
        return f"refs/tags/{value}", value

    if require_tag:
        raise ReleaseProvenanceError(
            "this release operation requires a stable release tag"
        )

    if FULL_SHA_PATTERN.fullmatch(value) is not None:
        return value, None

    raise ReleaseProvenanceError(
        "release source must be a stable release tag "
        "or full lowercase 40-character commit SHA"
    )


def _run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _git_output(*args: str) -> str:
    completed = _run_git(*args)

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()

        raise ReleaseProvenanceError(
            f"git {' '.join(args)} failed with {completed.returncode}: {detail}"
        )

    return (completed.stdout or "").strip()


def _resolve_commit(ref: str) -> str:
    commit = _git_output(
        "rev-parse",
        "--verify",
        f"{ref}^{{commit}}",
    )

    if FULL_SHA_PATTERN.fullmatch(commit) is None:
        raise ReleaseProvenanceError(
            f"ref did not resolve to a full commit SHA: {ref!r}"
        )

    return commit


def _is_ancestor(
    ancestor: str,
    descendant: str,
) -> bool:
    completed = _run_git(
        "merge-base",
        "--is-ancestor",
        ancestor,
        descendant,
    )

    if completed.returncode == 0:
        return True

    if completed.returncode == 1:
        return False

    detail = (completed.stderr or completed.stdout or "").strip()

    raise ReleaseProvenanceError(
        f"unable to evaluate protected-main ancestry: {detail}"
    )


def _project_version() -> str:
    source = (PROJECT_ROOT / "src" / "__init__.py").read_text(encoding="utf-8")

    matches = re.findall(
        r'(?m)^__version__ = "([^"]+)"\s*$',
        source,
    )

    if len(matches) != 1:
        raise ReleaseProvenanceError(
            "src/__init__.py must define exactly one __version__"
        )

    version = matches[0]

    if STABLE_VERSION_PATTERN.fullmatch(version) is None:
        raise ReleaseProvenanceError(
            "release provenance requires stable MAJOR.MINOR.PATCH"
        )

    return version


def validate_release_source(
    source_ref: str,
    main_ref: str,
    *,
    require_tag: bool,
) -> dict[str, str | None]:
    """Validate and describe one immutable release source."""
    if not isinstance(main_ref, str) or not main_ref or main_ref != main_ref.strip():
        raise ReleaseProvenanceError(
            "protected main ref must be non-empty and normalized"
        )

    normalized_ref, tag_name = normalize_source_ref(
        source_ref,
        require_tag=require_tag,
    )

    source_commit = _resolve_commit(normalized_ref)
    checkout_commit = _resolve_commit("HEAD")

    if source_commit != checkout_commit:
        raise ReleaseProvenanceError(
            "release source commit does not match checked-out HEAD"
        )

    main_commit = _resolve_commit(main_ref)

    if not _is_ancestor(
        source_commit,
        main_commit,
    ):
        raise ReleaseProvenanceError(
            "release source commit is not reachable from protected main"
        )

    project_version = _project_version()

    if tag_name is not None and tag_name != f"v{project_version}":
        raise ReleaseProvenanceError(
            f"release tag {tag_name} does not match project version v{project_version}"
        )

    return {
        "source_ref": normalized_ref,
        "source_commit": source_commit,
        "main_ref": main_ref,
        "main_commit": main_commit,
        "project_version": project_version,
        "tag": tag_name,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "--source-ref",
        required=True,
    )

    parser.add_argument(
        "--main-ref",
        required=True,
    )

    parser.add_argument(
        "--require-tag",
        action="store_true",
    )

    args = parser.parse_args(argv)

    try:
        evidence = validate_release_source(
            args.source_ref,
            args.main_ref,
            require_tag=args.require_tag,
        )
    except (
        OSError,
        ReleaseProvenanceError,
    ) as error:
        print(
            f"release provenance validation failed: {error}",
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            evidence,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
