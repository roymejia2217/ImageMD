"""Transactional repair of the known shifted-IHDR PNG corruption."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.application.ports import (
    CommitReceipt,
    ErrorCode,
    PngValidator,
    PngWriteKind,
    PngWriter,
    StorageTransactionPort,
)


class RepairKind(str, Enum):
    REPAIRED = "repaired"
    REJECTED = "rejected"
    STAGING_FAILED = "staging_failed"
    WRITE_FAILED = "write_failed"
    VALIDATION_FAILED = "validation_failed"
    COMMIT_FAILED = "commit_failed"


@dataclass(frozen=True, slots=True)
class RepairPolicy:
    backup_suffix: str

    def __post_init__(self) -> None:
        if (
            not self.backup_suffix
            or "/" in self.backup_suffix
            or "\\" in self.backup_suffix
        ):
            raise ValueError("backup_suffix must be a non-empty filename suffix")


@dataclass(frozen=True, slots=True)
class RepairResult:
    kind: RepairKind
    receipt: CommitReceipt | None = None
    transaction_error: ErrorCode | None = None


class PngRepairService:
    """Run repair in a private stage and commit it with a preserved backup."""

    def __init__(
        self,
        writer: PngWriter,
        policy: RepairPolicy,
        validator: PngValidator,
        storage: StorageTransactionPort,
    ) -> None:
        if policy is None:
            raise ValueError("an explicit backup suffix policy is required")
        self._writer = writer
        self._policy = policy
        self._validator = validator
        self._storage = storage

    def repair(self, source_path: str) -> RepairResult:
        source = Path(source_path)
        if source.suffix.lower() != ".png":
            return RepairResult(RepairKind.REJECTED)
        snapshot = self._storage.snapshot_file(source_path)
        if not snapshot.succeeded or snapshot.value is None:
            return RepairResult(
                RepairKind.STAGING_FAILED, transaction_error=snapshot.error
            )
        staged_result = self._storage.create_staging_file(snapshot.value)
        if not staged_result.succeeded or staged_result.value is None:
            return RepairResult(
                RepairKind.STAGING_FAILED, transaction_error=staged_result.error
            )
        staged = staged_result.value

        try:
            write_result = self._writer.write_repaired_png(
                str(staged.source.path), str(staged.path)
            )
        except Exception:
            self._storage.discard_staged_file(staged)
            return RepairResult(RepairKind.WRITE_FAILED)
        if not write_result.succeeded:
            self._storage.discard_staged_file(staged)
            kind = (
                RepairKind.REJECTED
                if write_result.kind is PngWriteKind.NOT_REPAIRABLE
                else RepairKind.VALIDATION_FAILED
                if write_result.kind is PngWriteKind.VALIDATION_FAILED
                else RepairKind.WRITE_FAILED
            )
            return RepairResult(kind)
        try:
            valid_stage = self._validator.is_valid(str(staged.path))
        except Exception:
            valid_stage = False
        if not valid_stage:
            self._storage.discard_staged_file(staged)
            return RepairResult(RepairKind.VALIDATION_FAILED)

        staged_snapshot = self._storage.snapshot_file(staged.path)
        if not staged_snapshot.succeeded or staged_snapshot.value is None:
            self._storage.discard_staged_file(staged)
            return RepairResult(
                RepairKind.COMMIT_FAILED, transaction_error=staged_snapshot.error
            )
        backup = Path(f"{staged.source.path}{self._policy.backup_suffix}")
        committed = self._storage.commit_staged_file(
            staged, staged_snapshot.value.sha256, backup
        )
        if not committed.succeeded:
            return RepairResult(
                RepairKind.COMMIT_FAILED, transaction_error=committed.error
            )
        return RepairResult(RepairKind.REPAIRED, receipt=committed.value)
