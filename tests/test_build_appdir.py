from pathlib import Path
import importlib.util
import tempfile
import unittest


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "appimage" / "build_appdir.py"
SPEC = importlib.util.spec_from_file_location("build_appdir", MODULE_PATH)
assert SPEC and SPEC.loader
build_appdir = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_appdir)


class TestAppRun(unittest.TestCase):
    def test_uses_appdir_and_forwards_arguments(self):
        self.assertIn('"$APPDIR/usr/bin/imagemd" "$@"', build_appdir.APPRUN)

    def test_rejects_existing_appdir(self):
        with tempfile.TemporaryDirectory() as temporary:
            appdir = Path(temporary) / "ImageMD.AppDir"
            appdir.mkdir()
            ffmpeg = Path(temporary) / "ffmpeg"
            ffmpeg.write_bytes(b"#!/bin/sh\n")
            ffmpeg.chmod(0o755)
            ffprobe = Path(temporary) / "ffprobe"
            ffprobe.write_bytes(b"#!/bin/sh\n")
            ffprobe.chmod(0o755)
            with self.assertRaises(FileExistsError):
                build_appdir.create(Path(temporary), appdir, ffmpeg, ffprobe)


if __name__ == "__main__":
    unittest.main()
