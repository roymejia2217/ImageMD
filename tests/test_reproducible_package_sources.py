from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_rpm = load_module("build_rpm", PROJECT_ROOT / "packaging/rpm/build_rpm.py")
build_arch = load_module("build_arch", PROJECT_ROOT / "packaging/arch/build_arch.py")
reproducibility = load_module(
    "reproducibility", PROJECT_ROOT / "packaging/reproducibility.py"
)


def make_valid_stage(stage: Path) -> None:
    rootfs = stage / "rootfs"
    required_files = (
        "usr/bin/imagemd",
        "usr/share/applications/org.roymejia.ImageMD.desktop",
        "usr/share/icons/hicolor/scalable/apps/org.roymejia.ImageMD.svg",
        "usr/share/metainfo/org.roymejia.ImageMD.metainfo.xml",
        "usr/share/doc/imagemd/copyright",
        "usr/share/man/man1/imagemd.1",
    )
    for relative in required_files:
        path = rootfs / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture: {relative}\n", encoding="utf-8")
    (stage / "release-metadata.json").write_text(
        json.dumps(
            {
                "package": "imagemd",
                "architecture": "x86_64",
                "version": "1.2.3.dev0",
            }
        ),
        encoding="utf-8",
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TestReproduciblePackageSources(unittest.TestCase):
    def test_arch_recipe_source_archive_is_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            stage = base / "stage"
            stage.mkdir()
            make_valid_stage(stage)
            archive_bytes = []

            with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
                for number in range(2):
                    output = build_arch.create_recipe(stage, base / f"arch-{number}")
                    archive = output / "imagemd-1.2.3.dev0.tar.gz"
                    archive_bytes.append(archive.read_bytes())

            self.assertEqual(sha256(archive_bytes[0]), sha256(archive_bytes[1]))
            self.assertEqual(archive_bytes[0], archive_bytes[1])

    def test_rpm_source_archive_is_reproducible_without_rpmbuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            stage = base / "stage"
            stage.mkdir()
            make_valid_stage(stage)
            captured_archives: list[tuple[Path, bytes]] = []

            def fake_rpmbuild(command, check):
                self.assertTrue(check)
                topdir_argument = command[command.index("--define") + 1]
                topdir = Path(topdir_argument.split(" ", 1)[1])
                source_archive = topdir / "SOURCES" / "imagemd-stage.tar.gz"
                source_bytes = source_archive.read_bytes()
                captured_archives.append((source_archive, source_bytes))
                rpm_directory = topdir / "RPMS" / "x86_64"
                rpm_directory.mkdir(parents=True)
                (rpm_directory / "imagemd-1.2.3~dev0-1.x86_64.rpm").write_bytes(
                    source_bytes
                )
                return subprocess.CompletedProcess(command, 0)

            with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
                with patch.object(
                    build_rpm.subprocess, "run", side_effect=fake_rpmbuild
                ):
                    for number in range(2):
                        build_rpm.build(stage, base / f"rpm-{number}")

            self.assertEqual(len(captured_archives), 2)
            self.assertTrue(
                all(
                    path.name == "imagemd-stage.tar.gz" for path, _ in captured_archives
                )
            )
            first = captured_archives[0][1]
            second = captured_archives[1][1]
            self.assertEqual(sha256(first), sha256(second))
            self.assertEqual(first, second)

    def test_source_date_epoch_accepts_zero(self):
        with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
            self.assertEqual(reproducibility.source_date_epoch(), 0)

    def test_source_date_epoch_rejects_non_integer_and_negative_values(self):
        for value in ("not-an-integer", "-1"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": value}):
                    with self.assertRaises(ValueError):
                        reproducibility.source_date_epoch()


if __name__ == "__main__":
    unittest.main()
