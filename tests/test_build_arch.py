from pathlib import Path
import importlib.util
import json
import os
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "arch" / "build_arch.py"
SPEC = importlib.util.spec_from_file_location("build_arch", MODULE_PATH)
assert SPEC and SPEC.loader
build_arch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_arch)


class TestArchRecipe(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.stage = self.base / "stage"
        rootfs = self.stage / "rootfs"
        for relative in (
            "usr/bin/imagemd",
            "usr/share/applications/org.roymejia.ImageMD.desktop",
            "usr/share/icons/hicolor/scalable/apps/org.roymejia.ImageMD.svg",
            "usr/share/metainfo/org.roymejia.ImageMD.metainfo.xml",
            "usr/share/doc/imagemd/copyright",
            "usr/share/man/man1/imagemd.1",
        ):
            path = rootfs / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture: {relative}\n", encoding="utf-8")
        (self.stage / "release-metadata.json").write_text(
            json.dumps(
                {
                    "package": "imagemd",
                    "architecture": "x86_64",
                    "version": "1.2.3.dev0",
                }
            ),
            encoding="utf-8",
        )

    def test_creates_recipe_when_output_is_absent(self):
        output = self.base / "recipe"

        with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
            self.assertEqual(build_arch.create_recipe(self.stage, output), output)

        self.assertTrue((output / "PKGBUILD").is_file())
        self.assertTrue((output / "imagemd-1.2.3.dev0.tar.gz").is_file())

    def test_allows_an_existing_empty_directory(self):
        output = self.base / "recipe"
        output.mkdir()

        with patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "0"}):
            build_arch.create_recipe(self.stage, output)

        self.assertTrue((output / "PKGBUILD").is_file())

    def test_rejects_an_existing_non_empty_directory(self):
        output = self.base / "recipe"
        output.mkdir()
        (output / "preexisting").write_text("must remain", encoding="utf-8")

        with self.assertRaisesRegex(FileExistsError, "non-empty"):
            build_arch.create_recipe(self.stage, output)

        self.assertEqual(
            (output / "preexisting").read_text(encoding="utf-8"), "must remain"
        )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_rejects_a_symlink_output(self):
        target = self.base / "target"
        target.mkdir()
        output = self.base / "recipe"
        output.symlink_to(target, target_is_directory=True)

        with self.assertRaisesRegex(FileExistsError, "symlink"):
            build_arch.create_recipe(self.stage, output)

    def test_template_declares_all_runtime_dependencies(self):
        template = (Path(__file__).parents[1] / "packaging/arch/PKGBUILD.in").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "depends=('ffmpeg' 'glibc>=2.36' 'zlib' 'hicolor-icon-theme')", template
        )

    def test_template_has_pinned_archive_and_runtime_dependencies(self):
        template = (Path(__file__).parents[1] / "packaging/arch/PKGBUILD.in").read_text(
            encoding="utf-8"
        )
        self.assertIn("sha256sums=('@SHA256@')", template)
        self.assertIn(
            "depends=('ffmpeg' 'glibc>=2.36' 'zlib' 'hicolor-icon-theme')", template
        )
        self.assertIn("options=('!debug')", template)
        self.assertIn('cp -a "${srcdir}/rootfs/." "${pkgdir}/"', template)


if __name__ == "__main__":
    unittest.main()
