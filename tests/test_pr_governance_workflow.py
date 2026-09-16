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
        self.assertRegex(self.workflow, r"(?m)^permissions:\n  contents: read\s*$")
        self.assertNotIn("contents: write", self.workflow)
        self.assertNotIn("secrets.", self.workflow)

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
        self.assertIn("python -m ci.governance pr", self.workflow)
        self.assertIn("--body-file", self.workflow)

    def test_no_dependency_installation(self):
        self.assertNotIn("setup-uv", self.workflow)
        self.assertNotIn("uv sync", self.workflow)

    def test_pr_metadata_flows_only_as_data(self):
        self.assertRegex(self.workflow, re.compile(r"PR_TITLE", re.MULTILINE))
        self.assertRegex(self.workflow, re.compile(r"RUNNER_TEMP/pr-body\.md"))


if __name__ == "__main__":
    unittest.main()
