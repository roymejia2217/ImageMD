import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
LOCK = ROOT / "uv.lock"
VERIFY = ROOT / ".github" / "workflows" / "verify.yml"


class QualityWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pyproject_text = PYPROJECT.read_text(encoding="utf-8")
        cls.pyproject = tomllib.loads(cls.pyproject_text)
        cls.lock_text = LOCK.read_text(encoding="utf-8")
        cls.workflow = VERIFY.read_text(encoding="utf-8")

    def test_ruff_is_pinned_in_the_development_dependency_group(self):
        development_dependencies = self.pyproject.get("dependency-groups", {}).get(
            "dev"
        )
        self.assertIsInstance(
            development_dependencies,
            list,
            "pyproject.toml must define a dependency-groups.dev list",
        )
        self.assertEqual(
            development_dependencies.count("ruff==0.14.14"),
            1,
            "the development group must contain exactly ruff==0.14.14",
        )

    def test_uv_lock_resolves_the_exact_ruff_version(self):
        package_match = re.search(
            r'(?ms)^\[\[package\]\]\nname = "ruff"\nversion = "([^"]+)"\n',
            self.lock_text,
        )
        self.assertIsNotNone(package_match, "uv.lock must contain a Ruff package entry")
        self.assertEqual(package_match.group(1), "0.14.14")

    def test_lint_commands_run_after_sync_and_before_the_build(self):
        sync_index = self.workflow.index("run: uv sync --locked")
        check_index = self.workflow.find("uv run ruff check .")
        format_index = self.workflow.find("uv run ruff format --check .")
        build_index = self.workflow.index("run: uv build --wheel")

        self.assertGreaterEqual(check_index, 0, "ruff check command is required")
        self.assertGreaterEqual(format_index, 0, "ruff format command is required")
        self.assertLess(sync_index, check_index)
        self.assertLess(sync_index, format_index)
        self.assertLess(check_index, build_index)
        self.assertLess(format_index, build_index)

    def test_lint_commands_are_exact_and_not_softened(self):
        self.assertEqual(
            re.findall(
                r"(?m)^\s+(uv run ruff (?:check \.|format --check \.))\s*$",
                self.workflow,
            ),
            ["uv run ruff check .", "uv run ruff format --check ."],
        )
        lint_start = self.workflow.index("uv run ruff check .")
        build_start = self.workflow.index("run: uv build --wheel")
        lint_section = self.workflow[lint_start:build_start]
        for forbidden in (
            "--ignore",
            "|| true",
            "continue-on-error",
            "ruff check . --",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lint_section)

    @staticmethod
    def _job_sections(workflow):
        jobs_start = re.search(r"(?m)^jobs:\s*$", workflow)
        if jobs_start is None:
            raise AssertionError("workflow must define jobs")
        jobs_workflow = workflow[jobs_start.end() :]
        matches = list(re.finditer(r"(?m)^  ([A-Za-z0-9-]+):\s*$", jobs_workflow))
        return {
            match.group(1): jobs_workflow[match.start() : matches[index + 1].start()]
            if index + 1 < len(matches)
            else jobs_workflow[match.start() :]
            for index, match in enumerate(matches)
        }

    def test_primary_job_key_is_quality(self):
        self.assertRegex(self.workflow, r"(?m)^  quality:\s*$")
        self.assertNotIn("test-and-build", self.workflow)

    def test_quality_job_display_name(self):
        sections = self._job_sections(self.workflow)
        self.assertIn("quality", sections)
        self.assertIn("name: Quality and tests", sections["quality"])

    def test_required_ci_aggregate_is_stable(self):
        sections = self._job_sections(self.workflow)
        self.assertIn("required-ci", sections)
        aggregate = sections["required-ci"]
        self.assertIn("name: Required CI", aggregate)
        self.assertRegex(aggregate, r"(?m)^    needs:\s*quality\s*$")
        self.assertRegex(aggregate, r"(?m)^\s+if:\s*\$\{\{\s*always\(\)\s*\}\}\s*$")
        self.assertIn("runs-on: ubuntu-24.04", aggregate)
        self.assertRegex(aggregate, r"(?m)^\s+timeout-minutes:\s*5\s*$")
        self.assertIn("contents: read", aggregate)
        self.assertIn("needs.quality.result", aggregate)

    def test_required_ci_aggregate_does_not_repeat_work(self):
        aggregate = self._job_sections(self.workflow)["required-ci"]
        for forbidden in (
            "uv sync",
            "uv run",
            "uv build",
            "ruff",
            "upload-artifact",
            "secrets.",
            "contents: write",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, aggregate)

    def test_quality_commands_are_preserved(self):
        for fragment in (
            "uv lock --check",
            "run: uv sync --locked",
            "uv run ruff check .",
            "uv run ruff format --check .",
            "uv audit --locked",
            "uv run python -m unittest discover -v",
            "run: uv build --wheel",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.workflow)
        self.assertRegex(self.workflow, r"(?m)^  pull_request:\s*$")
        self.assertRegex(self.workflow, r"(?m)^permissions:\n  contents: read\s*$")


class CommitGovernanceWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text(
            encoding="utf-8"
        )

    def test_checkout_has_full_history_for_commit_range(self):
        self.assertRegex(self.workflow, r"(?m)^\s+fetch-depth:\s*0\s*$")

    def test_checkout_does_not_persist_credentials(self):
        self.assertRegex(self.workflow, r"(?m)^\s+persist-credentials:\s*false\s*$")

    def test_commit_governance_step_is_pull_request_only(self):
        self.assertIn("Validate pull request commit subjects", self.workflow)
        match = re.search(
            r"(?ms)^\s*-\s*name:\s*Validate pull request commit subjects\s*\n"
            r"(?:[ ]+.*\n)*?\s+if:\s*(.+)\s*$",
            self.workflow,
        )
        # Fallback: locate the step block and inspect its condition.
        if match is None:
            step_index = self.workflow.index("Validate pull request commit subjects")
            window = self.workflow[max(0, step_index - 600) : step_index + 600]
            self.assertIn("github.event_name == 'pull_request'", window)
        else:
            self.assertIn("github.event_name == 'pull_request'", match.group(1))

    def test_commit_range_shas_come_from_event_env_values(self):
        self.assertIn("github.event.pull_request.base.sha", self.workflow)
        self.assertIn("github.event.pull_request.head.sha", self.workflow)
        self.assertIn("PR_BASE_SHA", self.workflow)
        self.assertIn("PR_HEAD_SHA", self.workflow)

    def test_commit_validator_invocation_is_exact(self):
        self.assertIn("python -m ci.governance commits", self.workflow)
        self.assertIn('--base "$PR_BASE_SHA"', self.workflow)
        self.assertIn('--head "$PR_HEAD_SHA"', self.workflow)
        step_index = self.workflow.index("Validate pull request commit subjects")
        run_index = self.workflow.index("python -m ci.governance commits")
        self.assertGreater(run_index, step_index)
        run_line = self.workflow[run_index : run_index + 200]
        self.assertNotIn("github.event.pull_request", run_line)

    def test_commit_governance_runs_before_dependency_installation(self):
        self.assertIn(
            "Validate pull request commit subjects",
            self.workflow,
            "verify.yml must define the commit-subjects governance step",
        )
        step_index = self.workflow.index("Validate pull request commit subjects")
        sync_index = self.workflow.index("run: uv sync --locked")
        self.assertLess(step_index, sync_index)

    def test_required_ci_remains_stable(self):
        self.assertRegex(self.workflow, r"(?m)^  required-ci:\s*$")
        self.assertIn("name: Required CI", self.workflow)
        self.assertIn("needs.quality.result", self.workflow)

    def test_push_to_main_behavior_remains_available(self):
        self.assertRegex(self.workflow, r"(?m)^  push:\s*$")
        self.assertIn("branches: [main]", self.workflow)


if __name__ == "__main__":
    unittest.main()
