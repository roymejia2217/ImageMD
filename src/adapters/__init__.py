"""Filesystem adapters for controlled application side effects."""

from src.adapters.storage_transaction import (
    CommitReceipt,
    ErrorCode,
    FileSnapshot,
    OperationResult,
    StagedFile,
    commit_staged_file,
    create_staging_file,
    snapshot_file,
)

__all__ = [
    "CommitReceipt",
    "ErrorCode",
    "FileSnapshot",
    "OperationResult",
    "StagedFile",
    "commit_staged_file",
    "create_staging_file",
    "snapshot_file",
]
