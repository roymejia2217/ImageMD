from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from src.application.apply_metadata import ApplyKind, ApplyPolicy, MetadataApplyService
from src.application.date_decision import DateDecision, DecisionKind, TemporalPolicy
from src.domain.temporal import DateCandidate, DateSource


class WriterStub:
    def __init__(self, succeeds=True):
        self.succeeds, self.calls = succeeds, []

    def write_metadata_to_stage(self, source_path, staged_path, new_date):
        self.calls.append((source_path, staged_path, new_date))
        if self.succeeds:
            Path(staged_path).write_bytes(b"updated")
        return self.succeeds


class TestMetadataApplyService(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.policy = ApplyPolicy(
            TemporalPolicy(ZoneInfo("America/Guayaquil"), 0, 90), ".bak"
        )

    def decision(self, date):
        candidate = DateCandidate(date, DateSource.FILENAME, 95, "fixture")
        return DateDecision(DecisionKind.PROPOSE_UPDATE, candidate, "test")

    def test_applies_through_stage_and_keeps_backup(self):
        source = Path(self.temp.name) / "photo.jpg"
        source.write_bytes(b"original")
        writer = WriterStub()
        result = MetadataApplyService(writer, self.policy).apply(
            str(source), self.decision(datetime(2026, 1, 2, 3, 4, 5))
        )
        self.assertEqual(result.kind, ApplyKind.APPLIED)
        self.assertEqual(source.read_bytes(), b"updated")
        self.assertEqual((Path(f"{source}.bak")).read_bytes(), b"original")
        self.assertEqual(writer.calls[0][2].tzinfo, None)
        self.assertEqual(Path(writer.calls[0][1]).suffix, ".jpg")

    def test_rejects_any_non_approved_decision(self):
        source = Path(self.temp.name) / "photo.jpg"
        source.write_bytes(b"original")
        writer = WriterStub()
        result = MetadataApplyService(writer, self.policy).apply(
            str(source), DateDecision(DecisionKind.REQUIRE_REVIEW, None, "review")
        )
        self.assertEqual(result.kind, ApplyKind.REJECTED)
        self.assertEqual(writer.calls, [])
        self.assertEqual(source.read_bytes(), b"original")

    def test_writer_failure_preserves_source_and_removes_stage(self):
        source = Path(self.temp.name) / "photo.jpg"
        source.write_bytes(b"original")
        result = MetadataApplyService(WriterStub(False), self.policy).apply(
            str(source), self.decision(datetime(2026, 1, 2))
        )
        self.assertEqual(result.kind, ApplyKind.WRITE_FAILED)
        self.assertEqual(source.read_bytes(), b"original")
        self.assertEqual(list(Path(self.temp.name).glob("*.stage*")), [])

    def test_local_video_date_is_resolved_to_utc_for_writer(self):
        source = Path(self.temp.name) / "clip.mov"
        source.write_bytes(b"original")
        writer = WriterStub()
        result = MetadataApplyService(writer, self.policy).apply(
            str(source), self.decision(datetime(2026, 1, 2, 12, 0, 0))
        )
        self.assertEqual(result.kind, ApplyKind.APPLIED)
        self.assertEqual(
            writer.calls[0][2], datetime(2026, 1, 2, 17, tzinfo=timezone.utc)
        )

    def test_invalid_backup_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            ApplyPolicy(self.policy.temporal, "nested/name")


if __name__ == "__main__":
    unittest.main()
