from datetime import datetime, timezone
import unittest
from zoneinfo import ZoneInfo

from src.application.date_decision import (
    DateDecisionPlanner,
    DecisionKind,
    TemporalPolicy,
)
from src.domain.temporal import DateCandidate, DateSource


class TestDateDecisionPlanner(unittest.TestCase):
    def setUp(self):
        self.planner = DateDecisionPlanner(
            TemporalPolicy(
                timezone=ZoneInfo("America/Guayaquil"),
                tolerance_seconds=60,
                automatic_write_confidence=90,
            )
        )

    @staticmethod
    def candidate(value, source=DateSource.FILENAME, confidence=95):
        return DateCandidate(value, source, confidence, "fixture")

    def test_matching_local_filename_and_utc_metadata_need_no_action(self):
        decision = self.planner.plan(
            self.candidate(datetime(2026, 2, 8, 12, 0, 0)),
            self.candidate(
                datetime(2026, 2, 8, 17, 0, 30, tzinfo=timezone.utc),
                DateSource.VIDEO_METADATA,
            ),
        )
        self.assertEqual(decision.kind, DecisionKind.NO_ACTION)

    def test_high_confidence_difference_proposes_update_without_writing(self):
        preferred = self.candidate(datetime(2026, 2, 8, 12, 0, 0))
        decision = self.planner.plan(
            preferred,
            self.candidate(
                datetime(2026, 2, 8, 18, 0, 0, tzinfo=timezone.utc), DateSource.EXIF
            ),
        )
        self.assertEqual(decision.kind, DecisionKind.PROPOSE_UPDATE)
        self.assertEqual(decision.target, preferred)

    def test_low_confidence_candidate_requires_review(self):
        decision = self.planner.plan(
            self.candidate(datetime(2026, 2, 8, 12, 0, 0), confidence=30),
            None,
        )
        self.assertEqual(decision.kind, DecisionKind.REQUIRE_REVIEW)

    def test_deep_scan_never_proposes_automatic_update(self):
        decision = self.planner.plan(
            self.candidate(datetime(2026, 2, 8, 12, 0, 0), DateSource.DEEP_SCAN, 100),
            None,
        )
        self.assertEqual(decision.kind, DecisionKind.REQUIRE_REVIEW)

    def test_deep_scan_observation_cannot_authorize_an_automatic_update(self):
        decision = self.planner.plan(
            self.candidate(datetime(2026, 2, 8, 12, 0, 0)),
            self.candidate(datetime(2026, 2, 8, 18, 0, 0), DateSource.DEEP_SCAN, 100),
        )
        self.assertEqual(decision.kind, DecisionKind.REQUIRE_REVIEW)

    def test_ambiguous_wall_time_requires_review(self):
        planner = DateDecisionPlanner(
            TemporalPolicy(
                timezone=ZoneInfo("America/New_York"),
                tolerance_seconds=0,
                automatic_write_confidence=90,
            )
        )
        decision = planner.plan(
            self.candidate(datetime(2026, 11, 1, 1, 30)),
            self.candidate(
                datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc),
                DateSource.VIDEO_METADATA,
            ),
        )
        self.assertEqual(decision.kind, DecisionKind.REQUIRE_REVIEW)

    def test_no_candidates_is_insufficient_evidence(self):
        decision = self.planner.plan(None, None)
        self.assertEqual(decision.kind, DecisionKind.INSUFFICIENT_EVIDENCE)


if __name__ == "__main__":
    unittest.main()
