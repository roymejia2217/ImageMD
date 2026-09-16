import importlib
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src import config
from src.media_ops import MediaMetadataManager


class TestFfmpegCommandContract(unittest.TestCase):
    def test_environment_configuration_uses_documented_defaults(self):
        keys = ("IMAGEMD_FFMPEG_EXECUTABLE", "IMAGEMD_FFPROBE_EXECUTABLE")
        original = {key: os.environ.get(key) for key in keys}
        was_present = {key: key in os.environ for key in keys}
        try:
            for key in keys:
                os.environ.pop(key, None)
            importlib.reload(config)
            self.assertEqual(config.FFMPEG_EXECUTABLE, "ffmpeg")
            self.assertEqual(config.FFPROBE_EXECUTABLE, "ffprobe")

            os.environ["IMAGEMD_FFMPEG_EXECUTABLE"] = "/opt/media/bin/ffmpeg-custom"
            os.environ["IMAGEMD_FFPROBE_EXECUTABLE"] = "/opt/media/bin/ffprobe-custom"
            importlib.reload(config)
            self.assertEqual(config.FFMPEG_EXECUTABLE, "/opt/media/bin/ffmpeg-custom")
            self.assertEqual(config.FFPROBE_EXECUTABLE, "/opt/media/bin/ffprobe-custom")
        finally:
            for key in keys:
                if was_present[key]:
                    os.environ[key] = original[key]
                else:
                    os.environ.pop(key, None)
            importlib.reload(config)

    def test_default_commands_are_injected_and_checked_independently(self):
        with patch(
            "src.media_ops.shutil.which",
            side_effect=lambda name: name if name == "ffprobe" else None,
        ) as which:
            manager = MediaMetadataManager()

        self.assertEqual(manager.ffmpeg_executable, "ffmpeg")
        self.assertEqual(manager.ffprobe_executable, "ffprobe")
        self.assertFalse(manager.ffmpeg_available)
        self.assertTrue(manager.ffprobe_available)
        self.assertEqual(
            which.call_args_list,
            [unittest.mock.call("ffmpeg"), unittest.mock.call("ffprobe")],
        )

    def test_explicit_executable_overrides_are_checked_independently(self):
        with patch(
            "src.media_ops.shutil.which",
            side_effect=lambda name: name if name == "/custom/probe" else None,
        ) as which:
            manager = MediaMetadataManager(
                ffmpeg_executable="/custom/encode",
                ffprobe_executable="/custom/probe",
            )

        self.assertEqual(manager.ffmpeg_executable, "/custom/encode")
        self.assertEqual(manager.ffprobe_executable, "/custom/probe")
        self.assertFalse(manager.ffmpeg_available)
        self.assertTrue(manager.ffprobe_available)
        self.assertEqual(
            which.call_args_list,
            [unittest.mock.call("/custom/encode"), unittest.mock.call("/custom/probe")],
        )

    def test_probe_uses_configured_ffprobe_command(self):
        manager = MediaMetadataManager(ffprobe_executable="/custom/probe")
        probe = {
            "format": {"tags": {"creation_time": "2024-03-04T05:06:07Z"}},
            "streams": [],
        }
        with (
            patch("src.media_ops.shutil.which", return_value="/custom/probe"),
            patch("src.media_ops.ffmpeg.probe", return_value=probe) as run_probe,
        ):
            manager.ffprobe_available = True
            date = manager._get_video_date("clip.mp4")

        self.assertEqual(date, datetime(2024, 3, 4, 5, 6, 7, tzinfo=timezone.utc))
        run_probe.assert_called_once_with("clip.mp4", cmd="/custom/probe")

    def test_staged_video_writer_uses_configured_ffmpeg_command(self):
        manager = MediaMetadataManager(ffmpeg_executable="/custom/encoder")
        manager.ffmpeg_available = True
        stream = MagicMock()
        stream.output.return_value.overwrite_output.return_value.run.return_value = None
        with (
            patch("src.media_ops.ffmpeg.input", return_value=stream),
            patch("src.media_ops.os.path.isfile", return_value=True),
        ):
            result = manager.write_metadata_to_stage(
                "/tmp/source.mov",
                "/tmp/stage.mov",
                datetime(2024, 3, 4, 5, 6, 7, tzinfo=timezone.utc),
            )

        self.assertTrue(result)
        stream.output.return_value.overwrite_output.return_value.run.assert_called_once_with(
            quiet=True, cmd="/custom/encoder"
        )

    def test_legacy_video_writer_uses_configured_ffmpeg_command(self):
        manager = MediaMetadataManager(ffmpeg_executable="/custom/encoder")
        manager.ffmpeg_available = True
        stream = MagicMock()
        stream.output.return_value.overwrite_output.return_value.run.return_value = None
        with (
            patch("src.media_ops.ffmpeg.input", return_value=stream),
            patch("src.media_ops.os.path.exists", return_value=True),
            patch("src.media_ops.os.remove"),
            patch("src.media_ops.os.rename"),
            patch("src.media_ops.shutil.copystat"),
        ):
            result = manager._update_video_date(
                "/tmp/source.mov", datetime(2024, 3, 4, 5, 6, 7, tzinfo=timezone.utc)
            )

        self.assertTrue(result)
        stream.output.return_value.overwrite_output.return_value.run.assert_called_once_with(
            quiet=True, cmd="/custom/encoder"
        )


if __name__ == "__main__":
    unittest.main()
