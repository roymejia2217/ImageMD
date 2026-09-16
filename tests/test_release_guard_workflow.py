import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_GUARD = ROOT / ".github" / "workflows" / "release-guard.yml"
VERIFY = ROOT / ".github" / "workflows" / "verify.yml"


class ReleaseGuardWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = RELEASE_GUARD.read_text(encoding="utf-8")
        cls.verify_workflow = VERIFY.read_text(encoding="utf-8")

    def test_runs_only_for_version_tags_or_manual_dispatch(self):
        self.assertRegex(
            self.workflow,
            r"(?m)^on:\n  push:\n    tags:\n      - [\"']v\*[\"']\n  workflow_dispatch:\s*$",
        )

    def test_permissions_are_read_only(self):
        self.assertRegex(self.workflow, r"(?m)^permissions:\n  contents: read\s*$")

    def test_checkout_uses_triggering_ref(self):
        self.assertRegex(
            self.workflow,
            r"(?m)^\s+uses: actions/checkout@[0-9a-f]{40}[^\n]*\n\s+with:\n\s+ref: \$\{\{ github\.ref \}\}$",
        )

    def test_actions_match_verify_workflow_full_shas(self):
        action_pattern = re.compile(
            r"(?m)^\s+uses: ([^@\s]+)@([0-9a-f]{40})(?:\s+#.*)?$"
        )
        release_actions = action_pattern.findall(self.workflow)
        verify_actions = action_pattern.findall(self.verify_workflow)

        self.assertEqual(len(release_actions), 3)
        self.assertEqual(len(verify_actions), 3)
        self.assertEqual(set(release_actions), set(verify_actions))

    def test_workflow_has_no_release_or_secret_capabilities(self):
        forbidden = (
            "softprops/action-gh-release",
            "gh release",
            "create-release",
            "upload-release-asset",
            "contents: write",
            "id-token: write",
            "attestations: write",
            "secrets.",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, self.workflow)

    def test_each_run_block_enables_strict_shell_mode(self):
        lines = self.workflow.splitlines()
        scalar_runs = [line for line in lines if re.match(r"^\s+run:\s*[^|\s]", line)]
        self.assertEqual(
            scalar_runs,
            [],
            "every run step must use a block beginning with set -eu",
        )
        run_blocks = []
        index = 0
        while index < len(lines):
            match = re.match(r"^(\s*)run:\s*\|\s*$", lines[index])
            if not match:
                index += 1
                continue

            indentation = len(match.group(1))
            commands = []
            index += 1
            while index < len(lines):
                line = lines[index]
                if line.strip() and len(line) - len(line.lstrip()) <= indentation:
                    break
                if line.strip():
                    commands.append(line.strip())
                index += 1
            run_blocks.append(commands)

        self.assertTrue(run_blocks, "expected at least one run block")
        for commands in run_blocks:
            with self.subTest(commands=commands):
                self.assertTrue(commands, "run block must not be empty")
                self.assertEqual(commands[0], "set -eu")


if __name__ == "__main__":
    unittest.main()
