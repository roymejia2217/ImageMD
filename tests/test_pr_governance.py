"""Behavioral contract for the executable PR governance validator."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ci.governance import (
    extract_required_sections,
    validate_pr_body,
    validate_subject,
)

try:
    from ci.governance import validate_commit_subjects
except ImportError:
    validate_commit_subjects = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]

VALID_BODY = """## Summary

Added a Windows release builder.

## Verification

Ran the focused contract tests.

## Release impact

None.
"""

VALID_SUBJECTS = (
    "feat: add Windows release builder",
    "fix(release): normalize artifact names",
    "ci(governance): enforce PR contract",
    "refactor(domain)!: replace temporal model",
)


def run_governance_cli(title, body):
    """Execute the governance CLI and return its process exit code."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", encoding="utf-8", delete=False
    ) as handle:
        handle.write(body)
        body_path = handle.name
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "ci.governance",
                "pr",
                "--title",
                title,
                "--body-file",
                body_path,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        Path(body_path).unlink(missing_ok=True)
    return completed.returncode


class SubjectContractTests(unittest.TestCase):
    def test_valid_conventional_subjects_are_accepted(self):
        for subject in VALID_SUBJECTS:
            with self.subTest(subject=subject):
                self.assertEqual(validate_subject(subject), [])

    def test_invalid_type_is_rejected(self):
        self.assertTrue(validate_subject("feature: add thing"))

    def test_missing_colon_space_is_rejected(self):
        self.assertTrue(validate_subject("feat:add thing"))

    def test_empty_summary_is_rejected(self):
        self.assertTrue(validate_subject("fix:"))
        self.assertTrue(validate_subject("feat: "))

    def test_overlong_subject_is_rejected(self):
        self.assertTrue(validate_subject("feat: " + "x" * 67))

    def test_newline_injection_is_rejected(self):
        self.assertTrue(validate_subject("feat: add thing\nFixes: #1"))

    def test_uppercase_type_is_rejected(self):
        self.assertTrue(validate_subject("FIX: repair the build"))

    def test_whitespace_only_title_is_rejected(self):
        self.assertTrue(validate_subject("   "))

    def test_malformed_scope_is_rejected(self):
        self.assertTrue(validate_subject("feat(): add thing"))
        self.assertTrue(validate_subject("feat( ): add thing"))

    def test_title_length_boundary(self):
        accepted = "feat: " + "x" * 66
        rejected = "feat: " + "x" * 67
        self.assertEqual(len(accepted), 72)
        self.assertEqual(len(rejected), 73)
        self.assertEqual(validate_subject(accepted), [])
        self.assertTrue(validate_subject(rejected))


