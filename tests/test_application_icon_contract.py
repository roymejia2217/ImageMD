from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "org.roymejia.ImageMD"
ICON_HASHES = {
    16: "61bc6775de7702a38f6be9f6db9bc37230cf103c3793926943f659245e2392dd",
    32: "bfc6c623ab54450f5898d6b80f76419c2102e3762c49ff83559746af8a174ed8",
    48: "370da7a2c74d7a5bd003023d88715f52db7206b1b6e72cd083059cd07ca516a9",
    256: "f687ca71cca44b602f8f35a0cc8dd08b91031754c0d0b498aea9562a6ae95039",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApplicationIconContractTests(unittest.TestCase):
    def test_windows_canonical_icon_matches_official_1_0_0_release_resource(self):
        icon = ROOT / "packaging/common/icons/windows/ImageMD.ico"
        self.assertTrue(icon.is_file())
        self.assertEqual(
            sha256(icon),
            "168db1b8a7c62fa2ab92c1210185d145923f31c1be23fded42d9420f48b98392",
        )

        spec = (ROOT / "imagemd.spec").read_text(encoding="utf-8")
        self.assertIn(
            'icon="packaging/common/icons/windows/ImageMD.ico" '
            'if sys.platform == "win32" else None',
            spec,
        )

    def test_linux_icons_are_exact_windows_release_identity_frames(self):
        for size, expected_hash in ICON_HASHES.items():
            with self.subTest(size=size):
                icon = (
                    ROOT
                    / "packaging/common/icons/hicolor"
                    / f"{size}x{size}"
                    / "apps"
                    / f"{PACKAGE_ID}.png"
                )
                self.assertTrue(icon.is_file(), f"missing canonical {size}px icon")
                self.assertEqual(sha256(icon), expected_hash)

        self.assertFalse(
            (ROOT / f"packaging/common/{PACKAGE_ID}.svg").exists(),
            "the invented Linux SVG must not remain a package identity source",
        )

    def test_shared_stage_installs_every_canonical_icon_frame(self):
        build_stage = load_module(
            "build_stage_icon_contract", "packaging/build_stage.py"
        )
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "ImageMD"
            bundle.write_bytes(b"portable-bundle")
            bundle.chmod(0o755)
            stage = Path(temporary) / "stage"

            build_stage.create_stage(bundle, stage)

            for size, expected_hash in ICON_HASHES.items():
                with self.subTest(size=size):
                    installed = (
                        stage
                        / "rootfs/usr/share/icons/hicolor"
                        / f"{size}x{size}"
                        / "apps"
                        / f"{PACKAGE_ID}.png"
                    )
                    self.assertTrue(installed.is_file())
                    self.assertEqual(sha256(installed), expected_hash)

    def test_debian_validator_requires_canonical_png_icons(self):
        build_deb = load_module(
            "build_deb_icon_contract", "packaging/debian/build_deb.py"
        )
        for size in ICON_HASHES:
            self.assertIn(
                f"usr/share/icons/hicolor/{size}x{size}/apps/{PACKAGE_ID}.png",
                build_deb.REQUIRED_PATHS,
            )
        self.assertFalse(
            any(path.endswith(".svg") for path in build_deb.REQUIRED_PATHS)
        )

    def test_rpm_and_flatpak_package_all_canonical_png_icons(self):
        rpm_spec = (ROOT / "packaging/rpm/imagemd-rpm.spec.in").read_text(
            encoding="utf-8"
        )
        flatpak = (ROOT / "packaging/flatpak/org.roymejia.ImageMD.yml").read_text(
            encoding="utf-8"
        )

        for size in ICON_HASHES:
            relative = f"icons/hicolor/{size}x{size}/apps/{PACKAGE_ID}.png"
            with self.subTest(size=size):
                self.assertIn(relative, rpm_spec)
                self.assertIn(relative, flatpak)

        self.assertNotIn(f"{PACKAGE_ID}.svg", rpm_spec)
        self.assertNotIn(f"{PACKAGE_ID}.svg", flatpak)

    def test_appimage_exposes_256px_identity_as_dir_icon(self):
        build_stage = load_module(
            "build_stage_appimage_icon_contract", "packaging/build_stage.py"
        )
        build_appdir = load_module(
            "build_appdir_icon_contract", "packaging/appimage/build_appdir.py"
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "ImageMD"
            bundle.write_bytes(b"portable-bundle")
            bundle.chmod(0o755)
            stage = root / "stage"
            build_stage.create_stage(bundle, stage)

            ffmpeg = root / "ffmpeg"
            ffmpeg.write_bytes(b"#!/bin/sh\n")
            ffmpeg.chmod(0o755)
            ffprobe = root / "ffprobe"
            ffprobe.write_bytes(b"#!/bin/sh\n")
            ffprobe.chmod(0o755)

            appdir = root / "ImageMD.AppDir"
            build_appdir.create(stage, appdir, ffmpeg, ffprobe)

            canonical = (
                appdir / "usr/share/icons/hicolor/256x256/apps" / f"{PACKAGE_ID}.png"
            )
            root_icon = appdir / f"{PACKAGE_ID}.png"
            dir_icon = appdir / ".DirIcon"

            self.assertTrue(canonical.is_file())
            self.assertTrue(root_icon.is_symlink())
            self.assertEqual(
                root_icon.readlink(),
                Path(f"usr/share/icons/hicolor/256x256/apps/{PACKAGE_ID}.png"),
            )
            self.assertTrue(dir_icon.is_symlink())
            self.assertEqual(dir_icon.readlink(), Path(f"{PACKAGE_ID}.png"))
            self.assertEqual(sha256(canonical), ICON_HASHES[256])


if __name__ == "__main__":
    unittest.main()
