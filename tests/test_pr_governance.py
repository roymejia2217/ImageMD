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


if __name__ == "__main__":
    unittest.main()
