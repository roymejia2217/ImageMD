from pathlib import Path
import hashlib
import importlib.util
import os
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "packaging" / "write_checksums.py"
SPEC = importlib.util.spec_from_file_location("write_checksums", MODULE_PATH)
assert SPEC and SPEC.loader
write_checksums_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(write_checksums_module)


class TestWriteChecksums(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.artifacts = Path(self.temp.name) / "artifacts"
        self.artifacts.mkdir()
        self.output = self.artifacts / "SHA256SUMS"

    def test_writes_sorted_sha256_records_for_direct_regular_files(self):
        (self.artifacts / "zeta.bin").write_bytes(b"zeta")
        (self.artifacts / "alpha.bin").write_bytes(b"alpha")
        nested = self.artifacts / "nested"
        nested.mkdir()
        (nested / "ignored.bin").write_bytes(b"nested")

        result = write_checksums_module.write_checksums(self.artifacts, self.output)

        expected = "".join(
            f"{hashlib.sha256(contents).hexdigest()}  {name}\n"
            for name, contents in (("alpha.bin", b"alpha"), ("zeta.bin", b"zeta"))
        )
        self.assertEqual(result, self.output)
        self.assertEqual(self.output.read_text(encoding="utf-8"), expected)

    def test_rejects_existing_output(self):
        self.output.write_text("preserve", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            write_checksums_module.write_checksums(self.artifacts, self.output)

        self.assertEqual(self.output.read_text(encoding="utf-8"), "preserve")

    def test_removes_output_when_hashing_second_artifact_fails(self):
        (self.artifacts / "alpha.bin").write_bytes(b"alpha")
        (self.artifacts / "beta.bin").write_bytes(b"beta")

        with mock.patch.object(
            write_checksums_module,
            "_sha256",
            side_effect=[hashlib.sha256(b"alpha").hexdigest(), OSError("hash failed")],
        ) as sha256:
            with self.assertRaisesRegex(OSError, "hash failed"):
                write_checksums_module.write_checksums(self.artifacts, self.output)

        self.assertEqual(sha256.call_count, 2)
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_ignores_symlink(self):
        target = self.artifacts / "target.bin"
        target.write_bytes(b"target")
        (self.artifacts / "linked.bin").symlink_to(target)

        write_checksums_module.write_checksums(self.artifacts, self.output)

        self.assertEqual(
            self.output.read_text(encoding="utf-8"),
            f"{hashlib.sha256(b'target').hexdigest()}  target.bin\n",
        )

    def test_rejects_empty_artifact_directory(self):
        with self.assertRaisesRegex(ValueError, "no eligible files"):
            write_checksums_module.write_checksums(self.artifacts, self.output)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
