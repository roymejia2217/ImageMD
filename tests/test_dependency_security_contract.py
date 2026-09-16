import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
REQUIREMENTS = ROOT / "requirements.txt"
LOCK = ROOT / "uv.lock"
VERIFY_WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"


class DependencySecurityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pyproject = PYPROJECT.read_text(encoding="utf-8")
        cls.requirements = REQUIREMENTS.read_text(encoding="utf-8")
        cls.lock = LOCK.read_text(encoding="utf-8")
        cls.verify_workflow = VERIFY_WORKFLOW.read_text(encoding="utf-8")

    def test_pyproject_pins_pillow_to_12_3_0(self):
        self.assertEqual(
            re.findall(r'^\s*"Pillow==[^"\n]+",?\s*$', self.pyproject, re.MULTILINE),
            ['    "Pillow==12.3.0",'],
        )

    def test_requirements_pins_pillow_to_12_3_0(self):
        self.assertEqual(
            re.findall(r"^Pillow==[^\n]+$", self.requirements, re.MULTILINE),
            ["Pillow==12.3.0"],
        )

    def test_pyproject_pins_ttkbootstrap_to_1_20_4(self):
        self.assertEqual(
            re.findall(
                r'^\s*"ttkbootstrap==[^"\n]+",?\s*$', self.pyproject, re.MULTILINE
            ),
            ['    "ttkbootstrap==1.20.4",'],
        )

    def test_requirements_pins_ttkbootstrap_to_1_20_4(self):
        self.assertEqual(
            re.findall(r"^ttkbootstrap==[^\n]+$", self.requirements, re.MULTILINE),
            ["ttkbootstrap==1.20.4"],
        )

    def test_lock_resolves_only_pillow_12_3_0(self):
        pillow_package = re.search(
            r'(?ms)^\[\[package\]\]\nname = "pillow"\n.*?(?=^\[\[package\]\]|\Z)',
            self.lock,
        )
        self.assertIsNotNone(pillow_package)
        self.assertIn('version = "12.3.0"', pillow_package.group(0))
        self.assertIn('specifier = "==12.3.0"', self.lock)
        self.assertNotIn("12.0.0", pillow_package.group(0))
        self.assertNotIn('specifier = "==12.0.0"', self.lock)

    def test_lock_resolves_only_ttkbootstrap_1_20_4(self):
        ttkbootstrap_package = re.search(
            r'(?ms)^\[\[package\]\]\nname = "ttkbootstrap"\n.*?(?=^\[\[package\]\]|\Z)',
            self.lock,
        )
        self.assertIsNotNone(ttkbootstrap_package)
        self.assertIn('version = "1.20.4"', ttkbootstrap_package.group(0))
        self.assertIn('specifier = "==1.20.4"', self.lock)
        self.assertNotIn("1.19.0", ttkbootstrap_package.group(0))
        self.assertNotIn('specifier = "==1.19.0"', self.lock)

    def test_verify_audits_locked_dependencies_on_python_312_linux_x64(self):
        workflow = self.verify_workflow
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertRegex(workflow, r'(?m)^\s+python-version:\s*["\']3\.12["\']\s*$')
        self.assertRegex(workflow, r'(?m)^\s+architecture:\s*["\']x64["\']\s*$')
        lock_index = workflow.index("uv lock --check")
        sync_index = workflow.index("uv sync --locked")
        audit_index = workflow.index("uv audit --locked")
        self.assertLess(lock_index, sync_index)
        self.assertLess(sync_index, audit_index)
        for forbidden in ("--ignore", "|| true", "continue-on-error:"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, workflow)


if __name__ == "__main__":
    unittest.main()
