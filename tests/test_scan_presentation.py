from datetime import datetime
import unittest

from src.application.date_decision import DateDecision, DecisionKind
from src.application.scan_media import ScanResult
from src.application.scan_presentation import ScanPresentationKind, present_scan
from src.domain.temporal import DateCandidate, DateSource


class TestScanPresentation(unittest.TestCase):
    @staticmethod
    def candidate() -> DateCandidate:
        return DateCandidate(
            datetime(2026, 2, 8, 12), DateSource.FILENAME, 95, "fixture"
        )

    def test_proposal_is_the_only_non_repair_auto_action(self):
        candidate = self.candidate()
        result = ScanResult(
            candidate,
            None,
            DateDecision(DecisionKind.PROPOSE_UPDATE, candidate, "fixture"),
        )

        presentation = present_scan(result, is_corrupted=False)

        self.assertEqual(presentation.kind, ScanPresentationKind.NO_METADATA)
        self.assertTrue(presentation.action_needed)
        self.assertFalse(presentation.needs_repair)

    def test_review_is_not_queued_for_automatic_mutation(self):
        candidate = self.candidate()
        result = ScanResult(
            candidate,
            None,
            DateDecision(DecisionKind.REQUIRE_REVIEW, candidate, "ambiguous"),
        )

        presentation = present_scan(result, is_corrupted=False)

        self.assertEqual(presentation.kind, ScanPresentationKind.REVIEW_REQUIRED)
        self.assertFalse(presentation.action_needed)

    def test_corruption_requires_transactional_repair(self):
        result = ScanResult(
            None,
            None,
            DateDecision(DecisionKind.INSUFFICIENT_EVIDENCE, None, "none"),
        )

        presentation = present_scan(result, is_corrupted=True)

        self.assertEqual(presentation.kind, ScanPresentationKind.CORRUPT)
        self.assertTrue(presentation.action_needed)
        self.assertTrue(presentation.needs_repair)


if __name__ == "__main__":
    unittest.main()
