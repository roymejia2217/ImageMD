import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / ".github" / "workflows" / "package.yml"

CHECKOUT_SHA = "11bd71901bbe5b1630ceea73d27597364c9af683"
DOWNLOAD_SHA = "d3f86a106a0bac45b974a628896c90dbdf5c8093"
UPLOAD_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"
ATTEST_SHA = "508db95dd578ae2727ebd6217d5ba78e4fbda05d"
PACKAGE_JOBS = ("deb", "rpm", "arch", "appimage", "flatpak")
PACKAGE_OUTPUTS = {job: f"imagemd-{job}" for job in PACKAGE_JOBS}


class PackageWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = PACKAGE.read_text(encoding="utf-8")
        cls.jobs = cls._job_sections(cls.workflow)
        cls.run_blocks = cls._run_blocks(cls.workflow)

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

    @staticmethod
    def _run_blocks(workflow):
        lines = workflow.splitlines()
        blocks = []
        for index, line in enumerate(lines):
            match = re.match(r"^(\s*)run:\s*(.*)$", line)
            if not match:
                continue
            indent = len(match.group(1))
            if match.group(2) != "|":
                raise AssertionError("every run must use a block scalar")
            commands = []
            for body in lines[index + 1 :]:
                if body.strip() and len(body) - len(body.lstrip()) <= indent:
                    break
                if body.strip():
                    commands.append(body.strip())
            blocks.append(commands)
        return blocks

    def test_release_trigger_and_global_permissions_are_minimal(self):
        self.assertRegex(
            self.workflow,
            r'(?m)^on:\n  push:\n    tags:\n      - "v\*"\n  workflow_dispatch:',
        )
        self.assertRegex(
            self.workflow,
            r"(?ms)^  workflow_dispatch:\n    inputs:\n      source_ref:\n"
            r"        description: .+\n        required: true\n        type: string$",
        )
        self.assertIn(
            "PACKAGE_REF: ${{ github.event_name == 'workflow_dispatch' && inputs.source_ref || github.ref }}",
            self.workflow,
        )
        permissions = re.search(r"(?ms)^permissions:\n((?:  [^\n]+\n)+)", self.workflow)
        self.assertIsNotNone(permissions)
        self.assertEqual(
            re.findall(r"(?m)^  ([\w-]+):\s*(\w+)\s*$", permissions.group(1)),
            [("contents", "read")],
        )

    def test_all_run_blocks_are_strict_shell_block_scalars(self):
        self.assertTrue(self.run_blocks)
        self.assertNotRegex(self.workflow, r"(?m)^\s+run:\s+[^|\s]")
        for commands in self.run_blocks:
            self.assertEqual(commands[0], "set -eu")

    def test_job_graph_is_explicit_and_isolated(self):
        expected = {
            "release-gate": None,
            "bundle-stage": ["release-gate"],
            **{job: ["bundle-stage"] for job in PACKAGE_JOBS},
            "assemble-candidate": ["bundle-stage", *PACKAGE_JOBS],
        }
        self.assertEqual(set(self.jobs), set(expected))
        for job, needs in expected.items():
            match = re.search(r"(?m)^    needs:\s*(.+)$", self.jobs[job])
            if needs is None:
                self.assertIsNone(match)
                continue
            self.assertIsNotNone(match)
            self.assertEqual(re.findall(r"[A-Za-z0-9-]+", match.group(1)), needs)

    def test_stage_contract_is_immutable_and_format_jobs_download_it(self):
        stage = self.jobs["bundle-stage"]
        self.assertIn("name: imagemd-package-stage", stage)
        self.assertNotRegex(stage, r"packaging/(?:debian|rpm|arch|appimage|flatpak)/")
        for job in PACKAGE_JOBS:
            section = self.jobs[job]
            self.assertIn(f"uses: actions/checkout@{CHECKOUT_SHA}", section)
            self.assertIn("ref: ${{ env.PACKAGE_REF }}", section)
            self.assertIn(f"uses: actions/download-artifact@{DOWNLOAD_SHA}", section)
            self.assertRegex(
                section, r"name: imagemd-package-stage\s+path: artifacts/stage"
            )

    def test_each_format_owns_only_its_named_output_and_builder(self):
        builders = {
            "deb": ("packaging/debian/", "build_deb.py"),
            "rpm": ("packaging/rpm/", "build_rpm.py", "Dockerfile.rpm"),
            "arch": ("packaging/arch/", "build_arch.py", "Dockerfile.arch"),
            "appimage": (
                "packaging/appimage/",
                "appimagetool",
                "Dockerfile.appimage-runtime",
            ),
            "flatpak": ("packaging/flatpak/", "flatpak-builder", "build-bundle"),
        }
        for job, output in PACKAGE_OUTPUTS.items():
            section = self.jobs[job]
            self.assertIn(f"name: {output}", section)
            for other in PACKAGE_OUTPUTS.values():
                if other != output:
                    self.assertNotIn(f"name: {other}", section)
            for other_job, other_builders in builders.items():
                if other_job != job:
                    for builder in other_builders:
                        self.assertNotIn(builder, section)

    def test_arch_ownership_is_scoped_to_arch_output(self):
        section = self.jobs["arch"]
        self.assertIn("/artifacts/arch", section)
        self.assertIn("chown builder:builder /artifacts/arch", section)
        self.assertNotRegex(
            section, r"chown\s+builder:builder\s+/artifacts(?:\s|['\";&]|$)"
        )
        self.assertNotRegex(section, r"(?i)(restore|sudo chown|ownership.*artifacts)")

    def test_flatpak_uses_user_scoped_lifecycle_everywhere(self):
        section = self.jobs["flatpak"]
        for fragment in (
            "flatpak --user remote-add",
            "flatpak --user update --appstream",
            "flatpak --user install",
            "flatpak-builder --user",
            "flatpak --user build-bundle",
            "flatpak --user run",
        ):
            self.assertIn(fragment, section)
        self.assertNotRegex(section, r"sudo\s+flatpak")
        self.assertNotRegex(section, r"(?m)^\s*flatpak-builder\s+(?!--user\b)")

    def test_aggregate_has_exact_privileges_and_only_assembles(self):
        section = self.jobs["assemble-candidate"]
        permissions = re.search(
            r"(?ms)^    permissions:\n((?:      [^\n]+\n)+)", section
        )
        self.assertIsNotNone(permissions)
        self.assertEqual(
            re.findall(r"(?m)^      ([\w-]+):\s*(\w+)\s*$", permissions.group(1)),
            [
                ("contents", "read"),
                ("id-token", "write"),
                ("attestations", "write"),
                ("artifact-metadata", "write"),
            ],
        )
        for output in PACKAGE_OUTPUTS.values():
            self.assertRegex(section, rf"name: {output}\s+path: artifacts/release")
        self.assertIn("-eq 5", section)
        self.assertIn(
            "https://github.com/anchore/syft/releases/download/v1.51.1/syft_1.51.1_linux_amd64.tar.gz",
            section,
        )
        self.assertIn(
            "8fcb33017a0dc1058298c923c436d19dfa68ae93968e0b423248542e3afb9fc3", section
        )
        self.assertIn("python packaging/write_checksums.py", section)
        self.assertEqual(section.count("uses: actions/attest@"), 2)
        self.assertIn("retention-days: 14", section)
        self.assertNotRegex(section, r"packaging/(?:debian|rpm|arch|appimage|flatpak)/")

    def test_actions_are_pinned_and_capabilities_are_forbidden(self):
        expected = {
            "actions/checkout": CHECKOUT_SHA,
            "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
            "astral-sh/setup-uv": "2ddd2b9cb38ad8efd50337e8ab201519a34c9f24",
            "actions/download-artifact": DOWNLOAD_SHA,
            "actions/upload-artifact": UPLOAD_SHA,
            "actions/attest": ATTEST_SHA,
        }
        uses = re.findall(r"(?m)^\s+uses:\s+([^@\s]+)@([^\s#]+)", self.workflow)
        self.assertTrue(uses)
        self.assertEqual({name for name, _ in uses}, set(expected))
        for name, sha in uses:
            self.assertEqual(sha, expected[name])
        for token in (
            "softprops/action-gh-release",
            "gh release",
            "secrets.",
            "contents: write",
            "--privileged",
            "continue-on-error",
            "@latest",
            "@main",
            "@master",
        ):
            self.assertNotIn(token, self.workflow)

    def test_reproducible_pyinstaller_contract_is_preserved(self):
        section = self.jobs["bundle-stage"]
        self.assertEqual(section.count("--env PYTHONHASHSEED=1"), 2)
        self.assertEqual(section.count("--env SOURCE_DATE_EPOCH"), 2)
        self.assertIn("artifacts/reproducibility-bundle", section)
        self.assertIn(
            "cmp --silent artifacts/bundle/ImageMD artifacts/reproducibility-bundle/ImageMD",
            section,
        )

    def test_deb_rpm_arch_install_and_quality_contracts_are_present(self):
        deb = self.jobs["deb"]
        for fragment in (
            "dpkg-deb --info",
            "dpkg -i",
            "test -x /usr/bin/imagemd",
            "dpkg --purge imagemd",
        ):
            self.assertIn(fragment, deb)
        rpm = self.jobs["rpm"]
        self.assertIn("rpmlint artifacts/rpm/*.x86_64.rpm", rpm)
        self.assertRegex(rpm, r"grep\s+-Eq\s+['\"]?: \[EW\]:")
        for fragment in (
            "dnf --assumeyes install",
            "rpm --verify imagemd",
            "dnf --assumeyes remove imagemd",
        ):
            self.assertIn(fragment, rpm)
        arch = self.jobs["arch"]
        for fragment in (
            "makepkg --noconfirm --syncdeps --cleanbuild",
            "namcap ./*.pkg.tar.zst",
            "pacman --noconfirm -U",
            "pacman --noconfirm -R imagemd",
        ):
            self.assertIn(fragment, arch)
        self.assertIn(
            "imagemd W: Dependency included, but may not be needed ('ffmpeg')", arch
        )

    def test_appimage_and_flatpak_runtime_smoke_contracts_are_present(self):
        appimage = self.jobs["appimage"]
        self.assertGreaterEqual(appimage.count("sha256sum --check --strict"), 2)
        for fragment in (
            "--appimage-offset",
            "timeout 10 xvfb-run -a artifacts/ImageMD-x86_64.AppImage",
            'test "$status" -eq 124',
        ):
            self.assertIn(fragment, appimage)
        flatpak = self.jobs["flatpak"]
        for fragment in (
            "test -x /app/bin/ffmpeg",
            "test -x /app/bin/ffprobe",
            "timeout 10 xvfb-run -a flatpak --user run org.roymejia.ImageMD",
            'test "$status" -eq 124',
        ):
            self.assertIn(fragment, flatpak)


if __name__ == "__main__":
    unittest.main()