class BodyContractTests(unittest.TestCase):
    def test_complete_body_is_accepted(self):
        self.assertEqual(validate_pr_body(VALID_BODY), [])

    def test_missing_summary_is_rejected(self):
        body = VALID_BODY.replace(
            "## Summary\n\nAdded a Windows release builder.\n\n", ""
        )
        self.assertTrue(validate_pr_body(body))

    def test_missing_verification_is_rejected(self):
        body = VALID_BODY.replace(
            "## Verification\n\nRan the focused contract tests.\n\n", ""
        )
        self.assertTrue(validate_pr_body(body))

    def test_missing_release_impact_is_rejected(self):
        body = VALID_BODY.replace("## Release impact\n\nNone.\n", "")
        self.assertTrue(validate_pr_body(body))

    def test_html_comment_only_section_is_rejected(self):
        body = (
            "## Summary\n\n<!-- TODO: fill this in -->\n\n"
            "## Verification\n\nRan tests.\n\n## Release impact\n\nNone.\n"
        )
        self.assertTrue(validate_pr_body(body))

    def test_heading_inside_html_comment_does_not_count(self):
        body = (
            "## Summary\n\nChange.\n\n<!-- ## Verification -->\n\n"
            "## Release impact\n\nNone.\n"
        )
        self.assertTrue(validate_pr_body(body))

    def test_duplicated_required_heading_is_rejected(self):
        body = (
            "## Summary\n\nFirst.\n\n## Summary\n\nSecond.\n\n"
            "## Verification\n\nRan tests.\n\n## Release impact\n\nNone.\n"
        )
        self.assertTrue(validate_pr_body(body))

    def test_wrong_heading_level_does_not_count(self):
        for heading in ("# Summary", "### Summary"):
            with self.subTest(heading=heading):
                body = (
                    f"{heading}\n\nChange.\n\n## Verification\n\nRan tests.\n\n"
                    "## Release impact\n\nNone.\n"
                )
                self.assertTrue(validate_pr_body(body))

    def test_content_in_one_section_cannot_satisfy_another(self):
        body = "## Summary\n\n\n## Verification\n\nRan tests.\n\n## Release impact\n\nNone.\n"
        self.assertTrue(validate_pr_body(body))

    def test_filled_body_keeps_template_comments(self):
        body = (
            "## Summary\n\n<!-- Explain the change. -->\n\nAdded the builder.\n\n"
            "## Verification\n\n<!-- Provide evidence. -->\n\nRan tests.\n\n"
            "## Release impact\n\n<!-- State impact. -->\n\nNone.\n"
        )
        self.assertEqual(validate_pr_body(body), [])


class ExtractSectionsTests(unittest.TestCase):
    def test_extract_returns_required_sections(self):
        sections = extract_required_sections(VALID_BODY)
        self.assertEqual(set(sections), {"Summary", "Verification", "Release impact"})
        self.assertEqual(sections["Summary"], "Added a Windows release builder.")
        self.assertEqual(sections["Verification"], "Ran the focused contract tests.")
        self.assertEqual(sections["Release impact"], "None.")

    def test_extract_strips_html_comments(self):
        body = (
            "## Summary\n\n<!-- Explain. -->\n\nAdded the builder.\n\n"
            "## Verification\n\nRan tests.\n\n## Release impact\n\nNone.\n"
        )
        sections = extract_required_sections(body)
        self.assertEqual(sections["Summary"], "Added the builder.")

    def test_extract_comment_only_section_is_empty(self):
        body = (
            "## Summary\n\n<!-- TODO -->\n\n"
            "## Verification\n\nRan tests.\n\n## Release impact\n\nNone.\n"
        )
        sections = extract_required_sections(body)
        self.assertEqual(sections["Summary"], "")


class GovernanceCliTests(unittest.TestCase):
    def test_valid_pr_exits_zero(self):
        self.assertEqual(run_governance_cli(VALID_SUBJECTS[0], VALID_BODY), 0)

    def test_invalid_title_exits_two(self):
        self.assertEqual(run_governance_cli("Update files", VALID_BODY), 2)

    def test_invalid_body_exits_two(self):
        self.assertEqual(run_governance_cli(VALID_SUBJECTS[0], "no sections"), 2)


