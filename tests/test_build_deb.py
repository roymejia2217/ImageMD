from pathlib import Path
import importlib.util
import json
import tempfile
import unittest


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "debian" / "build_deb.py"
SPEC = importlib.util.spec_from_file_location("build_deb", MODULE_PATH)
assert SPEC and SPEC.loader
build_deb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_deb)


class TestDebianBuild(unittest.TestCase):
    def test_development_version_sorts_before_final_release(self):
        self.assertEqual(build_deb.debian_version("1.1.0.dev0"), "1.1.0~dev0")
        self.assertEqual(build_deb.debian_version("1.1.0"), "1.1.0")

    def test_control_uses_version_from_staging_metadata(self):
        control = build_deb.control_contents({"version": "1.1.0.dev0"})
        self.assertIn("Version: 1.1.0~dev0", control)
        self.assertIn("Depends: ffmpeg, libc6 (>= 2.36)", control)

    def test_missing_stage_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            (stage / "rootfs").mkdir()
            (stage / "release-metadata.json").write_text(
                json.dumps({"package": "imagemd", "architecture": "x86_64"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing required file"):
                build_deb.read_metadata(stage)


if __name__ == "__main__":
    unittest.main()
