from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.media_ops import MediaMetadataManager


class TestStagedMediaWriter(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.source = self.parent / "source.jpg"
        self.source.write_bytes(b"source bytes")
        with patch("src.media_ops.shutil.which", return_value=None):
            self.manager = MediaMetadataManager()

    def test_rejects_relative_or_identical_paths_without_mutating_source(self):
        original = self.source.read_bytes()
        self.assertFalse(
            self.manager.write_metadata_to_stage(
                "source.jpg", str(self.parent / "x.jpg"), datetime.now()
            )
        )
        self.assertFalse(
            self.manager.write_metadata_to_stage(
                str(self.source), str(self.source), datetime.now()
            )
        )
        self.assertEqual(self.source.read_bytes(), original)

    def test_legacy_in_place_api_refuses_to_mutate_source(self):
        original = self.source.read_bytes()

        result = self.manager.update_metadata_date(
            str(self.source), datetime(2026, 1, 2)
        )

        self.assertFalse(result)
        self.assertEqual(self.source.read_bytes(), original)

    def test_jpeg_copies_then_writes_only_staged_path(self):
        staged = self.parent / "staged.jpg"
        with patch.object(
            self.manager, "_update_jpg_date", return_value=True
        ) as update:
            result = self.manager.write_metadata_to_stage(
                str(self.source), str(staged), datetime(2026, 1, 2)
            )
        self.assertTrue(result)
        self.assertEqual(self.source.read_bytes(), b"source bytes")
        self.assertEqual(staged.read_bytes(), b"source bytes")
        update.assert_called_once_with(str(staged), datetime(2026, 1, 2), silent=True)

    def test_video_requires_aware_date_without_invoking_ffmpeg(self):
        source = self.parent / "source.mov"
        staged = self.parent / "staged.stage.mov"
        source.write_bytes(b"video")
        with patch("src.media_ops.ffmpeg.input") as ffmpeg_input:
            result = self.manager.write_metadata_to_stage(
                str(source), str(staged), datetime(2026, 1, 2)
            )
        self.assertFalse(result)
        ffmpeg_input.assert_not_called()
        self.assertEqual(source.read_bytes(), b"video")

    def test_video_uses_staged_container_and_requires_output(self):
        source = self.parent / "source.mov"
        staged = self.parent / "staged.stage.mov"
        source.write_bytes(b"video")
        self.manager.ffmpeg_available = True
        stream = MagicMock()
        stream.output.return_value.overwrite_output.return_value.run.return_value = None
        with (
            patch("src.media_ops.ffmpeg.input", return_value=stream) as ffmpeg_input,
            patch("src.media_ops.os.path.isfile", return_value=True),
        ):
            result = self.manager.write_metadata_to_stage(
                str(source), str(staged), datetime(2026, 1, 2, tzinfo=timezone.utc)
            )
        self.assertTrue(result)
        ffmpeg_input.assert_called_once_with(str(source))
        stream.output.assert_called_once_with(
            str(staged), metadata="creation_time=2026-01-02T00:00:00Z", c="copy", map=0
        )
        self.assertEqual(source.read_bytes(), b"video")

    def test_video_fails_when_ffmpeg_does_not_create_staged_output(self):
        source = self.parent / "source.mov"
        staged = self.parent / "staged.stage.mov"
        source.write_bytes(b"video")
        self.manager.ffmpeg_available = True
        stream = MagicMock()
        stream.output.return_value.overwrite_output.return_value.run.return_value = None
        with (
            patch("src.media_ops.ffmpeg.input", return_value=stream),
            patch("src.media_ops.os.path.isfile", return_value=False),
        ):
            result = self.manager.write_metadata_to_stage(
                str(source), str(staged), datetime(2026, 1, 2, tzinfo=timezone.utc)
            )
        self.assertFalse(result)
        self.assertEqual(source.read_bytes(), b"video")


if __name__ == "__main__":
    unittest.main()
