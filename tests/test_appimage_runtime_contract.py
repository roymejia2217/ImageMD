import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "appimage" / "build_appdir.py"
SPEC = importlib.util.spec_from_file_location(
    "build_appdir_runtime_contract", MODULE_PATH
)
assert SPEC and SPEC.loader
build_appdir = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_appdir)


class TestAppImageRuntimeContract(unittest.TestCase):
    def test_copies_runtime_binaries_and_configures_apprun(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary) / "stage"
            rootfs = stage / "rootfs"
            required = (
                "usr/bin/imagemd",
                "usr/share/applications/org.roymejia.ImageMD.desktop",
                "usr/share/icons/hicolor/scalable/apps/org.roymejia.ImageMD.svg",
                "usr/share/metainfo/org.roymejia.ImageMD.metainfo.xml",
                "usr/share/doc/imagemd/copyright",
                "usr/share/man/man1/imagemd.1",
            )
            for relative in required:
                path = rootfs / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"stage fixture")
            (stage / "release-metadata.json").write_text(
                json.dumps(
                    {"package": "imagemd", "architecture": "x86_64", "version": "0.0.0"}
                ),
                encoding="utf-8",
            )
            ffmpeg = Path(temporary) / "ffmpeg"
            ffmpeg.write_bytes(b"#!/bin/sh\n")
            ffmpeg.chmod(0o755)
            ffprobe = Path(temporary) / "ffprobe"
            ffprobe.write_bytes(b"#!/bin/sh\n")
            ffprobe.chmod(0o755)
            appdir = Path(temporary) / "ImageMD.AppDir"

            result = build_appdir.create(stage, appdir, ffmpeg, ffprobe)

            self.assertEqual(result, appdir)
            for name, source in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)):
                target = appdir / "usr" / "bin" / name
                self.assertEqual(target.read_bytes(), source.read_bytes())
                self.assertTrue(target.is_file())
                self.assertTrue(target.stat().st_mode & stat.S_IXUSR)
            apprun = (appdir / "AppRun").read_text(encoding="utf-8")
            ffmpeg_assignment = 'IMAGEMD_FFMPEG_EXECUTABLE="$APPDIR/usr/bin/ffmpeg"'
            ffprobe_assignment = 'IMAGEMD_FFPROBE_EXECUTABLE="$APPDIR/usr/bin/ffprobe"'
            self.assertIn(ffmpeg_assignment, apprun)
            self.assertIn(ffprobe_assignment, apprun)
            self.assertLess(apprun.index(ffmpeg_assignment), apprun.index("exec "))
            self.assertLess(apprun.index(ffprobe_assignment), apprun.index("exec "))

    def test_rejects_missing_or_directory_or_non_executable_runtime_binary(self):
        for binary_name in ("ffmpeg", "ffprobe"):
            for invalid_kind in ("missing", "directory", "non-executable"):
                with self.subTest(binary=binary_name, invalid=invalid_kind):
                    with tempfile.TemporaryDirectory() as temporary:
                        stage = Path(temporary) / "stage"
                        rootfs = stage / "rootfs"
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
                            path.write_bytes(b"stage fixture")
                        (stage / "release-metadata.json").write_text(
                            json.dumps(
                                {
                                    "package": "imagemd",
                                    "architecture": "x86_64",
                                    "version": "0.0.0",
                                }
                            ),
                            encoding="utf-8",
                        )
                        ffmpeg = Path(temporary) / "ffmpeg"
                        ffmpeg.write_bytes(b"#!/bin/sh\n")
                        ffmpeg.chmod(0o755)
                        ffprobe = Path(temporary) / "ffprobe"
                        ffprobe.write_bytes(b"#!/bin/sh\n")
                        ffprobe.chmod(0o755)
                        invalid = Path(temporary) / binary_name
                        if invalid_kind == "missing":
                            invalid.unlink()
                        elif invalid_kind == "directory":
                            invalid.unlink()
                            invalid.mkdir()
                        else:
                            invalid.chmod(0o644)
                        appdir = Path(temporary) / "ImageMD.AppDir"

                        with self.assertRaises((OSError, ValueError)):
                            build_appdir.create(stage, appdir, ffmpeg, ffprobe)

                        self.assertFalse(appdir.exists())


if __name__ == "__main__":
    unittest.main()
