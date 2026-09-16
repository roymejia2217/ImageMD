import unittest
from datetime import datetime, timezone
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.date_utils import DateExtractor
from src.domain.temporal import DateSource


class TestDatePatterns(unittest.TestCase):
    def setUp(self):
        self.extractor = DateExtractor()

    def assertDate(
        self,
        filename,
        expected_year,
        expected_month,
        expected_day,
        expected_hour=None,
        expected_minute=None,
        expected_second=None,
    ):
        dt, has_time = self.extractor.extract_date(filename)
        self.assertIsNotNone(dt, f"Failed to extract date from: {filename}")

        self.assertEqual(dt.year, expected_year, f"Year mismatch for {filename}")
        self.assertEqual(dt.month, expected_month, f"Month mismatch for {filename}")
        self.assertEqual(dt.day, expected_day, f"Day mismatch for {filename}")

        if expected_hour is not None:
            self.assertEqual(dt.hour, expected_hour, f"Hour mismatch for {filename}")
            self.assertEqual(
                dt.minute, expected_minute, f"Minute mismatch for {filename}"
            )
            if expected_second is not None:
                self.assertEqual(
                    dt.second, expected_second, f"Second mismatch for {filename}"
                )

    def test_existing_patterns(self):
        # WhatsApp Spanish
        self.assertDate(
            "Imagen de WhatsApp 2024-08-26 a las 17.24.54_97e752ef.jpg",
            2024,
            8,
            26,
            17,
            24,
            54,
        )
        # WhatsApp English
        self.assertDate(
            "WhatsApp Image 2024-01-01 at 12.00.00.jpeg", 2024, 1, 1, 12, 0, 0
        )
        # Facebook
        self.assertDate("FB_IMG_1541718757550.jpg", 2018, 11, 8)  # UTC date roughly

    def test_new_requirements(self):
        # 1. Signal Mobile (signal-YYYY-MM-DD-HHMM.jpg)
        self.assertDate("signal-2023-05-20-1430.jpg", 2023, 5, 20, 14, 30, 0)

        # 2. Signal Desktop (signal-yyyy-mm-dd-hhmmss.ext)
        self.assertDate("signal-2023-05-20-143055.jpg", 2023, 5, 20, 14, 30, 55)

        # 3. Telegram (photo_YYYY-MM-DD_HH-MM-SS.jpg)
        self.assertDate("photo_2023-11-29_10-20-30.jpg", 2023, 11, 29, 10, 20, 30)

        # 4. iOS Screenshot (Screenshot YYYY-MM-DD at HH.MM.SS.png)
        # Note: Often "Screenshot YYYY-MM-DD at HH.MM.SS.png"
        self.assertDate("Screenshot 2023-01-25 at 19.00.00.png", 2023, 1, 25, 19, 0, 0)

        # 5. Generic format often found in downloads: YYYY-MM-DD_HH-MM-SS (Underscore separator)
        self.assertDate("2023-11-29_10-20-30.jpg", 2023, 11, 29, 10, 20, 30)

    def test_extract_date_compatibility(self):
        whatsapp_dt, whatsapp_has_time = self.extractor.extract_date(
            "WhatsApp Image 2024-01-01 at 12.00.00.jpeg"
        )
        self.assertEqual(whatsapp_dt, datetime(2024, 1, 1, 12, 0, 0))
        self.assertIsNone(whatsapp_dt.tzinfo)
        self.assertTrue(whatsapp_has_time)

        facebook_dt, facebook_has_time = self.extractor.extract_date(
            "FB_IMG_1541718757550.jpg"
        )
        self.assertEqual(facebook_dt, datetime(2018, 11, 8, 23, 12, 37, 550000))
        self.assertIsNone(facebook_dt.tzinfo)
        self.assertTrue(facebook_has_time)

    def test_whatsapp_candidate_preserves_local_semantics(self):
        candidate = self.extractor.extract_candidate(
            "WhatsApp Image 2024-01-01 at 12.00.00.jpeg", confidence=87
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.observed_at, datetime(2024, 1, 1, 12, 0, 0))
        self.assertIsNone(candidate.observed_at.tzinfo)
        self.assertIs(candidate.source, DateSource.FILENAME)
        self.assertEqual(candidate.confidence, 87)
        self.assertEqual(
            candidate.evidence,
            "filename-pattern:%Y-%m-%d %H.%M.%S:2024-01-01T12:00:00",
        )
        self.assertNotIn("WhatsApp Image", candidate.evidence)
        self.assertNotIn("/", candidate.evidence)

    def test_facebook_candidate_is_aware_utc_instant(self):
        candidate = self.extractor.extract_candidate(
            "FB_IMG_1541718757550.jpg", confidence=91
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(
            candidate.observed_at,
            datetime(2018, 11, 8, 23, 12, 37, 550000, tzinfo=timezone.utc),
        )
        self.assertIs(candidate.observed_at.tzinfo, timezone.utc)
        self.assertIs(candidate.source, DateSource.FILENAME)

    def test_candidate_rejects_invalid_confidence(self):
        with self.assertRaises(ValueError):
            self.extractor.extract_candidate(
                "WhatsApp Image 2024-01-01 at 12.00.00.jpeg", confidence=101
            )

    def test_candidate_returns_none_for_unmatched_filename(self):
        self.assertIsNone(
            self.extractor.extract_candidate("photo-without-date.jpg", confidence=80)
        )


if __name__ == "__main__":
    unittest.main()
