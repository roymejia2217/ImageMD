import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "src" / "__init__.py"
PYPROJECT = ROOT / "pyproject.toml"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
VERSIONING = ROOT / "VERSIONING.md"

SEMVER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SUBJECT_PATTERN = re.compile(
    r"(?P<type>feat|fix|perf|refactor|test|docs|build|ci|chore)"
    r"(?:\([A-Za-z0-9][A-Za-z0-9._-]*\))?"
    r"(?P<breaking>!)?"
    r": (?P<summary>.+)"
)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise AssertionError(
            f"git {' '.join(args)} failed with {completed.returncode}: {detail}"
        )
    return (completed.stdout or "").strip()


def _parse_version(value: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.fullmatch(value)
    if match is None:
        raise AssertionError(f"invalid stable SemVer version: {value!r}")
    return tuple(int(group) for group in match.groups())


def _format_version(value: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in value)


def _project_version() -> str:
    text = VERSION_FILE.read_text(encoding="utf-8")
    matches = re.findall(
        r'(?m)^__version__ = "([^"]+)"\s*$',
        text,
    )
    if len(matches) != 1:
        raise AssertionError(
            "src/__init__.py must define exactly one quoted __version__"
        )
    return matches[0]


def _github_event_payload() -> dict[str, object]:
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")

    if not event_path:
        raise AssertionError(
            "GITHUB_EVENT_PATH is required for pull_request version governance"
        )

    try:
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssertionError(
            "unable to read GitHub pull_request event payload"
        ) from exc

    if not isinstance(payload, dict):
        raise AssertionError("GitHub event payload must be a JSON object")

    return payload


def _pull_request_sha(
    payload: dict[str, object],
    side: str,
) -> str:
    if side not in {"base", "head"}:
        raise AssertionError(f"invalid pull request side: {side!r}")

    try:
        pull_request = payload["pull_request"]
        side_payload = pull_request[side]
        value = side_payload["sha"]
    except (KeyError, TypeError) as exc:
        raise AssertionError(
            f"GitHub event payload is missing pull_request.{side}.sha"
        ) from exc

    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise AssertionError(
            f"pull_request.{side}.sha is not a 40-character lowercase Git SHA"
        )

    _git(
        "cat-file",
        "-e",
        f"{value}^{{commit}}",
    )

    return value


def _semantic_history_tips() -> tuple[str, ...]:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return ("HEAD",)

    if os.environ.get("GITHUB_EVENT_NAME", "") != "pull_request":
        return ("HEAD",)

    payload = _github_event_payload()

    return (
        _pull_request_sha(payload, "base"),
        _pull_request_sha(payload, "head"),
    )


def _reachable_release_tags() -> list[tuple[tuple[int, int, int], str]]:
    tags: list[tuple[tuple[int, int, int], str]] = []

    for tag in _git(
        "tag",
        "--merged",
        "HEAD",
        "--list",
        "v*",
    ).splitlines():
        if not tag.startswith("v"):
            raise AssertionError(f"release-like tag is malformed: {tag!r}")

        value = tag[1:]

        if SEMVER_PATTERN.fullmatch(value) is None:
            raise AssertionError(f"release-like tag is not stable SemVer: {tag!r}")

        tags.append((_parse_version(value), tag))

    if not tags:
        raise AssertionError(
            "no reachable stable release tags matching vMAJOR.MINOR.PATCH"
        )

    return sorted(tags)


def _commit_subjects(base_tag: str) -> list[str]:
    history_tips = _semantic_history_tips()

    output = _git(
        "log",
        "--format=%s",
        f"^{base_tag}",
        *history_tips,
    )

    return output.splitlines() if output else []


def _required_bump(subjects: list[str]) -> str | None:
    if not subjects:
        return None

    rank = 1

    for subject in subjects:
        match = SUBJECT_PATTERN.fullmatch(subject)

        if match is None:
            raise AssertionError(
                "unreleased commit subject does not satisfy "
                "ImageMD Conventional Commit grammar: "
                f"{subject!r}"
            )

        if match.group("breaking"):
            rank = max(rank, 3)
        elif match.group("type") == "feat":
            rank = max(rank, 2)

    return {
        1: "patch",
        2: "minor",
        3: "major",
    }[rank]


def _bump(
    base: tuple[int, int, int],
    bump: str | None,
) -> tuple[int, int, int]:
    major, minor, patch = base

    if bump is None:
        return base

    if bump == "patch":
        return major, minor, patch + 1

    if bump == "minor":
        return major, minor + 1, 0

    if bump == "major":
        return major + 1, 0, 0

    raise AssertionError(f"unknown bump: {bump!r}")


def _history_contract_is_required() -> bool:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return True

    event = os.environ.get("GITHUB_EVENT_NAME", "")
    ref = os.environ.get("GITHUB_REF", "")

    return event == "pull_request" or ref == "refs/heads/main"


class VersionContractTests(unittest.TestCase):
    def test_pull_request_history_uses_authored_base_and_head(self):
        base_sha = "1" * 40
        head_sha = "2" * 40

        payload = {
            "pull_request": {
                "base": {"sha": base_sha},
                "head": {"sha": head_sha},
            }
        }

        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "event.json"
            event_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            environment = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event_path),
            }

            with patch.dict(
                os.environ,
                environment,
                clear=False,
            ):
                with patch(
                    f"{__name__}._git",
                    return_value="fix(release): example",
                ) as git:
                    subjects = _commit_subjects("v1.1.1")

        calls = [entry.args for entry in git.call_args_list]

        self.assertEqual(
            subjects,
            ["fix(release): example"],
        )
        self.assertIn(
            (
                "log",
                "--format=%s",
                "^v1.1.1",
                base_sha,
                head_sha,
            ),
            calls,
        )
        self.assertNotIn(
            (
                "log",
                "--format=%s",
                "v1.1.1..HEAD",
            ),
            calls,
        )

    def test_pull_request_history_requires_event_path(self):
        environment = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": "",
        }

        with patch.dict(
            os.environ,
            environment,
            clear=False,
        ):
            with self.assertRaisesRegex(
                AssertionError,
                "GITHUB_EVENT_PATH",
            ):
                _commit_subjects("v1.1.1")

    def test_pull_request_history_rejects_malformed_sha(self):
        payload = {
            "pull_request": {
                "base": {"sha": "1" * 40},
                "head": {"sha": "not-a-sha"},
            }
        }

        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "event.json"
            event_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            environment = {
                "GITHUB_ACTIONS": "true",
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_EVENT_PATH": str(event_path),
            }

            with patch.dict(
                os.environ,
                environment,
                clear=False,
            ):
                with patch(
                    f"{__name__}._git",
                    return_value="",
                ):
                    with self.assertRaisesRegex(
                        AssertionError,
                        "head.sha",
                    ):
                        _commit_subjects("v1.1.1")

    def test_push_history_uses_head(self):
        environment = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "push",
        }

        with patch.dict(
            os.environ,
            environment,
            clear=False,
        ):
            with patch(
                f"{__name__}._git",
                return_value="fix(release): example",
            ) as git:
                subjects = _commit_subjects("v1.1.1")

        self.assertEqual(
            subjects,
            ["fix(release): example"],
        )

        git.assert_called_once_with(
            "log",
            "--format=%s",
            "^v1.1.1",
            "HEAD",
        )

    def test_local_history_uses_head(self):
        environment = {
            "GITHUB_ACTIONS": "false",
            "GITHUB_EVENT_NAME": "",
        }

        with patch.dict(
            os.environ,
            environment,
            clear=False,
        ):
            with patch(
                f"{__name__}._git",
                return_value="fix(release): example",
            ) as git:
                subjects = _commit_subjects("v1.1.1")

        self.assertEqual(
            subjects,
            ["fix(release): example"],
        )

        git.assert_called_once_with(
            "log",
            "--format=%s",
            "^v1.1.1",
            "HEAD",
        )

    def test_project_version_is_strict_stable_semver(self):
        version = _project_version()

        self.assertEqual(
            _format_version(_parse_version(version)),
            version,
        )

    def test_setuptools_uses_src_version_as_single_source(self):
        pyproject = PYPROJECT.read_text(encoding="utf-8")

        self.assertIn(
            'dynamic = ["version"]',
            pyproject,
        )
        self.assertIn(
            'version = { attr = "src.__version__" }',
            pyproject,
        )

    def test_unreleased_version_matches_required_semver_bump(self):
        if not _history_contract_is_required():
            self.skipTest(
                "history-derived version validation belongs to "
                "local/Verify execution, not shallow "
                "package/promotion jobs"
            )

        self.assertEqual(
            _git(
                "rev-parse",
                "--is-shallow-repository",
            ),
            "false",
            "version governance requires complete Git history",
        )

        base_version, base_tag = max(_reachable_release_tags())
        subjects = _commit_subjects(base_tag)
        bump = _required_bump(subjects)

        expected = _format_version(
            _bump(
                base_version,
                bump,
            )
        )
        actual = _project_version()

        self.assertEqual(
            actual,
            expected,
            (
                f"src.__version__={actual} does not match "
                f"the required version {expected}; "
                f"base={base_tag}, "
                f"unreleased_commits={len(subjects)}, "
                f"required_bump={bump or 'none'}"
            ),
        )

    def test_tag_trigger_matches_source_version(self):
        if os.environ.get("GITHUB_ACTIONS") != "true":
            self.skipTest("GitHub tag-trigger contract is evaluated only in Actions")

        if os.environ.get("GITHUB_REF_TYPE") != "tag":
            self.skipTest("current Actions run was not triggered from a tag")

        tag = os.environ.get(
            "GITHUB_REF_NAME",
            "",
        )

        self.assertEqual(
            tag,
            f"v{_project_version()}",
        )

    def test_versioning_document_is_present_and_linked(self):
        self.assertTrue(
            VERSIONING.is_file(),
            "VERSIONING.md must exist",
        )

        versioning = VERSIONING.read_text(encoding="utf-8")
        contributing = CONTRIBUTING.read_text(encoding="utf-8")

        for required in (
            "# ImageMD versioning contract",
            "src.__version__",
            "MAJOR",
            "MINOR",
            "PATCH",
            "Conventional Commits",
            "ImageMD-specific",
        ):
            with self.subTest(required=required):
                self.assertIn(
                    required,
                    versioning,
                )

        self.assertIn(
            "[VERSIONING.md](VERSIONING.md)",
            contributing,
        )


if __name__ == "__main__":
    unittest.main()
