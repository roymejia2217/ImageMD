from datetime import datetime, timezone
import unittest
from zoneinfo import ZoneInfo

from src.domain.temporal import (
    AmbiguousLocalTimeError,
    CandidateComparison,
    DateCandidate,
    DateSource,
    LocalTimeResolution,
    NonexistentLocalTimeError,
    compare_candidates,
)


class TestDateCandidate(unittest.TestCase):
    def candidate(self, observed_at: datetime) -> DateCandidate:
        return DateCandidate(observed_at, DateSource.FILENAME, 90, "fixture")

    def test_utc_and_equivalent_local_time_match(self):
        local = self.candidate(datetime(2026, 2, 8, 12, 0, 0))
        utc = DateCandidate(
            datetime(2026, 2, 8, 17, 0, 0, tzinfo=timezone.utc),
            DateSource.VIDEO_METADATA,
            95,
            "creation_time",
        )
        result = compare_candidates(
            local,
            utc,
            tolerance_seconds=0,
            zone=ZoneInfo("America/Guayaquil"),
        )
        self.assertEqual(result, CandidateComparison.MATCH)

    def test_local_value_requires_timezone_policy(self):
        candidate = self.candidate(datetime(2026, 2, 8, 12, 0, 0))
        with self.assertRaises(ValueError):
            candidate.as_instant()

    def test_nonexistent_dst_time_is_rejected(self):
        candidate = self.candidate(datetime(2026, 3, 8, 2, 30, 0))
        with self.assertRaises(NonexistentLocalTimeError):
            candidate.as_instant(ZoneInfo("America/New_York"))

    def test_ambiguous_dst_time_requires_explicit_policy(self):
        candidate = self.candidate(datetime(2026, 11, 1, 1, 30, 0))
        zone = ZoneInfo("America/New_York")
        with self.assertRaises(AmbiguousLocalTimeError):
            candidate.as_instant(zone)
        earliest = candidate.as_instant(zone, LocalTimeResolution.EARLIEST)
        latest = candidate.as_instant(zone, LocalTimeResolution.LATEST)
        self.assertLess(earliest, latest)

    def test_ambiguous_values_are_incomparable_without_policy(self):
        ambiguous = self.candidate(datetime(2026, 11, 1, 1, 30, 0))
        utc = DateCandidate(
            datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc),
            DateSource.VIDEO_METADATA,
            95,
            "creation_time",
        )
        result = compare_candidates(
            ambiguous,
            utc,
            tolerance_seconds=0,
            zone=ZoneInfo("America/New_York"),
        )
        self.assertEqual(result, CandidateComparison.INCOMPARABLE)

    def test_invalid_confidence_is_rejected(self):
        with self.assertRaises(ValueError):
            DateCandidate(datetime(2026, 1, 1), DateSource.FILENAME, 101, "fixture")


if __name__ == "__main__":
    unittest.main()
