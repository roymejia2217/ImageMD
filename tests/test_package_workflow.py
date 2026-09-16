import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / ".github" / "workflows" / "package.yml"
VERIFY = ROOT / ".github" / "workflows" / "verify.yml"
DEBIAN_IMAGE = (
    "debian@sha256:6ebd97fa83deb272194a2cf015b3d26a4d538e9ad3a7a79d544c8af5b0a01443"
)
FEDORA_IMAGE = (
    "fedora:42@sha256:99e203b80b1c3d8f7e161ec10a68fd02b081ef83a3963553e513c82846b97814"
)
ARCH_DOCKERFILE = ROOT / "packaging" / "container" / "Dockerfile.arch"


class PackageWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = PACKAGE.read_text(encoding="utf-8")
        cls.verify_workflow = VERIFY.read_text(encoding="utf-8")
        cls.arch_dockerfile = ARCH_DOCKERFILE.read_text(encoding="utf-8")

    def test_runs_for_version_tags_or_manual_dispatch(self):
        self.assertRegex(
            self.workflow,
            r"(?m)^on:\n  push:\n    tags:\n      - [\"']v\*[\"']\n  workflow_dispatch:\s*$",
        )

    def test_permissions_are_exactly_the_attestation_permissions(self):
        permissions_match = re.search(
            r"(?ms)^permissions:\n((?:  [^\n]+\n)+)", self.workflow
        )
        self.assertIsNotNone(permissions_match)
        permissions = dict(
            re.findall(
                r"(?m)^  ([\w-]+):\s*(read|write)\s*$", permissions_match.group(1)
            )
        )
        self.assertEqual(
            permissions,
            {
                "contents": "read",
                "id-token": "write",
                "attestations": "write",
                "artifact-metadata": "write",
            },
        )

    def test_actions_use_exactly_the_verify_workflow_shas(self):
        action_pattern = re.compile(
            r"(?m)^\s+uses: ([^@\s]+)@([0-9a-f]{40})(?:\s+#.*)?$"
        )
        bootstrap_actions = {
            "actions/checkout",
            "actions/setup-python",
            "astral-sh/setup-uv",
        }
        package_actions = [
            action
            for action in action_pattern.findall(self.workflow)
            if action[0] in bootstrap_actions
        ]
        verify_actions = [
            action
            for action in action_pattern.findall(self.verify_workflow)
            if action[0] in bootstrap_actions
        ]

        self.assertEqual(len(package_actions), 3)
        self.assertEqual(len(verify_actions), 3)
        self.assertEqual(package_actions, verify_actions)

    def test_workflow_has_no_forbidden_capabilities(self):
        forbidden = (
            "secrets.",
            "softprops/action-gh-release",
            "gh release",
            "--privileged",
            "contents: write",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, self.workflow)

    def test_each_run_block_starts_in_strict_shell_mode(self):
        lines = self.workflow.splitlines()
        run_blocks = []

        for index, line in enumerate(lines):
            match = re.match(r"^(\s*)run:\s*(.*)$", line)
            if not match:
                continue

            self.assertEqual(match.group(2), "|", "run commands must use block scalars")
            indentation = len(match.group(1))
            commands = []
            for body_line in lines[index + 1 :]:
                if (
                    body_line.strip()
                    and len(body_line) - len(body_line.lstrip()) <= indentation
                ):
                    break
                if body_line.strip():
                    commands.append(body_line.strip())
            run_blocks.append(commands)

        self.assertTrue(run_blocks, "expected at least one run block")
        for commands in run_blocks:
            with self.subTest(commands=commands):
                self.assertTrue(commands, "run block must not be empty")
                self.assertEqual(commands[0], "set -eu")

    def test_debian_package_is_inspected_and_installed_in_pinned_image(self):
        required = (
            DEBIAN_IMAGE,
            '"$PWD/artifacts:/artifacts:ro"',
            "dpkg-deb --info artifacts/imagemd.deb",
            "dpkg-deb --contents artifacts/imagemd.deb",
            "dpkg -i /artifacts/imagemd.deb",
            "test -x /usr/bin/imagemd",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.workflow)

    def test_release_artifacts_are_promoted_before_checksums(self):
        required = (
            "mkdir -p artifacts/release",
            "cp artifacts/imagemd.deb artifacts/release/",
            "cp artifacts/rpm/*.x86_64.rpm artifacts/release/",
            "cp artifacts/arch/*.pkg.tar.zst artifacts/release/",
            "cp artifacts/ImageMD-x86_64.AppImage artifacts/release/",
            "cp artifacts/ImageMD.flatpak artifacts/release/",
            "cp artifacts/stage/release-metadata.json artifacts/release/ImageMD-release-metadata.json",
            "artifacts/release",
            "-eq 5",
            "https://github.com/anchore/syft/releases/download/v1.51.1/syft_1.51.1_linux_amd64.tar.gz",
            "8fcb33017a0dc1058298c923c436d19dfa68ae93968e0b423248542e3afb9fc3",
            "sha256sum",
            "syft",
            "dir:artifacts/release",
            "spdx-json",
            ".spdx.json",
            "python packaging/write_checksums.py --artifacts artifacts/release --output artifacts/release/SHA256SUMS",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.workflow)
        self.assertNotIn("artifacts/bundle/SHA256SUMS", self.workflow)
        promotion_index = self.workflow.index("mkdir -p artifacts/release")
        checksum_index = self.workflow.index(
            "python packaging/write_checksums.py --artifacts artifacts/release"
        )
        self.assertLess(promotion_index, checksum_index)
        promotion = self.workflow[promotion_index:checksum_index]
        promotion_flat = re.sub(r"\\\s*\n\s*", " ", promotion)
        self.assertRegex(
            promotion_flat,
            r"find\s+artifacts/release\b.*?-name\s+'\*\.deb'.*?-name\s+'\*\.rpm'.*?-name\s+'\*\.pkg\.tar\.zst'.*?-name\s+'\*\.AppImage'.*?-name\s+'\*\.flatpak'.*?\|\s*wc\s+-l\)?\"?\s*-eq\s+5",
        )
        metadata_index = promotion.find(
            "cp artifacts/stage/release-metadata.json artifacts/release/ImageMD-release-metadata.json"
        )
        self.assertGreaterEqual(metadata_index, 0, "release metadata must be promoted")
        metadata_index += promotion_index
        syft_run_index = self.workflow.index(
            "artifacts/tools/syft dir:artifacts/release", metadata_index
        )
        sbom_index = self.workflow.index(
            "--output spdx-json=artifacts/release/ImageMD.spdx.json", syft_run_index
        )
        attest_index = self.workflow.index("uses: actions/attest@", checksum_index)
        upload_index = self.workflow.index(
            "uses: actions/upload-artifact@", attest_index
        )
        self.assertLess(metadata_index, syft_run_index)
        self.assertLess(syft_run_index, sbom_index)
        self.assertLess(sbom_index, checksum_index)
        self.assertLess(checksum_index, attest_index)
        self.assertLess(attest_index, upload_index)
        self.assertIn("subject-path: artifacts/release/*", self.workflow[attest_index:])
        self.assertIn("path: artifacts/release", self.workflow[upload_index:])
        syft_url = self.workflow.find(
            "https://github.com/anchore/syft/releases/download/v1.51.1/syft_1.51.1_linux_amd64.tar.gz"
        )
        self.assertGreaterEqual(syft_url, 0, "Syft download URL is required")
        if syft_url < 0:
            return
        syft_hash = self.workflow.find(
            "8fcb33017a0dc1058298c923c436d19dfa68ae93968e0b423248542e3afb9fc3",
            syft_url,
        )
        self.assertGreaterEqual(syft_hash, 0, "Syft checksum is required")
        if syft_hash < 0:
            return
        syft_verify = self.workflow.find("sha256sum", syft_hash)
        syft_extract = self.workflow.find("tar -x", syft_verify)
        syft_run = self.workflow.find("dir:artifacts/release", syft_extract)
        self.assertGreaterEqual(
            syft_verify, 0, "Syft checksum verification is required"
        )
        self.assertGreaterEqual(syft_extract, 0, "Syft archive extraction is required")
        self.assertGreaterEqual(syft_run, 0, "Syft invocation is required")
        self.assertLess(syft_url, syft_hash)
        self.assertLess(syft_hash, syft_verify)
        self.assertLess(syft_verify, syft_extract)
        self.assertLess(syft_extract, syft_run)
        self.assertLess(syft_run, checksum_index)
        syft_section = self.workflow[syft_url:checksum_index]
        for token in (
            "latest",
            "continuous",
            "secrets.",
            "upload-artifact",
            "docker push",
            "curl |",
            "wget |",
        ):
            with self.subTest(syft_forbidden=token):
                self.assertNotIn(token, syft_section)

    def test_attestations_are_pinned_and_separate_provenance_from_sbom(self):
        attest_pattern = re.compile(
            r"(?m)^\s+uses: actions/attest@([0-9a-f]{40})(?:\s+#.*)?$"
        )
        attestations = attest_pattern.findall(self.workflow)
        self.assertEqual(
            attestations,
            [
                "508db95dd578ae2727ebd6217d5ba78e4fbda05d",
                "508db95dd578ae2727ebd6217d5ba78e4fbda05d",
            ],
        )
        self.assertNotRegex(
            self.workflow, r"(?m)^\s+uses: actions/attest@(?![0-9a-f]{40})"
        )
        sbom_index = self.workflow.find("artifacts/release/ImageMD.spdx.json")
        checksums_index = self.workflow.find(
            "python packaging/write_checksums.py --artifacts artifacts/release"
        )
        attest_indexes = [
            match.start()
            for match in re.finditer(r"uses: actions/attest@", self.workflow)
        ]
        self.assertEqual(len(attest_indexes), 2)
        first_attest_index, second_attest_index = attest_indexes
        self.assertGreaterEqual(sbom_index, 0)
        self.assertGreaterEqual(checksums_index, 0)
        self.assertLess(sbom_index, first_attest_index)
        self.assertLess(checksums_index, first_attest_index)
        self.assertLess(first_attest_index, second_attest_index)
        upload_index = self.workflow.find(
            "uses: actions/upload-artifact@", second_attest_index
        )
        self.assertGreaterEqual(upload_index, 0)
        self.assertLess(second_attest_index, upload_index)

        first_attest_step = self.workflow[first_attest_index:second_attest_index]
        second_attest_step = self.workflow[second_attest_index:upload_index]
        for attest_step in (first_attest_step, second_attest_step):
            subject_line = re.search(r"(?m)^\s+subject-path:\s*([^\n]+)$", attest_step)
            self.assertIsNotNone(subject_line)
            self.assertIn("artifacts/release/*", subject_line.group(1))
            self.assertNotIn("workspace", subject_line.group(1))
        self.assertNotIn("sbom-path:", first_attest_step)
        self.assertIn(
            "sbom-path: artifacts/release/ImageMD.spdx.json", second_attest_step
        )
        for token in ("softprops/action-gh-release", "gh release", "secrets."):
            with self.subTest(forbidden=token):
                self.assertNotIn(token, first_attest_step)
                self.assertNotIn(token, second_attest_step)

    def test_release_candidate_upload_is_pinned_and_follows_attestation(self):
        upload_pattern = re.compile(
            r"(?m)^\s+uses: actions/upload-artifact@([^\s]+)(?:\s+#.*)?$"
        )
        uploads = upload_pattern.findall(self.workflow)
        self.assertEqual(uploads, ["ea165f8d65b6e75b540449e92b4886f43607fa02"])
        self.assertNotRegex(
            self.workflow,
            r"(?m)^\s+uses: actions/upload-artifact@(?!ea165f8d65b6e75b540449e92b4886f43607fa02(?:\s|$))",
        )
        attest_index = self.workflow.find("uses: actions/attest@")
        upload_index = self.workflow.find("uses: actions/upload-artifact@")
        self.assertGreaterEqual(attest_index, 0)
        self.assertGreaterEqual(upload_index, 0)
        self.assertLess(attest_index, upload_index)
        upload_step = self.workflow[upload_index:]
        for fragment in (
            "name: imagemd-release-candidate",
            "path: artifacts/release",
            "if-no-files-found: error",
            "retention-days: 14",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, upload_step)
        for token in (
            "softprops/action-gh-release",
            "gh release",
            "secrets.",
            "contents: write",
        ):
            with self.subTest(forbidden=token):
                self.assertNotIn(token, upload_step)

    def test_rpm_builder_uses_the_pinned_dockerfile_and_build_command(self):
        required = (
            "--file packaging/container/Dockerfile.rpm",
            "--tag imagemd-rpm-builder:ci",
            "python packaging/rpm/build_rpm.py",
            "--stage artifacts/stage",
            "--output-directory artifacts/rpm",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.workflow)

    def test_rpm_is_counted_and_linted(self):
        self.assertIn("-name '*.x86_64.rpm' | wc -l)", self.workflow)
        self.assertIn(
            "test \"$(find artifacts/rpm -maxdepth 1 -type f -name '*.x86_64.rpm' | wc -l)\" -eq 1",
            self.workflow,
        )
        self.assertIn("rpmlint artifacts/rpm/*.x86_64.rpm", self.workflow)

    def test_rpmlint_output_is_captured_printed_and_rejects_errors_or_warnings(self):
        step_match = re.search(
            r"(?ms)^      - name: Build and lint the RPM package\n"
            r".*?(?=^      - name:|\Z)",
            self.workflow,
        )
        self.assertIsNotNone(step_match)
        step = step_match.group(0)
        normalized_step = re.sub(r"\\\s*\n\s*", " ", step)
        self.assertRegex(
            normalized_step,
            r"if\s+!\s+docker\s+run\b.*?"
            r"rpmlint artifacts/rpm/\*\.x86_64\.rpm\s+"
            r">\s*['\"]?\$RUNNER_TEMP/rpmlint\.log['\"]?\s+2>&1\s*;\s*then",
        )
        self.assertRegex(
            normalized_step,
            r"cat\s+['\"]?\$RUNNER_TEMP/rpmlint\.log['\"]?",
        )
        self.assertRegex(
            normalized_step,
            r"grep\s+-Eq?\s+['\"]?: \[EW\]:['\"]?"
            r"\s+['\"]?\$RUNNER_TEMP/rpmlint\.log['\"]?",
        )
        self.assertNotRegex(step, r"\|\s*tee\b")

    def test_rpm_is_installed_and_removed_in_a_clean_pinned_fedora_container(self):
        required = (
            FEDORA_IMAGE,
            '"$PWD/artifacts:/artifacts:ro"',
            "dnf --assumeyes install /artifacts/rpm/*.x86_64.rpm",
            "test -x /usr/bin/imagemd",
            "dnf --assumeyes remove imagemd",
            "test ! -e /usr/bin/imagemd",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.workflow)

    def test_source_date_epoch_is_persisted_before_package_builders(self):
        lines = self.workflow.splitlines()
        preparation_lines = [
            index
            for index, line in enumerate(lines)
            if "SOURCE_DATE_EPOCH" in line
            and "git log -1 --format=%ct" in line
            and "$GITHUB_ENV" in line
        ]
        self.assertTrue(
            preparation_lines,
            "SOURCE_DATE_EPOCH from the latest commit timestamp must be persisted to GITHUB_ENV",
        )

        builder_lines = [
            index
            for index, line in enumerate(lines)
            if any(
                builder in line
                for builder in (
                    "packaging/build_stage.py",
                    "packaging/rpm/build_rpm.py",
                    "packaging/arch/build_arch.py",
                )
            )
        ]
        self.assertTrue(builder_lines, "expected package builder references")
        self.assertLess(min(preparation_lines), min(builder_lines))

    def test_standalone_bundle_builds_are_reproducibility_checked(self):
        step_match = re.search(
            r"(?ms)^      - name: Build the standalone application bundle\n"
            r".*?(?=^      - name:|\Z)",
            self.workflow,
        )
        self.assertIsNotNone(step_match)
        step = step_match.group(0)
        required = (
            "--env PYTHONHASHSEED=1",
            "--env SOURCE_DATE_EPOCH",
            "artifacts/reproducibility-bundle",
            "--workpath /tmp/imagemd-repro-work",
            "cmp --silent artifacts/bundle/ImageMD artifacts/reproducibility-bundle/ImageMD",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, step)
        self.assertEqual(step.count("--env PYTHONHASHSEED=1"), 2)
        self.assertEqual(step.count("--env SOURCE_DATE_EPOCH"), 2)

    def test_rpm_builder_docker_run_passes_source_date_epoch_before_python(self):
        lines = self.workflow.splitlines()
        run_blocks = []
        for index, line in enumerate(lines):
            match = re.match(r"^(\s*)run:\s*\|\s*$", line)
            if not match:
                continue
            indentation = len(match.group(1))
            block = []
            for body_line in lines[index + 1 :]:
                if (
                    body_line.strip()
                    and len(body_line) - len(body_line.lstrip()) <= indentation
                ):
                    break
                if body_line.strip():
                    block.append(body_line.strip())
            run_blocks.append(block)

        build_blocks = [
            block
            for block in run_blocks
            if any("python packaging/rpm/build_rpm.py" in line for line in block)
        ]
        self.assertEqual(len(build_blocks), 1)
        block = build_blocks[0]
        python_index = next(
            index
            for index, line in enumerate(block)
            if "python packaging/rpm/build_rpm.py" in line
        )
        docker_starts = [
            index
            for index, line in enumerate(block[:python_index])
            if "docker run" in line
        ]
        self.assertTrue(docker_starts, "RPM builder must run inside Docker")

        invocation = block[docker_starts[-1] : python_index]
        self.assertTrue(
            any("--env SOURCE_DATE_EPOCH" in line for line in invocation),
            "the Docker invocation for build_rpm.py must pass SOURCE_DATE_EPOCH before Python",
        )

    def test_arch_output_ownership_uses_the_parent_artifacts_mount(self):
        prepare_match = re.search(
            r"(?ms)^      - name: Prepare the Arch package output directory\n"
            r".*?(?=^      - name:|\Z)",
            self.workflow,
        )
        self.assertIsNotNone(prepare_match)
        prepare_step = prepare_match.group(0)
        self.assertNotIn("mkdir -p artifacts/arch", prepare_step)
        self.assertIn('--volume "$PWD/artifacts:/artifacts"', prepare_step)
        self.assertIn("chown builder:builder /artifacts", prepare_step)

        build_match = re.search(
            r"(?ms)^      - name: Build and lint the Arch package\n"
            r".*?(?=^      - name:|\Z)",
            self.workflow,
        )
        self.assertIsNotNone(build_match)
        self.assertIn("--output artifacts/arch", build_match.group(0))

    def test_arch_namcap_glob_expands_inside_the_container_shell(self):
        build_match = re.search(
            r"(?ms)^      - name: Build and lint the Arch package\n"
            r".*?(?=^      - name:|\Z)",
            self.workflow,
        )
        self.assertIsNotNone(build_match)
        step = build_match.group(0)
        normalized_step = re.sub(r"\\\s*\n\s*", " ", step)
        package_glob = "namcap ./*.pkg.tar.zst"
        namcap_index = normalized_step.find(package_glob)
        self.assertGreaterEqual(namcap_index, 0, "Arch lint must invoke namcap")
        docker_index = normalized_step.rfind("docker run", 0, namcap_index)
        self.assertGreaterEqual(
            docker_index, 0, "Arch namcap must run in a Docker container"
        )
        lint_invocation = normalized_step[
            docker_index : namcap_index + len(package_glob)
        ]
        self.assertRegex(
            lint_invocation,
            r"imagemd-arch-builder:ci\s+sh\s+-ceu\s+['\"]?namcap\s+\./\*\.pkg\.tar\.zst",
            "namcap must run through a container shell so the package glob expands there",
        )
        self.assertNotRegex(
            lint_invocation,
            r"imagemd-arch-builder:ci\s+namcap\s+\./\*\.pkg\.tar\.zst",
            "the Docker invocation must not pass the package glob directly to namcap",
        )

    def test_arch_namcap_output_is_captured_printed_and_strictly_filtered(self):
        build_match = re.search(
            r"(?ms)^      - name: Build and lint the Arch package\n"
            r".*?(?=^      - name:|\Z)",
            self.workflow,
        )
        self.assertIsNotNone(build_match)
        step = build_match.group(0)
        normalized_step = re.sub(r"\\\s*\n\s*", " ", step)
        allowed_warning = (
            "imagemd W: Dependency included, but may not be needed ('ffmpeg')"
        )
        self.assertIn(allowed_warning, step)
        self.assertRegex(
            normalized_step,
            r"if\s+!\s+docker\s+run\b.*?"
            r"sh\s+-ceu\s+['\"]?namcap\s+\.\/\*\.pkg\.tar\.zst"
            r"['\"]?\s+>\s*['\"]?\$RUNNER_TEMP/namcap\.log['\"]?\s+2>&1\s*;\s*then",
            "Arch namcap must capture stdout and stderr while retaining failure status",
        )
        self.assertRegex(
            normalized_step,
            r"cat\s+['\"]?\$RUNNER_TEMP/namcap\.log['\"]?",
            "the Arch namcap log must always be printed",
        )
        self.assertRegex(
            normalized_step,
            r"(?s)if\s+!\s+docker\s+run\b.*?then.*?"
            r"cat\s+['\"]?\$RUNNER_TEMP/namcap\.log['\"]?.*?"
            r"exit\s+1\s*;?\s*fi",
            "a nonzero namcap exit must fail after printing its log",
        )
        self.assertRegex(
            normalized_step,
            r"(?:grep\s+-[A-Za-z]*Fv[A-Za-z]*\s+['\"]?"
            + re.escape(allowed_warning)
            + r"['\"]?\s+['\"]?\$RUNNER_TEMP/namcap\.log['\"]?|"
            r"awk\b.*?exception=['\"]?"
            + re.escape(allowed_warning)
            + r"['\"]?.*?\$RUNNER_TEMP/namcap\.log)",
            "only the exact known namcap warning may be allowlisted",
        )
        self.assertRegex(
            normalized_step,
            r"(?:grep\s+-E[^\n]*[EW][^\n]*\$RUNNER_TEMP/namcap\.log|"
            r"awk\b.*?\[EW\].*?\$RUNNER_TEMP/namcap\.log)",
            "Arch namcap errors and warnings must fail the workflow",
        )
        self.assertNotRegex(step, r"\|\s*(?:tee|grep)\b")
        self.assertNotRegex(step, r"\|\s*grep\s+-v(?:[A-Za-z]|\s)")
        self.assertNotRegex(step, r"\|\|\s*(?:true|:)")
        self.assertNotRegex(
            step, r"(?i)(?:continue-on-error:\s*true|if:\s*false|skip.*namcap)"
        )

    def test_appimage_block_builds_and_validates_reproducible_bundle(self):
        lines = self.workflow.splitlines()
        run_blocks = []
        for index, line in enumerate(lines):
            match = re.match(r"^(\s*)run:\s*\|\s*$", line)
            if not match:
                continue
            indentation = len(match.group(1))
            block = []
            for body_line in lines[index + 1 :]:
                if (
                    body_line.strip()
                    and len(body_line) - len(body_line.lstrip()) <= indentation
                ):
                    break
                if body_line.strip():
                    block.append(body_line.strip())
            run_blocks.append(block)

        appimage_blocks = [
            block
            for block in run_blocks
            if any(
                token in line
                for line in block
                for token in (
                    "Dockerfile.appimage-runtime",
                    "build_appdir.py",
                    "appimagetool",
                )
            )
        ]
        self.assertEqual(len(appimage_blocks), 1)
        block = appimage_blocks[0]
        required = (
            "--file packaging/container/Dockerfile.appimage-runtime",
            "--tag imagemd-appimage-runtime:ci",
            "--build-arg SOURCE_DATE_EPOCH",
            "/opt/imagemd-runtime/bin/ffmpeg",
            "/opt/imagemd-runtime/bin/ffprobe",
            "packaging/appimage/build_appdir.py",
            "--stage artifacts/stage",
            "--appdir artifacts/appdir",
            "--ffmpeg",
            "--ffprobe",
            "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage",
            "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0",
            "https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64",
            "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d",
            "APPIMAGE_EXTRACT_AND_RUN=1",
            "--runtime-file",
            ".AppImage",
            "--appimage-offset",
            "timeout 10",
            "xvfb-run -a",
            "artifacts/ImageMD-x86_64.AppImage",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertTrue(any(fragment in line for line in block))

        self.assertGreaterEqual(
            sum("sha256sum" in line for line in block),
            2,
            "the appimagetool and runtime downloads must each be checksum-verified",
        )
        block_text = "\n".join(block)
        self.assertRegex(block_text, r"(?m)^status\s*=\s*\$\?$|\$status")
        self.assertRegex(
            block_text,
            r"(?s)(?:if\b.*?(?:\$status|status).*?(?:-ne|!=).*?124.*?then.*?exit|case\s+\"?\$status\"?.*?124\s*\).*?(?:;;|success|exit))",
            "AppImage validation must treat only exit code 124 as the timeout success case",
        )
        self.assertFalse(
            any(
                token in line
                for line in block
                for token in ("continuous", "latest", "curl |", "wget |")
            )
        )

    def test_arch_package_build_and_clean_container_install_are_pinned(self):
        arch_digest = re.search(r"FROM\s+(archlinux:[^\s]+)", self.arch_dockerfile)
        self.assertIsNotNone(arch_digest, "Dockerfile.arch must pin an Arch base image")
        arch_image = arch_digest.group(1)
        lines = self.workflow.splitlines()
        run_blocks = []
        for index, line in enumerate(lines):
            match = re.match(r"^(\s*)run:\s*\|\s*$", line)
            if not match:
                continue
            indentation = len(match.group(1))
            block = []
            for body_line in lines[index + 1 :]:
                if (
                    body_line.strip()
                    and len(body_line) - len(body_line.lstrip()) <= indentation
                ):
                    break
                if body_line.strip():
                    block.append(body_line.strip())
            run_blocks.append(block)

        arch_blocks = [
            block
            for block in run_blocks
            if any(
                token in line
                for line in block
                for token in (
                    "Dockerfile.arch",
                    "build_arch.py",
                    "pacman",
                    "makepkg",
                    "namcap",
                )
            )
        ]
        self.assertTrue(arch_blocks, "expected an Arch packaging block")
        block_text = "\n".join("\n".join(block) for block in arch_blocks)
        required = (
            "--file packaging/container/Dockerfile.arch",
            "--tag imagemd-arch-builder:ci",
            "packaging/arch/build_arch.py",
            "--stage artifacts/stage",
            "--output artifacts/arch",
            "--env SOURCE_DATE_EPOCH",
            "makepkg --noconfirm --syncdeps --cleanbuild",
            "*.pkg.tar.zst",
            "namcap",
            arch_image,
            "pacman --noconfirm -U",
            "/usr/bin/imagemd",
            "pacman --noconfirm -R",
            "imagemd",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, block_text)
        self.assertRegex(self.arch_dockerfile, r"(?m)^USER\s+builder\s*$")
        build_line = next(
            index
            for index, line in enumerate(block_text.splitlines())
            if "packaging/arch/build_arch.py" in line
        )
        env_lines = [
            index
            for index, line in enumerate(block_text.splitlines()[:build_line])
            if "--env SOURCE_DATE_EPOCH" in line
        ]
        self.assertTrue(
            env_lines, "build_arch.py Docker invocation must pass SOURCE_DATE_EPOCH"
        )
        self.assertRegex(
            block_text,
            r"(?:find|test).*\*\.pkg\.tar\.zst.*(?:wc\s+-l|eq\s+1)|(?:wc\s+-l|find).*\.pkg\.tar\.zst",
        )
        self.assertRegex(block_text, r"test\s+!\s+-e\s+/usr/bin/imagemd")
        for token in (
            "--privileged",
            "latest",
            "continuous",
            "secrets.",
            "docker push",
            "upload-artifact",
        ):
            with self.subTest(forbidden=token):
                self.assertNotIn(token, block_text)

    def test_native_flatpak_block_builds_installs_and_smoke_tests_bundle(self):
        lines = self.workflow.splitlines()
        run_blocks = []
        for index, line in enumerate(lines):
            match = re.match(r"^(\s*)run:\s*\|\s*$", line)
            if not match:
                continue
            indentation = len(match.group(1))
            block = []
            for body_line in lines[index + 1 :]:
                if (
                    body_line.strip()
                    and len(body_line) - len(body_line.lstrip()) <= indentation
                ):
                    break
                if body_line.strip():
                    block.append(body_line.strip())
            run_blocks.append(block)

        flatpak_blocks = [
            block
            for block in run_blocks
            if any(
                token in line
                for line in block
                for token in (
                    "flatpak-builder",
                    "prepare_flatpak.py",
                    "flatpak build-bundle",
                )
            )
        ]
        self.assertEqual(len(flatpak_blocks), 1)
        block_text = "\n".join(flatpak_blocks[0])
        required = (
            "sudo flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo",
            "org.freedesktop.Platform//25.08",
            "org.freedesktop.Sdk//25.08",
            "packaging/flatpak/prepare_flatpak.py --stage artifacts/stage --output artifacts/flatpak-context",
            "artifacts/flatpak-context/org.roymejia.ImageMD.yml",
            "flatpak-builder",
            "--force-clean",
            "--repo",
            "--install-deps-from=flathub",
            "flatpak build-bundle",
            ".flatpak",
            "flatpak run --command=sh",
            "test -x /app/bin/ffmpeg",
            "test -x /app/bin/ffprobe",
            "timeout 10 xvfb-run -a flatpak run org.roymejia.ImageMD",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, block_text)
        flatpak_command_text = re.sub(r"\\\s*", " ", block_text)
        self.assertRegex(
            flatpak_command_text,
            r"flatpak-builder\s+--force-clean\s+--repo\s+\S+\s+--install-deps-from=flathub\s+artifacts/flatpak-build\s+artifacts/flatpak-context/org\.roymejia\.ImageMD\.yml",
            "flatpak-builder must receive the explicit build directory before its manifest",
        )
        self.assertRegex(block_text, r"(?m)^status\s*=\s*\$\?")
        self.assertRegex(
            block_text,
            r"(?s)(?:if\b.*?(?:\$status|status).*?(?:-ne|!=).*?124.*?then.*?exit|case\s+\"?\$status\"?.*?124\s*\).*?(?:;;|success|exit))",
            "Flatpak GUI smoke test must treat only exit code 124 as timeout success",
        )
        for token in (
            "--no-gpg-verify",
            "--privileged",
            "continuous",
            "latest",
            "docker push",
            "upload-artifact",
            "secrets.",
        ):
            with self.subTest(forbidden=token):
                self.assertNotIn(token, block_text)


if __name__ == "__main__":
    unittest.main()
