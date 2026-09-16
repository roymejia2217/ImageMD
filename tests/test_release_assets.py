from pathlib import Path
from contextlib import redirect_stdout
import io
import json
import subprocess
import sys
from unittest.mock import patch
import tempfile
import unittest


from packaging import release_assets
from packaging.release_assets import normalize_release_assets, release_asset_names


VALID_METADATA = {
    "package": "imagemd",
    "version": "1.1.1",
    "architecture": "x86_64",
}

EXPECTED_NAMES = {
    "deb": "ImageMD-1.1.1-x86_64.deb",
    "rpm": "ImageMD-1.1.1-x86_64.rpm",
    "arch": "ImageMD-1.1.1-x86_64.pkg.tar.zst",
    "appimage": "ImageMD-1.1.1-x86_64.AppImage",
    "flatpak": "ImageMD-1.1.1-x86_64.flatpak",
    "metadata": "ImageMD-1.1.1-release-metadata.json",
    "sbom": "ImageMD-1.1.1.spdx.json",
    "checksums": "ImageMD-1.1.1-SHA256SUMS",
}

PACKAGE_EXTENSIONS = {
    "deb": ".deb",
    "rpm": ".rpm",
    "arch": ".pkg.tar.zst",
    "appimage": ".AppImage",
    "flatpak": ".flatpak",
}


class TestReleaseAssetNames(unittest.TestCase):
    def test_returns_canonical_names_for_release_metadata(self):
        self.assertEqual(release_asset_names(VALID_METADATA), EXPECTED_NAMES)

    def test_rejects_metadata_with_wrong_package(self):
        metadata = {**VALID_METADATA, "package": "other-package"}

        with self.assertRaises(ValueError):
            release_asset_names(metadata)

    def test_rejects_metadata_with_non_semver_version(self):
        metadata = {**VALID_METADATA, "version": "1.1"}

        with self.assertRaises(ValueError):
            release_asset_names(metadata)

    def test_rejects_metadata_with_wrong_architecture(self):
        metadata = {**VALID_METADATA, "architecture": "amd64"}

        with self.assertRaises(ValueError):
            release_asset_names(metadata)


