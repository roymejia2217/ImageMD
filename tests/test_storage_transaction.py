import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.adapters.storage_transaction import (
    ErrorCode,
    commit_staged_file,
    create_staging_file,
    snapshot_file,
)


class TestStorageTransaction(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.parent = Path(self.temporary_directory.name)
        self.source = self.parent / "image.jpg"
        self.original = b"original bytes"
        self.source.write_bytes(self.original)
        result = snapshot_file(self.source)
        self.assertTrue(result.succeeded)
        self.snapshot = result.value

    def stage(self, content):
        result = create_staging_file(self.snapshot)
        self.assertTrue(result.succeeded)
        staged = result.value
        staged.path.write_bytes(content)
        return staged

    def test_success_returns_receipt_and_preserves_backup(self):
        updated = b"updated image bytes"
        backup = self.parent / "image.jpg.backup"
        result = commit_staged_file(
            self.stage(updated), hashlib.sha256(updated).hexdigest(), backup
        )

        self.assertTrue(result.succeeded)
        self.assertEqual(self.source.read_bytes(), updated)
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertEqual(
            result.value.previous_sha256, hashlib.sha256(self.original).hexdigest()
        )
        self.assertEqual(
            result.value.committed_sha256, hashlib.sha256(updated).hexdigest()
        )
        self.assertEqual(result.value.backup_path, backup)

    def test_source_changed_after_snapshot_is_rejected_without_replacing_source(self):
        staged = self.stage(b"replacement")
        changed = b"changed after snapshot"
        self.source.write_bytes(changed)

        result = commit_staged_file(
            staged,
            hashlib.sha256(b"replacement").hexdigest(),
            self.parent / "backup",
        )

        self.assertEqual(result.error, ErrorCode.SOURCE_CHANGED)
        self.assertEqual(self.source.read_bytes(), changed)
        self.assertFalse(staged.path.exists())

    def test_staged_digest_mismatch_is_rejected_and_staging_is_removed(self):
        staged = self.stage(b"actual staged content")

        result = commit_staged_file(
            staged,
            hashlib.sha256(b"different expected content").hexdigest(),
            self.parent / "backup",
        )

        self.assertEqual(result.error, ErrorCode.STAGED_DIGEST_MISMATCH)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse(staged.path.exists())

    def test_relative_and_directory_source_paths_are_rejected(self):
        relative = snapshot_file(Path("relative-image.jpg"))
        directory = snapshot_file(self.parent)

        self.assertEqual(relative.error, ErrorCode.INVALID_PATH)
        self.assertEqual(directory.error, ErrorCode.INVALID_PATH)

    def test_staging_and_backup_are_in_source_parent(self):
        staged = self.stage(b"replacement")
        backup = self.parent / "backup"

        self.assertEqual(staged.path.parent, self.source.parent)
        self.assertEqual(staged.path.suffix, self.source.suffix)
        self.assertEqual(staged.path.stat().st_mode & 0o777, 0o600)
        result = commit_staged_file(
            staged, hashlib.sha256(b"replacement").hexdigest(), backup
        )

        self.assertTrue(result.succeeded)
        self.assertEqual(backup.parent, self.source.parent)

    def test_replace_failure_preserves_source_and_cleans_staging(self):
        staged = self.stage(b"replacement")
        backup = self.parent / "backup"

        with patch(
            "src.adapters.storage_transaction.os.replace",
            side_effect=OSError("injected"),
        ):
            result = commit_staged_file(
                staged,
                hashlib.sha256(b"replacement").hexdigest(),
                backup,
            )

        self.assertEqual(result.error, ErrorCode.REPLACE_FAILED)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse(staged.path.exists())
        self.assertFalse(backup.exists())


if __name__ == "__main__":
    unittest.main()
