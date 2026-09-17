"""Contract for the trusted PR governance workflow."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "pr-governance.yml"

SETUP_PYTHON_SHA = "a26af69be951a213d495a4c3e4e4022e16d87065"


class PrGovernanceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_name_is_pr_governance(self):
        self.assertRegex(self.workflow, r"(?m)^name:\s*PR Governance\s*$")

    def test_trigger_is_pull_request_target_with_exact_activity_types(self):
        self.assertIn("pull_request_target", self.workflow)
        self.assertNotRegex(self.workflow, r"(?m)^  pull_request:\s*$")
        self.assertIn("types: [opened, edited, reopened, synchronize]", self.workflow)

    def test_global_permissions_are_read_only(self):
        self.assertRegex(
            self.workflow,
            r"(?m)^permissions:\n  contents: read\n  pull-requests: read\s*$",
        )
        self.assertNotIn("contents: write", self.workflow)
        self.assertNotIn("secrets.", self.workflow)
        for forbidden in (
            "actions: write",
            "checks: write",
            "issues: write",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.workflow)

    def test_checkout_uses_trusted_base_sha(self):
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", self.workflow)

    def test_checkout_does_not_persist_credentials(self):
        self.assertRegex(self.workflow, r"(?m)^\s+persist-credentials:\s*false\s*$")

    def test_head_checkout_is_forbidden(self):
        self.assertNotIn("github.event.pull_request.head.sha", self.workflow)
        self.assertNotIn("github.head_ref", self.workflow)

    def test_required_display_name_and_job_key(self):
        self.assertIn("name: Required PR Governance", self.workflow)
        self.assertRegex(self.workflow, r"(?m)^  pr-governance:\s*$")

    def test_python_action_is_pinned_to_expected_sha(self):
        self.assertIn(f"actions/setup-python@{SETUP_PYTHON_SHA}", self.workflow)
        self.assertRegex(
            self.workflow, r"(?m)^\s+python-version:\s*[\"']?3\.12[\"']?\s*$"
        )

    def test_runner_and_timeout_are_fixed(self):
        self.assertIn("runs-on: ubuntu-24.04", self.workflow)
        self.assertRegex(self.workflow, r"(?m)^\s+timeout-minutes:\s*10\s*$")

    def test_validator_runs_from_the_trusted_checkout(self):
        self.assertIn("python -m ci.governance trusted-pr", self.workflow)
        self.assertIn("--body-file", self.workflow)
        self.assertIn("--commits-file", self.workflow)
        self.assertIn("--files-file", self.workflow)
        self.assertIn("$RUNNER_TEMP/pr-commits.json", self.workflow)
        self.assertIn("$RUNNER_TEMP/pr-files.json", self.workflow)
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", self.workflow)

    def test_commit_metadata_comes_from_github_api(self):
        self.assertIn(
            "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/commits", self.workflow
        )
        self.assertIn("--paginate", self.workflow)
        self.assertIn("--slurp", self.workflow)
        self.assertIn("GH_TOKEN", self.workflow)
        self.assertIn("github.token", self.workflow)
        self.assertIn("PR_NUMBER", self.workflow)
        self.assertIn("github.event.pull_request.number", self.workflow)

    def test_changed_file_metadata_comes_from_github_api(self):
        self.assertIn(
            "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/files", self.workflow
        )
        self.assertIn("previous_filename", self.workflow)
        self.assertIn("$RUNNER_TEMP/pr-files.json", self.workflow)

    def test_pr_number_is_validated_before_use(self):
        self.assertIn("set -euo pipefail", self.workflow)
        self.assertIn("PR_NUMBER", self.workflow)
        self.assertIn("[!0-9]", self.workflow)

    def test_trusted_validation_uses_data_only(self):
        self.assertIn('--title "$PR_TITLE"', self.workflow)
        self.assertIn('--body-file "$RUNNER_TEMP/pr-body.md"', self.workflow)
        self.assertIn('--commits-file "$RUNNER_TEMP/pr-commits.json"', self.workflow)
        self.assertIn('--files-file "$RUNNER_TEMP/pr-files.json"', self.workflow)

    def test_no_execution_of_head_code(self):
        self.assertNotIn("github.event.pull_request.head.sha", self.workflow)
        for forbidden in ("eval ", "exec ", "shell=True"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.workflow)

    def test_no_dependency_installation(self):
        self.assertNotIn("setup-uv", self.workflow)
        self.assertNotIn("uv sync", self.workflow)

    def test_pr_metadata_flows_only_as_data(self):
        self.assertRegex(self.workflow, re.compile(r"PR_TITLE", re.MULTILINE))
        self.assertRegex(self.workflow, re.compile(r"RUNNER_TEMP/pr-body\.md"))

    def test_slurped_pages_are_not_reslurped(self):
        self.assertNotIn("jq -s", self.workflow)

    def test_paginated_api_calls_retain_paginate_and_slurp(self):
        self.assertGreaterEqual(self.workflow.count("--paginate"), 2)
        self.assertGreaterEqual(self.workflow.count("--slurp"), 2)

    def test_commit_pages_normalized_exactly_once(self):
        self.assertIn('"$RUNNER_TEMP/commits-pages.json"', self.workflow)
        self.assertIn('"$RUNNER_TEMP/pr-commits.json"', self.workflow)
        self.assertRegex(self.workflow, r"jq\s+(\\\n\s+)?'add \| map")
        self.assertIn("sha: .sha", self.workflow)
        self.assertIn("$RUNNER_TEMP/commits-pages.json", self.workflow)

    def test_file_pages_normalized_exactly_once(self):
        self.assertIn('"$RUNNER_TEMP/files-pages.json"', self.workflow)
        self.assertIn('"$RUNNER_TEMP/pr-files.json"', self.workflow)
        self.assertRegex(self.workflow, r"jq\s+(\\\n\s+)?'add \| map")
        self.assertIn("filename: .filename", self.workflow)
        self.assertIn("previous_filename", self.workflow)
        self.assertIn("$RUNNER_TEMP/files-pages.json", self.workflow)

    def test_trusted_pr_context_is_materialized_from_event_metadata(self):
        for expected in (
            "github.event.pull_request.base.ref",
            "github.event.pull_request.head.ref",
            "github.event.pull_request.base.repo.full_name",
            "github.event.pull_request.head.repo.full_name",
            "github.event.pull_request.author_association",
            "$RUNNER_TEMP/pr-context.json",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.workflow)

    def test_validator_receives_context_file(self):
        self.assertIn(
            '--context-file "$RUNNER_TEMP/pr-context.json"',
            self.workflow,
        )

    def test_context_is_data_only(self):
        self.assertIn("jq -n", self.workflow)
        self.assertNotIn("eval ", self.workflow)
        self.assertNotIn("exec ", self.workflow)


if __name__ == "__main__":
    unittest.main()
