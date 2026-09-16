"""Apply an approved metadata decision through staged, verified replacement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from src.application.date_decision import DateDecision, DecisionKind, TemporalPolicy
from src.application.ports import (
    CommitReceipt,
    ErrorCode,
    StagedMetadataWriter,
    StorageTransactionPort,
)
from src.domain.temporal import DateCandidate


class ApplyKind(str, Enum):
    APPLIED = "applied"
    REJECTED = "rejected"
    STAGING_FAILED = "staging_failed"
    WRITE_FAILED = "write_failed"
    COMMIT_FAILED = "commit_failed"


@dataclass(frozen=True, slots=True)
class ApplyPolicy:
    temporal: TemporalPolicy
    backup_suffix: str

    def __post_init__(self) -> None:
        if (
            not self.backup_suffix
            or "/" in self.backup_suffix
            or "\\" in self.backup_suffix
        ):
            raise ValueError("backup_suffix must be a non-empty filename suffix")


@dataclass(frozen=True, slots=True)
class ApplyResult:
    kind: ApplyKind
    receipt: CommitReceipt | None = None
    transaction_error: ErrorCode | None = None


class MetadataApplyService:
    """Bridge an approved plan to the staged storage transaction."""

    def __init__(
        self,
        writer: StagedMetadataWriter,
        policy: ApplyPolicy,
        storage: StorageTransactionPort,
    ) -> None:
        self._writer = writer
        self._policy = policy
        self._storage = storage

    def apply(self, source_path: str, decision: DateDecision) -> ApplyResult:
        if decision.kind is not DecisionKind.PROPOSE_UPDATE or decision.target is None:
            return ApplyResult(ApplyKind.REJECTED)
        snapshot_result = self._storage.snapshot_file(source_path)
        if not snapshot_result.succeeded or snapshot_result.value is None:
            return ApplyResult(
                ApplyKind.STAGING_FAILED, transaction_error=snapshot_result.error
            )
        staged_result = self._storage.create_staging_file(snapshot_result.value)
        if not staged_result.succeeded or staged_result.value is None:
            return ApplyResult(
                ApplyKind.STAGING_FAILED, transaction_error=staged_result.error
            )
        staged = staged_result.value
        target = self._writer_date(staged.source.path, decision.target)
        if target is None or not self._writer.write_metadata_to_stage(
            str(staged.source.path), str(staged.path), target
        ):
            self._storage.discard_staged_file(staged)
            return ApplyResult(ApplyKind.WRITE_FAILED)
        staged_snapshot = self._storage.snapshot_file(staged.path)
        if not staged_snapshot.succeeded or staged_snapshot.value is None:
            self._storage.discard_staged_file(staged)
            return ApplyResult(
                ApplyKind.COMMIT_FAILED, transaction_error=staged_snapshot.error
            )
        backup = Path(f"{staged.source.path}{self._policy.backup_suffix}")
        committed = self._storage.commit_staged_file(
            staged, staged_snapshot.value.sha256, backup
        )
        if not committed.succeeded:
            return ApplyResult(
                ApplyKind.COMMIT_FAILED, transaction_error=committed.error
            )
        return ApplyResult(ApplyKind.APPLIED, receipt=committed.value)

    def _writer_date(self, source: Path, candidate: DateCandidate) -> datetime | None:
        if source.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi"}:
            try:
                return candidate.as_instant(
                    self._policy.temporal.timezone,
                    self._policy.temporal.local_time_resolution,
                )
            except ValueError:
                return None
        if candidate.is_instant:
            return candidate.observed_at.astimezone(
                self._policy.temporal.timezone
            ).replace(tzinfo=None)
        return candidate.observed_at
