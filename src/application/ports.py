"""Application-owned contracts for storage transactions and PNG repair."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import os
from pathlib import Path
from typing import Generic, Protocol, TypeVar


T = TypeVar("T")


class ErrorCode(str, Enum):
    INVALID_PATH = "invalid_path"
    NOT_FOUND = "not_found"
    IO_ERROR = "io_error"
    SOURCE_CHANGED = "source_changed"
    STAGED_DIGEST_MISMATCH = "staged_digest_mismatch"
    BACKUP_EXISTS = "backup_exists"
    BACKUP_PATH_INVALID = "backup_path_invalid"
    REPLACE_FAILED = "replace_failed"
    CLEANUP_FAILED = "cleanup_failed"


@dataclass(frozen=True, slots=True)
class OperationResult(Generic[T]):
    value: T | None
    error: ErrorCode | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    path: Path
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class StagedFile:
    source: FileSnapshot
    path: Path


@dataclass(frozen=True, slots=True)
class CommitReceipt:
    path: Path
    backup_path: Path
    previous_size: int
    previous_sha256: str
    committed_size: int
    committed_sha256: str


class PngWriteKind(str, Enum):
    WRITTEN = "written"
    NOT_REPAIRABLE = "not_repairable"
    WRITE_FAILED = "write_failed"
    VALIDATION_FAILED = "validation_failed"


@dataclass(frozen=True, slots=True)
class PngWriteResult:
    kind: PngWriteKind

    @property
    def succeeded(self) -> bool:
        return self.kind is PngWriteKind.WRITTEN


class StorageTransactionPort(Protocol):
    def snapshot_file(
        self, path: str | os.PathLike[str]
    ) -> OperationResult[FileSnapshot]: ...

    def create_staging_file(
        self, snapshot: FileSnapshot
    ) -> OperationResult[StagedFile]: ...

    def commit_staged_file(
        self,
        staged: StagedFile,
        expected_sha256: str,
        backup_path: str | os.PathLike[str],
    ) -> OperationResult[CommitReceipt]: ...

    def discard_staged_file(self, staged: StagedFile) -> bool: ...


class StagedMetadataWriter(Protocol):
    def write_metadata_to_stage(
        self, source_path: str, staged_path: str, new_date: datetime
    ) -> bool: ...


class PngWriter(Protocol):
    def write_repaired_png(
        self, source_path: str, staged_path: str
    ) -> PngWriteResult: ...


class PngValidator(Protocol):
    def is_valid(self, path: str) -> bool: ...
