"""Safe local-file replacement with snapshot validation and a preserved backup."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Generic, TypeVar


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


def snapshot_file(path: str | os.PathLike[str]) -> OperationResult[FileSnapshot]:
    """Capture the absolute path, size and SHA-256 of a regular source file."""

    normalized = _validated_absolute_path(path)
    if normalized is None or normalized.is_dir() or normalized.is_symlink():
        return OperationResult(None, ErrorCode.INVALID_PATH)
    try:
        before = normalized.stat()
    except FileNotFoundError:
        return OperationResult(None, ErrorCode.NOT_FOUND)
    except OSError:
        return OperationResult(None, ErrorCode.IO_ERROR)
    if not stat.S_ISREG(before.st_mode):
        return OperationResult(None, ErrorCode.INVALID_PATH)
    try:
        digest, size = _digest_file(normalized)
        after = normalized.stat()
    except FileNotFoundError:
        return OperationResult(None, ErrorCode.NOT_FOUND)
    except OSError:
        return OperationResult(None, ErrorCode.IO_ERROR)
    if not _same_file_state(before, after) or size != before.st_size:
        return OperationResult(None, ErrorCode.SOURCE_CHANGED)
    return OperationResult(FileSnapshot(normalized, size, digest))


def create_staging_file(snapshot: FileSnapshot) -> OperationResult[StagedFile]:
    """Create a private empty staging file beside the snapshotted source."""

    if (
        not isinstance(snapshot, FileSnapshot)
        or not snapshot.path.is_absolute()
        or snapshot.path.is_dir()
        or snapshot.path.is_symlink()
    ):
        return OperationResult(None, ErrorCode.INVALID_PATH)
    descriptor = -1
    name: str | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{snapshot.path.name}.imagemd-",
            suffix=f".stage{snapshot.path.suffix}",
            dir=snapshot.path.parent,
        )
        os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        descriptor = -1
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        if name is not None:
            _remove_file(Path(name))
        return OperationResult(None, ErrorCode.IO_ERROR)
    assert name is not None
    return OperationResult(StagedFile(snapshot, Path(name)))


def commit_staged_file(
    staged: StagedFile,
    expected_sha256: str,
    backup_path: str | os.PathLike[str],
) -> OperationResult[CommitReceipt]:
    """Validate source and staged bytes, preserve a backup, then atomically replace."""

    if not isinstance(staged, StagedFile):
        return OperationResult(None, ErrorCode.INVALID_PATH)
    source = staged.source.path
    stage = _validated_absolute_path(staged.path)
    backup = _validated_absolute_path(backup_path)
    if (
        not source.is_absolute()
        or stage is None
        or backup is None
        or source.is_dir()
        or source.is_symlink()
        or stage.is_dir()
        or stage.is_symlink()
        or backup.is_dir()
    ):
        return _failure_after_cleanup(staged.path, ErrorCode.INVALID_PATH)
    if not _valid_digest(expected_sha256):
        return _failure_after_cleanup(stage, ErrorCode.STAGED_DIGEST_MISMATCH)
    if stage.parent != source.parent or backup.parent != source.parent:
        return _failure_after_cleanup(stage, ErrorCode.BACKUP_PATH_INVALID)
    if stage == source or backup == source or backup == stage:
        return _failure_after_cleanup(stage, ErrorCode.BACKUP_PATH_INVALID)
    if backup.exists():
        return _failure_after_cleanup(stage, ErrorCode.BACKUP_EXISTS)

    source_check = snapshot_file(source)
    if not source_check.succeeded or source_check.value != staged.source:
        return _failure_after_cleanup(stage, ErrorCode.SOURCE_CHANGED)
    try:
        staged_digest, staged_size = _digest_file(stage)
    except OSError:
        return _failure_after_cleanup(stage, ErrorCode.IO_ERROR)
    if staged_digest != expected_sha256:
        return _failure_after_cleanup(stage, ErrorCode.STAGED_DIGEST_MISMATCH)

    try:
        _copy_backup_exclusively(source, backup)
    except FileExistsError:
        return _failure_after_cleanup(stage, ErrorCode.BACKUP_EXISTS)
    except OSError:
        return _failure_after_cleanup(stage, ErrorCode.IO_ERROR)

    source_check = snapshot_file(source)
    if not source_check.succeeded or source_check.value != staged.source:
        return _failure_after_cleanup(stage, ErrorCode.SOURCE_CHANGED, backup)
    try:
        os.replace(stage, source)
    except OSError:
        return _failure_after_cleanup(stage, ErrorCode.REPLACE_FAILED, backup)

    return OperationResult(
        CommitReceipt(
            path=source,
            backup_path=backup,
            previous_size=staged.source.size,
            previous_sha256=staged.source.sha256,
            committed_size=staged_size,
            committed_sha256=staged_digest,
        )
    )


def _validated_absolute_path(path: str | os.PathLike[str]) -> Path | None:
    try:
        candidate = Path(path)
    except (TypeError, ValueError):
        return None
    if not candidate.is_absolute():
        return None
    return Path(os.path.abspath(candidate))


def _digest_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _same_file_state(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev == after.st_dev
        and before.st_ino == after.st_ino
        and before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
    )


def _valid_digest(digest: str) -> bool:
    return (
        isinstance(digest, str)
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
    )


def _copy_backup_exclusively(source: Path, backup: Path) -> None:
    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output_stream:
            with source.open("rb") as input_stream:
                shutil.copyfileobj(input_stream, output_stream)
        shutil.copystat(source, backup, follow_symlinks=False)
    except OSError:
        _remove_file(backup)
        raise


def _remove_file(path: Path) -> bool:
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
        return True
    except OSError:
        return False


def _failure_after_cleanup(
    staged_path: Path,
    code: ErrorCode,
    backup_path: Path | None = None,
) -> OperationResult[T]:
    staging_clean = _remove_file(staged_path)
    backup_clean = backup_path is None or _remove_file(backup_path)
    if not staging_clean or not backup_clean:
        return OperationResult(None, ErrorCode.CLEANUP_FAILED)
    return OperationResult(None, code)
