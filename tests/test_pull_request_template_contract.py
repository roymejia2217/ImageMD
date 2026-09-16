import re
import unittest
from pathlib import Path

from ci.governance import validate_pr_body


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / ".github" / "pull_request_template.md"

EXPECTED_TEMPLATE = """## Summary

<!--
Explain the behavioral or repository change and why it exists.
Keep this section declarative. Do not copy execution counters here.
-->

## Verification

<!--
Describe the verification strategy without hard-coding volatile execution
metrics.

Authoritative remote verification is the GitHub check set attached to the
current PR head, including `Required PR Governance` and `Required CI`.

Do not manually copy test counts, skipped counts, vulnerability counts,
workflow status, build duration, artifact hashes, or similar values that can
become stale after another commit.
-->

## Release impact

<!--
State None, PATCH, MINOR, MAJOR, or explain the release implication.
Do not claim a release was published unless the release workflow actually
published it.
-->
"""

CANONICAL_STABLE_BODY = """## Summary

Add executable semantic-version governance derived from the latest reachable
release tag and Conventional Commit history, advance ImageMD's development
version from 1.1.1 to 1.1.2, and make PR verification evidence resilient to
later head updates.

## Verification

Local XP Test-First RED/GREEN and the complete product gate were executed for
this change. Authoritative remote verification is provided by the required
GitHub checks attached to the current PR head:

- `Required PR Governance`
- `Required CI`

Volatile execution metrics are intentionally not duplicated in this body.

## Release impact

PATCH. This change establishes 1.1.2 as the required development version after
v1.1.1. It does not create a tag or publish a release.
"""

VOLATILE_CLAIM_PATTERNS = (
    re.compile(r"\b\d+\s+tests?\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+(?:passed|failed|skipped)\b", re.IGNORECASE),
    re.compile(r"\b\d+\s+vulnerabilit(?:y|ies)\b", re.IGNORECASE),
)


class PullRequestTemplateContractTests(unittest.TestCase):
    def test_template_matches_canonical_contract(self):
        self.assertEqual(
            TEMPLATE.read_text(encoding="utf-8"),
            EXPECTED_TEMPLATE,
        )

    def test_template_has_exact_required_h2_sections(self):
        headings = [
            line.removeprefix("## ")
            for line in EXPECTED_TEMPLATE.splitlines()
            if line.startswith("## ")
        ]

        self.assertEqual(
            headings,
            ["Summary", "Verification", "Release impact"],
        )

    def test_template_names_authoritative_remote_checks(self):
        self.assertIn(
            "`Required PR Governance`",
            EXPECTED_TEMPLATE,
        )
        self.assertIn(
            "`Required CI`",
            EXPECTED_TEMPLATE,
        )

    def test_template_does_not_use_fake_dynamic_placeholders(self):
        self.assertNotRegex(
            EXPECTED_TEMPLATE,
            r"\{\{[^}]+\}\}",
        )

    def test_unfilled_template_is_rejected_by_body_governance(self):
        self.assertTrue(
            validate_pr_body(EXPECTED_TEMPLATE),
            "HTML-comment-only template must not satisfy PR body governance",
        )

    def test_canonical_stable_body_is_accepted(self):
        self.assertEqual(
            validate_pr_body(CANONICAL_STABLE_BODY),
            [],
        )

    def test_canonical_body_contains_no_volatile_metric_claims(self):
        for pattern in VOLATILE_CLAIM_PATTERNS:
            with self.subTest(pattern=pattern.pattern):
                self.assertIsNone(
                    pattern.search(CANONICAL_STABLE_BODY),
                )

        self.assertIsNone(
            re.search(
                r"\b[0-9a-f]{40}\b",
                CANONICAL_STABLE_BODY,
                re.IGNORECASE,
            )
        )


if __name__ == "__main__":
    unittest.main()
