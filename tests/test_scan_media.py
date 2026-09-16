from datetime import datetime, timezone
import unittest
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from src.application.date_decision import DecisionKind, TemporalPolicy
from src.application.scan_media import MediaScanService, ScanPolicy, ScanResult
from src.domain.temporal import DateCandidate, DateSource


class TestMediaScanService(unittest.TestCase):
    def setUp(self):
        self.extractor = Mock()
        self.metadata_reader = Mock()
        self.service = MediaScanService(
            self.extractor,
            self.metadata_reader,
            TemporalPolicy(
                timezone=ZoneInfo("America/Guayaquil"),
                tolerance_seconds=60,
                automatic_write_confidence=90,
            ),
            ScanPolicy(
                filename_confidence=95,
                standard_metadata_confidence=90,
                deep_scan_confidence=30,
            ),
        )

    @staticmethod
    def candidate(value, source=DateSource.FILENAME, confidence=95):
        return DateCandidate(value, source, confidence, "test-fixture")

    def assert_dependencies_called_once(self):
        self.assertEqual(self.extractor.extract_candidate.call_count, 1)
        self.assertEqual(self.metadata_reader.get_metadata_candidate.call_count, 1)

    def test_matching_candidates_need_no_action(self):
        preferred = self.candidate(datetime(2026, 2, 8, 12, 0, 0))
        observed = self.candidate(
            datetime(2026, 2, 8, 17, 0, 30, tzinfo=timezone.utc),
            DateSource.EXIF,
            90,
        )
        self.extractor.extract_candidate.return_value = preferred
        self.metadata_reader.get_metadata_candidate.return_value = observed

        result = self.service.scan("photo-2026.jpg", "/media/photo.jpg")

        self.assertIsInstance(result, ScanResult)
        self.assertIs(result.preferred_candidate, preferred)
        self.assertIs(result.observed_candidate, observed)
        self.assertEqual(result.decision.kind, DecisionKind.NO_ACTION)
        self.assert_dependencies_called_once()

    def test_high_confidence_discrepancy_proposes_update(self):
        preferred = self.candidate(datetime(2026, 2, 8, 12, 0, 0))
        observed = self.candidate(
            datetime(2026, 2, 8, 18, 0, 0, tzinfo=timezone.utc),
            DateSource.EXIF,
            90,
        )
        self.extractor.extract_candidate.return_value = preferred
        self.metadata_reader.get_metadata_candidate.return_value = observed

        result = self.service.scan("photo-2026.jpg", "/media/photo.jpg")

        self.assertEqual(result.decision.kind, DecisionKind.PROPOSE_UPDATE)
        self.assertIs(result.decision.target, preferred)
        self.assert_dependencies_called_once()

    def test_deep_scan_observation_requires_review(self):
        preferred = self.candidate(datetime(2026, 2, 8, 12, 0, 0))
        observed = self.candidate(
            datetime(2026, 2, 8, 18, 0, 0), DateSource.DEEP_SCAN, 30
        )
        self.extractor.extract_candidate.return_value = preferred
        self.metadata_reader.get_metadata_candidate.return_value = observed

        result = self.service.scan("photo-2026.jpg", "/media/photo.jpg")

        self.assertEqual(result.decision.kind, DecisionKind.REQUIRE_REVIEW)
        self.assertIs(result.preferred_candidate, preferred)
        self.assertIs(result.observed_candidate, observed)
        self.assert_dependencies_called_once()

    def test_no_candidates_is_insufficient_evidence(self):
        self.extractor.extract_candidate.return_value = None
        self.metadata_reader.get_metadata_candidate.return_value = None

        result = self.service.scan("photo.jpg", "/media/photo.jpg")

        self.assertEqual(result.decision.kind, DecisionKind.INSUFFICIENT_EVIDENCE)
        self.assertIsNone(result.preferred_candidate)
        self.assertIsNone(result.observed_candidate)
        self.assert_dependencies_called_once()

    def test_each_dependency_receives_configured_parameters_once(self):
        self.extractor.extract_candidate.return_value = None
        self.metadata_reader.get_metadata_candidate.return_value = None

        self.service.scan("photo.jpg", "/media/photo.jpg")

        self.extractor.extract_candidate.assert_called_once_with(
            "photo.jpg", confidence=95
        )
        self.metadata_reader.get_metadata_candidate.assert_called_once_with(
            "/media/photo.jpg",
            standard_confidence=90,
            deep_scan_confidence=30,
        )

    def test_metadata_reader_error_propagates(self):
        self.extractor.extract_candidate.return_value = None
        self.metadata_reader.get_metadata_candidate.side_effect = OSError("read failed")

        with self.assertRaisesRegex(OSError, "read failed"):
            self.service.scan("photo.jpg", "/media/photo.jpg")

        self.assert_dependencies_called_once()

    def test_invalid_confidence_is_rejected(self):
        for confidence in (-1, 101, True, 1.5):
            with self.subTest(confidence=confidence):
                with self.assertRaises(ValueError):
                    ScanPolicy(confidence, 90, 30)


if __name__ == "__main__":
    unittest.main()
