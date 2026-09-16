import unittest
from datetime import datetime
from unittest.mock import patch

from src.domain.temporal import DateSource
from src.media_ops import MediaMetadataManager


class TestMediaMetadataCandidates(unittest.TestCase):
    def make_manager(self) -> MediaMetadataManager:
        with patch("src.media_ops.shutil.which", return_value=None):
            return MediaMetadataManager()

    def test_exif_candidate_is_local_and_uses_standard_confidence(self):
        manager = self.make_manager()
        local_date = datetime(2024, 3, 4, 5, 6, 7)
        with (
            patch.object(manager, "_get_jpg_date", return_value=local_date),
            patch.object(
                manager,
                "_read_metadata_date",
                wraps=manager._read_metadata_date,
            ) as read_route,
        ):
            candidate = manager.get_metadata_candidate(
                "photo.jpg", standard_confidence=88, deep_scan_confidence=35
            )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.observed_at, local_date)
        self.assertIsNone(candidate.observed_at.tzinfo)
        self.assertIs(candidate.source, DateSource.EXIF)
        self.assertEqual(candidate.confidence, 88)
        self.assertEqual(candidate.evidence, "source:exif")
        self.assertNotIn("photo.jpg", candidate.evidence)
        self.assertEqual(read_route.call_count, 1)

    def test_video_z_candidate_preserves_utc_awareness(self):
        manager = self.make_manager()
        manager.ffmpeg_available = True
        probe = {
            "format": {"tags": {"creation_time": "2024-03-04T05:06:07Z"}},
            "streams": [],
        }
        with (
            patch("src.media_ops.ffmpeg.probe", return_value=probe),
            patch.object(
                manager,
                "_read_metadata_date",
                wraps=manager._read_metadata_date,
            ) as read_route,
        ):
            candidate = manager.get_metadata_candidate(
                "clip.mp4", standard_confidence=81, deep_scan_confidence=30
            )

        self.assertEqual(
            candidate.observed_at, datetime.fromisoformat("2024-03-04T05:06:07+00:00")
        )
        self.assertEqual(candidate.observed_at.utcoffset().total_seconds(), 0)
        self.assertIs(candidate.source, DateSource.VIDEO_METADATA)
        self.assertEqual(candidate.confidence, 81)
        self.assertEqual(read_route.call_count, 1)

    def test_video_without_offset_remains_local_naive(self):
        manager = self.make_manager()
        manager.ffmpeg_available = True
        probe = {
            "format": {"tags": {"creation_time": "2024-03-04 05:06:07"}},
            "streams": [],
        }
        with (
            patch("src.media_ops.ffmpeg.probe", return_value=probe),
            patch.object(
                manager,
                "_read_metadata_date",
                wraps=manager._read_metadata_date,
            ) as read_route,
        ):
            candidate = manager.get_metadata_candidate(
                "clip.mp4", standard_confidence=81, deep_scan_confidence=30
            )

        self.assertEqual(candidate.observed_at, datetime(2024, 3, 4, 5, 6, 7))
        self.assertIsNone(candidate.observed_at.tzinfo)
        self.assertIs(candidate.source, DateSource.VIDEO_METADATA)
        self.assertEqual(read_route.call_count, 1)

    def test_deep_scan_candidate_keeps_its_source_and_confidence(self):
        manager = self.make_manager()
        deep_date = datetime(2022, 8, 9, 10, 11, 12)
        with (
            patch.object(manager, "_get_non_jpg_date", return_value=None),
            patch.object(manager, "_get_jpg_date", return_value=None),
            patch.object(manager, "_deep_scan_date", return_value=deep_date),
            patch.object(
                manager,
                "_read_metadata_date",
                wraps=manager._read_metadata_date,
            ) as read_route,
        ):
            candidate = manager.get_metadata_candidate(
                "image.png", standard_confidence=90, deep_scan_confidence=25
            )

        self.assertEqual(candidate.observed_at, deep_date)
        self.assertIsNone(candidate.observed_at.tzinfo)
        self.assertIs(candidate.source, DateSource.DEEP_SCAN)
        self.assertEqual(candidate.confidence, 25)
        self.assertEqual(read_route.call_count, 1)

    def test_confidence_validation_is_enforced_by_date_candidate(self):
        manager = self.make_manager()
        with (
            patch.object(manager, "_get_jpg_date", return_value=datetime(2024, 1, 2)),
            patch.object(
                manager,
                "_read_metadata_date",
                wraps=manager._read_metadata_date,
            ) as read_route,
            self.assertRaises(ValueError),
        ):
            manager.get_metadata_candidate(
                "photo.jpg", standard_confidence=101, deep_scan_confidence=25
            )
        self.assertEqual(read_route.call_count, 1)

    def test_legacy_video_api_strips_timezone_and_reads_once(self):
        manager = self.make_manager()
        aware_date = datetime.fromisoformat("2024-03-04T05:06:07+02:00")
        with (
            patch.object(manager, "_get_video_date", return_value=aware_date),
            patch.object(
                manager,
                "_read_metadata_date",
                wraps=manager._read_metadata_date,
            ) as read_route,
        ):
            date = manager.get_metadata_date("clip.mov")

        self.assertEqual(date, datetime(2024, 3, 4, 5, 6, 7))
        self.assertIsNone(date.tzinfo)
        self.assertEqual(read_route.call_count, 1)


if __name__ == "__main__":
    unittest.main()
