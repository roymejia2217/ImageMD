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


if __name__ == "__main__":
    unittest.main()