class CommitSubjectsContractTests(unittest.TestCase):
    def _validator(self):
        self.assertTrue(
            callable(validate_commit_subjects),
            "ci.governance must expose validate_commit_subjects(subjects)",
        )
        return validate_commit_subjects

    def test_validator_function_exists(self):
        self.assertTrue(
            callable(validate_commit_subjects),
            "ci.governance must expose validate_commit_subjects(subjects)",
        )

    def test_valid_sequence_is_accepted(self):
        validate = self._validator()
        subjects = [
            "feat: add Windows release builder",
            "fix(release): normalize artifact names",
            "ci(governance): enforce commit subjects",
        ]
        self.assertEqual(validate(subjects), [])

    def test_invalid_subject_is_rejected_with_position(self):
        validate = self._validator()
        subjects = [
            "feat: add Windows release builder",
            "Update files",
            "fix: repair the build",
        ]
        errors = validate(subjects)
        self.assertTrue(errors, "invalid commit subject must be reported")
        combined = "\n".join(errors)
        self.assertIn("2", combined)
        self.assertIn("Update files", combined)

    def test_every_commit_is_validated_not_only_head(self):
        validate = self._validator()
        middle_bad = [
            "feat: first change",
            "not a conventional subject",
            "fix: third change",
        ]
        errors = validate(middle_bad)
        self.assertTrue(errors)
        self.assertIn("2", "\n".join(errors))
        first_bad = ["not a conventional subject", "feat: second change"]
        self.assertTrue(validate(first_bad))
        last_bad = ["feat: first change", "not a conventional subject"]
        errors = validate(last_bad)
        self.assertTrue(errors)
        self.assertIn("2", "\n".join(errors))

    def test_empty_subject_is_rejected(self):
        validate = self._validator()
        self.assertTrue(validate(["feat: valid change", ""]))
        self.assertTrue(validate(["   "]))

    def test_newline_injection_is_rejected(self):
        validate = self._validator()
        self.assertTrue(validate(["feat: add thing\nFixes: #1"]))

    def test_subject_length_policy_is_preserved(self):
        validate = self._validator()
        accepted = "feat: " + "x" * 66
        rejected = "feat: " + "x" * 67
        self.assertEqual(len(accepted), 72)
        self.assertEqual(len(rejected), 73)
        self.assertEqual(validate([accepted]), [])
        errors = validate([rejected])
        self.assertTrue(errors)
        self.assertIn("1", "\n".join(errors))


def run_commits_cli(base, head):
    """Execute the commit-range CLI and return the completed process."""
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ci.governance",
            "commits",
            "--base",
            base,
            "--head",
            head,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed


class CommitsCliContractTests(unittest.TestCase):
    VALID_BASE = "0" * 40
    VALID_HEAD = "1" * 40

    def test_cli_rejects_malformed_base_sha_before_git(self):
        completed = run_commits_cli("not-a-sha", self.VALID_HEAD)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("base", (completed.stderr or "").lower())

    def test_cli_rejects_malformed_head_sha_before_git(self):
        completed = run_commits_cli(self.VALID_BASE, "ZZZ")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("head", (completed.stderr or "").lower())

    def test_cli_propagates_git_range_failure_as_exit_two(self):
        completed = run_commits_cli(self.VALID_BASE, self.VALID_HEAD)
        self.assertEqual(completed.returncode, 2)
        stderr = (completed.stderr or "").lower()
        self.assertTrue(
            ("git" in stderr) or ("range" in stderr) or ("no commit" in stderr),
            f"git-range failure must be reported on stderr, got: {completed.stderr!r}",
        )

    def test_cli_returns_two_when_one_commit_subject_is_invalid(self):
        import io
        import unittest.mock as mock
        from contextlib import redirect_stderr

        from ci import governance

        fake = mock.Mock(
            returncode=0,
            stdout="feat: valid change\nUpdate files\n",
            stderr="",
        )
        stderr_capture = io.StringIO()
        try:
            with mock.patch("subprocess.run", return_value=fake):
                with redirect_stderr(stderr_capture):
                    code = governance.main(
                        [
                            "commits",
                            "--base",
                            self.VALID_BASE,
                            "--head",
                            self.VALID_HEAD,
                        ]
                    )
        except SystemExit as exc:
            code = exc.code
        # When the validator is absent the CLI cannot report the subject;
        # a correct implementation exits 2 and names the invalid subject.
        self.assertEqual(code, 2)
        combined = stderr_capture.getvalue()
        self.assertIn(
            "Update files",
            combined,
            "commit validator must identify the invalid subject on stderr",
        )
        self.assertIn(
            "2",
            combined,
            "commit validator must identify the ordinal of the invalid subject",
        )


if __name__ == "__main__":
    unittest.main()
