from pathlib import Path
import importlib.util
import unittest


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "arch" / "build_arch.py"
SPEC = importlib.util.spec_from_file_location("build_arch", MODULE_PATH)
assert SPEC and SPEC.loader
build_arch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_arch)


class TestArchRecipe(unittest.TestCase):
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
