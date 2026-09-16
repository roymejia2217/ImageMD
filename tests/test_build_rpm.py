from pathlib import Path
import importlib.util
import unittest


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "rpm" / "build_rpm.py"
SPEC = importlib.util.spec_from_file_location("build_rpm", MODULE_PATH)
assert SPEC and SPEC.loader
build_rpm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_rpm)


class TestRpmBuild(unittest.TestCase):
    def test_development_version_sorts_before_final_release(self):
        self.assertEqual(build_rpm.rpm_version("1.1.0.dev0"), "1.1.0~dev0")
        self.assertEqual(build_rpm.rpm_version("1.1.0"), "1.1.0")

    def test_spec_is_for_x86_64_and_declares_video_runtime_dependency(self):
        spec = (
            Path(__file__).parents[1] / "packaging/rpm/imagemd-rpm.spec.in"
        ).read_text(encoding="utf-8")
        self.assertIn("BuildArch:      x86_64", spec)
        self.assertIn("Requires:       ffmpeg-free", spec)
        self.assertIn("desktop-file-validate", spec)
        self.assertIn("%license /usr/share/licenses/imagemd/LICENSE", spec)
        self.assertLess(
            spec.find("cp -a rootfs/. %{buildroot}/"),
            spec.find("rm -f %{buildroot}%{_datadir}/doc/imagemd/copyright"),
        )
        self.assertNotIn("%license %{_datadir}/doc/imagemd/copyright", spec)


if __name__ == "__main__":
    unittest.main()
