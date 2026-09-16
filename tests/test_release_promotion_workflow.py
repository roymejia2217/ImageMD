import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "promote-release.yml"


class ReleasePromotionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_is_manual_only_and_requires_promotion_inputs(self):
        self.assertRegex(
            self.workflow,
            r"(?m)^on:\n  workflow_dispatch:\n    inputs:\n",
        )
        self.assertNotRegex(self.workflow, r"(?m)^  (push|pull_request|schedule):")
        for input_name in ("tag", "candidate_run_id"):
            with self.subTest(input_name=input_name):
                input_block = re.search(
                    rf"(?ms)^      {input_name}:\n(.*?)(?=^      \w+:|^jobs:)",
                    self.workflow,
                )
                self.assertIsNotNone(input_block)
                self.assertRegex(
                    input_block.group(1), r"(?m)^        required:\s*true\s*$"
                )

    def test_permissions_are_exactly_for_release_and_artifact_read(self):
        permissions = re.search(r"(?ms)^permissions:\n((?:  [^\n]+\n)+)", self.workflow)
        self.assertIsNotNone(permissions)
        values = dict(
            re.findall(r"(?m)^  ([\w-]+):\s*(read|write)\s*$", permissions.group(1))
        )
        self.assertEqual(
            values,
            {
                "contents": "write",
                "actions": "read",
                "attestations": "read",
            },
        )

    def test_release_job_uses_production_environment(self):
        self.assertRegex(
            self.workflow,
            r"(?m)^  [\w-]+:\n(?:.*\n)*?    environment:\s*production-release\s*$",
        )

    def test_candidate_is_checked_out_and_downloaded_with_pinned_actions(self):
        self.assertIn(
            "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
            self.workflow,
        )
        self.assertIn(
            "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
            self.workflow,
        )
        download_index = self.workflow.index(
            "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
        )
        download_step = self.workflow[
            download_index : self.workflow.index("\n      - name:", download_index)
        ]
        self.assertRegex(
            download_step,
            r"(?m)^\s+github-token:\s*\$\{\{\s*github\.token\s*\}\}\s*$",
        )
        self.assertRegex(
            download_step,
            r"(?m)^\s+repository:\s*\$\{\{\s*github\.repository\s*\}\}\s*$",
        )
        self.assertRegex(
            download_step,
            r"(?ms)actions/download-artifact@[0-9a-f]{40}.*?\n\s+with:\n"
            r"\s+name:\s*imagemd-release-candidate\s*\n"
            r"\s+run-id:\s*\$\{\{\s*inputs\.candidate_run_id\s*\}\}\s*\n"
            r"\s+path:\s*release\s*$",
        )

    def test_every_run_block_starts_with_strict_shell_mode(self):
        lines = self.workflow.splitlines()
        run_blocks = []
        index = 0
        while index < len(lines):
            match = re.match(r"^(\s*)run:\s*\|\s*$", lines[index])
            if not match:
                self.assertFalse(
                    re.match(r"^\s+run:\s*[^|\s]", lines[index]),
                    "run commands must use block scalars",
                )
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
                self.assertTrue(commands)
                self.assertEqual(commands[0], "set -eu")

    def test_tag_is_checked_against_the_package_version(self):
        self.assertIn("inputs.tag", self.workflow)
        self.assertRegex(self.workflow, r"src(?:\.__version__| import __version__)")
        self.assertRegex(self.workflow, r"v.*__version__|__version__.*v")
        self.assertRegex(
            self.workflow,
            r"(?i)(test|if|case|assert|\[).*inputs\.tag.*(expected|version|==|=~)",
        )

    def test_release_contents_are_validated_before_the_single_release_action(self):
        release_action = (
            "softprops/action-gh-release@da05d552573ad5aba039eaac05058a918a7bf631"
        )
        self.assertEqual(self.workflow.count(release_action), 1)
        self.assertIn('sha256sum --check "$checksums_name"', self.workflow)
        self.assertIn(
            'python packaging/release_assets.py --version "$release_version" --name metadata',
            self.workflow,
        )
        for artifact in ("*.deb", "*.rpm", "*.pkg.tar.zst", "*.AppImage", "*.flatpak"):
            with self.subTest(artifact=artifact):
                self.assertIn(artifact, self.workflow)
        self.assertRegex(self.workflow, r"(?i)spdx")
        self.assertRegex(self.workflow, r"(?i)\.spdx\.json")
        self.assertRegex(self.workflow, r"(?m)(exactly|eq|==|\-eq)\s*5")

        validation_end = max(
            self.workflow.index('sha256sum --check "$checksums_name"'),
            self.workflow.lower().index("spdx"),
        )
        self.assertGreater(self.workflow.index(release_action), validation_end)

    def test_candidate_metadata_version_is_checked_before_release(self):
        release_action = (
            "softprops/action-gh-release@da05d552573ad5aba039eaac05058a918a7bf631"
        )
        release_index = self.workflow.index(release_action)
        validation = self.workflow[:release_index]
        self.assertRegex(validation, r"(?m)^\s+cd release\s*$")
        self.assertIn('test -f "$metadata_name"', validation)
        self.assertNotIn("ImageMD-release-metadata.json", validation)
        self.assertIn('test -f "$sbom_name"', validation)
        self.assertRegex(validation, r"(?s)python\b.*?import json")
        self.assertRegex(
            validation,
            r"(?s)json\.load.*?\[\s*[\"']version[\"']\s*\]",
        )
        self.assertRegex(validation, r"candidate_version")
        self.assertRegex(
            validation,
            r"(?s)test\s+[\"\']v\$\{candidate_version\}[\"\']\s*=\s+[\"\']\$\{\{\s*inputs\.tag\s*\}\}[\"\']",
        )

    def test_candidate_checksum_precedes_metadata_read_and_validation(self):
        release_action = (
            "softprops/action-gh-release@da05d552573ad5aba039eaac05058a918a7bf631"
        )
        validation_start = self.workflow.index(
            "- name: Validate the release candidate contents"
        )
        release_index = self.workflow.index(release_action)
        validation = self.workflow[validation_start:release_index]

        entered_release = validation.index("cd release")
        checksum = validation.index('sha256sum --check "$checksums_name"')
        metadata = validation.index("candidate_version=")
        self.assertLess(entered_release, checksum)
        self.assertLess(
            checksum,
            metadata,
            "candidate metadata must be read only after its checksum is verified",
        )

    def test_artifact_attestations_are_verified_before_release(self):
        release_action = (
            "softprops/action-gh-release@da05d552573ad5aba039eaac05058a918a7bf631"
        )
        release_index = self.workflow.index(release_action)
        attestation = re.search(
            r"(?ms)^      - name: Verify release artifact attestations\n"
            r"(.*?)(?=^      - name:|\Z)",
            self.workflow,
        )
        self.assertIsNotNone(
            attestation,
            "promotion must have a dedicated attestation-verification step",
        )
        attestation_start = attestation.start()
        attestation_end = attestation.end()
        attestation_step = attestation.group(0)

        self.assertLess(attestation_start, release_index)
        self.assertIn("gh attestation verify", attestation_step)
        for option in (
            "--repo ${{ github.repository }}",
            "--signer-workflow ${{ github.repository }}/.github/workflows/package.yml",
            "--source-ref refs/tags/${{ inputs.tag }}",
            "--deny-self-hosted-runners",
        ):
            with self.subTest(option=option):
                self.assertIn(option, attestation_step)
        for artifact in ("*.deb", "*.rpm", "*.pkg.tar.zst", "*.AppImage", "*.flatpak"):
            with self.subTest(artifact=artifact):
                self.assertIn(artifact, attestation_step)

        self.assertRegex(
            attestation_step,
            r"(?m)^\s+GH_TOKEN:\s*\$\{\{\s*github\.token\s*\}\}\s*$",
        )
        self.assertEqual(
            len(re.findall(r"(?m)^\s+GH_TOKEN:\s*", attestation_step)),
            1,
        )
        outside_attestation = (
            self.workflow[:attestation_start] + self.workflow[attestation_end:]
        )
        self.assertNotIn("GH_TOKEN:", outside_attestation)

        checksum_index = self.workflow.index('sha256sum --check "$checksums_name"')
        package_count_matches = list(
            re.finditer(r"(?i)(?:exactly|eq|==)\s*5|\-eq\s*5", self.workflow)
        )
        self.assertTrue(
            package_count_matches, "exactly five package formats must be counted"
        )
        package_count_index = max(match.start() for match in package_count_matches)
        self.assertGreater(attestation_start, checksum_index)
        self.assertGreater(attestation_start, package_count_index)

    def test_release_action_uses_the_input_tag_and_candidate_files(self):
        release_index = self.workflow.index(
            "softprops/action-gh-release@da05d552573ad5aba039eaac05058a918a7bf631"
        )
        release_step = self.workflow[release_index:]
        self.assertRegex(
            release_step, r"(?m)^\s+tag_name:\s*\$\{\{\s*inputs\.tag\s*\}\}\s*$"
        )
        self.assertRegex(release_step, r"(?m)^\s+files:\s*release/\*\s*$")
        self.assertRegex(release_step, r"(?m)^\s+fail_on_unmatched_files:\s*true\s*$")
        self.assertRegex(release_step, r"(?m)^\s+draft:\s*false\s*$")
        self.assertRegex(release_step, r"(?m)^\s+prerelease:\s*false\s*$")

    def test_workflow_has_no_unapproved_build_or_mutable_release_capabilities(self):
        forbidden = (
            "docker",
            "flatpak-builder",
            "makepkg",
            "syft",
            "gh release",
            "secrets.",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, self.workflow.lower())
        action_refs = re.findall(r"(?m)^\s+uses:\s+[^@\s]+@([^\s]+)", self.workflow)
        self.assertTrue(action_refs)
        for ref in action_refs:
            with self.subTest(ref=ref):
                self.assertRegex(ref, r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
