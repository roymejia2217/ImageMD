from pathlib import Path
import importlib.util
import json
import tempfile
import unittest


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "build_stage.py"
SPEC = importlib.util.spec_from_file_location("build_stage", MODULE_PATH)
assert SPEC and SPEC.loader
build_stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_stage)


class TestBuildStage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bundle = Path(self.temp.name) / "ImageMD"
        self.bundle.write_bytes(b"portable-bundle")
        self.bundle.chmod(0o755)

    def test_creates_deterministic_package_layout_and_metadata(self):
        output = Path(self.temp.name) / "stage"

        metadata = build_stage.create_stage(self.bundle, output)

        self.assertEqual(metadata["package"], "imagemd")
        self.assertEqual(
            (output / "rootfs/usr/bin/imagemd").read_bytes(), self.bundle.read_bytes()
        )
        self.assertTrue(
            (
                output / "rootfs/usr/share/applications/org.roymejia.ImageMD.desktop"
            ).is_file()
        )
        self.assertTrue(
            (
                output / "rootfs/usr/share/metainfo/org.roymejia.ImageMD.metainfo.xml"
            ).is_file()
        )
        self.assertTrue((output / "rootfs/usr/share/man/man1/imagemd.1").is_file())
        self.assertTrue(
            (output / "rootfs/usr/share/licenses/imagemd/LICENSE").is_file()
        )
        self.assertEqual(
            json.loads((output / "release-metadata.json").read_text(encoding="utf-8")),
            metadata,
        )

    def test_rejects_a_destination_that_already_exists(self):
        output = Path(self.temp.name) / "stage"
        output.mkdir()

        with self.assertRaises(FileExistsError):
            build_stage.create_stage(self.bundle, output)

    def test_rejects_non_executable_bundle(self):
        self.bundle.chmod(0o644)

        with self.assertRaisesRegex(ValueError, "executable regular file"):
            build_stage.create_stage(self.bundle, Path(self.temp.name) / "stage")


if __name__ == "__main__":
    unittest.main()