class TestNormalizeReleaseAssets(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def _write_package(self, key, source_name=None, contents=None):
        extension = PACKAGE_EXTENSIONS[key]
        path = self.directory / (source_name or f"source-{key}{extension}")
        path.write_bytes(contents or key.encode("ascii"))
        return path

    def _write_all_packages(self):
        for key in PACKAGE_EXTENSIONS:
            self._write_package(key)

    def test_renames_each_package_to_canonical_name_and_returns_paths(self):
        self._write_package("deb", "build-123.deb", b"deb-content")
        self._write_package("rpm", "build-123.rpm", b"rpm-content")
        self._write_package("arch", "build-123.pkg.tar.zst", b"arch-content")
        self._write_package("appimage", "build-123.AppImage", b"appimage-content")
        self._write_package("flatpak", "build-123.flatpak", b"flatpak-content")
        evidence = self.directory / "build-log.txt"
        evidence.write_text("preserve this evidence", encoding="utf-8")

        result = normalize_release_assets(self.directory, VALID_METADATA)

        self.assertEqual(
            result,
            {key: self.directory / EXPECTED_NAMES[key] for key in PACKAGE_EXTENSIONS},
        )
        for key, expected_name in EXPECTED_NAMES.items():
            if key in PACKAGE_EXTENSIONS:
                self.assertEqual(
                    (self.directory / expected_name).read_bytes(),
                    key.encode("ascii") + b"-content"
                    if key in {"deb", "rpm", "arch", "appimage", "flatpak"}
                    else key.encode("ascii"),
                )
        self.assertEqual(evidence.read_text(encoding="utf-8"), "preserve this evidence")
        self.assertFalse((self.directory / "build-123.deb").exists())

    def test_rejects_duplicate_package_extensions_without_mutating_directory(self):
        self._write_all_packages()
        duplicate = self._write_package("deb", "second-build.deb", b"second")
        original = (self.directory / "source-deb.deb").read_bytes()

        with self.assertRaises(ValueError):
            normalize_release_assets(self.directory, VALID_METADATA)

        self.assertEqual((self.directory / "source-deb.deb").read_bytes(), original)
        self.assertEqual(duplicate.read_bytes(), b"second")
        self.assertFalse((self.directory / EXPECTED_NAMES["deb"]).exists())

    def test_rejects_missing_package_extension(self):
        for key in PACKAGE_EXTENSIONS:
            if key != "flatpak":
                self._write_package(key)

        with self.assertRaises(ValueError):
            normalize_release_assets(self.directory, VALID_METADATA)

    def test_rejects_existing_canonical_destination_without_mutating_source(self):
        self._write_all_packages()
        source = self.directory / "source-deb.deb"
        original = source.read_bytes()
        destination = self.directory / EXPECTED_NAMES["deb"]
        destination.write_bytes(b"must-preserve")

        with self.assertRaises(FileExistsError):
            normalize_release_assets(self.directory, VALID_METADATA)

        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(destination.read_bytes(), b"must-preserve")

    def test_rejects_invalid_metadata_without_mutating_packages(self):
        self._write_all_packages()
        original = {path.name: path.read_bytes() for path in self.directory.iterdir()}

        with self.assertRaises(ValueError):
            normalize_release_assets(
                self.directory,
                {**VALID_METADATA, "version": "release-1.1"},
            )

        self.assertEqual(
            {path.name: path.read_bytes() for path in self.directory.iterdir()},
            original,
        )


class TestReleaseAssetCommand(unittest.TestCase):
    def test_executes_when_invoked_as_a_script(self):
        with tempfile.TemporaryDirectory() as temporary:
            metadata_path = Path(temporary) / "release-metadata.json"
            metadata_path.write_text(json.dumps(VALID_METADATA), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).parents[1] / "packaging/release_assets.py"),
                    "--metadata",
                    str(metadata_path),
                    "--name",
                    "checksums",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "ImageMD-1.1.1-SHA256SUMS\n")

    def test_emits_a_name_from_a_prevalidated_release_version(self):
        output = io.StringIO()

        with (
            patch(
                "sys.argv",
                [
                    "release_assets.py",
                    "--version",
                    "1.1.1",
                    "--name",
                    "metadata",
                ],
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(release_assets.main(), 0)

        self.assertEqual(output.getvalue(), "ImageMD-1.1.1-release-metadata.json\n")

    def test_emits_one_canonical_name_from_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            metadata_path = Path(temporary) / "release-metadata.json"
            metadata_path.write_text(json.dumps(VALID_METADATA), encoding="utf-8")
            output = io.StringIO()

            with (
                patch(
                    "sys.argv",
                    [
                        "release_assets.py",
                        "--metadata",
                        str(metadata_path),
                        "--name",
                        "flatpak",
                    ],
                ),
                redirect_stdout(output),
            ):
                self.assertEqual(release_assets.main(), 0)

        self.assertEqual(output.getvalue(), "ImageMD-1.1.1-x86_64.flatpak\n")

    def test_normalizes_a_directory_from_the_command_interface(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            metadata_path = directory / "release-metadata.json"
            metadata_path.write_text(json.dumps(VALID_METADATA), encoding="utf-8")
            for key, extension in PACKAGE_EXTENSIONS.items():
                (directory / f"candidate-{key}{extension}").write_bytes(
                    key.encode("ascii")
                )

            with patch(
                "sys.argv",
                [
                    "release_assets.py",
                    "--metadata",
                    str(metadata_path),
                    "--normalize-directory",
                    str(directory),
                ],
            ):
                self.assertEqual(release_assets.main(), 0)

            self.assertEqual(
                {path.name for path in directory.iterdir()},
                {
                    "release-metadata.json",
                    *(EXPECTED_NAMES[key] for key in PACKAGE_EXTENSIONS),
                },
            )


if __name__ == "__main__":
    unittest.main()
