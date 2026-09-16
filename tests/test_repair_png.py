import hashlib
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from src.adapters import storage_transaction
from src.adapters.png_validation import PillowPngValidator
from src.application.repair_png import (
    PngRepairService,
    RepairKind,
    RepairPolicy,
)
from src.repair import ImageRepairTool, PngWriteKind, PngWriteResult


def valid_png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), (20, 40, 60)).save(output, format="PNG")
    return output.getvalue()


class FailingValidationWriter:
    def write_repaired_png(self, source_path: str, staged_path: str):
        Path(staged_path).write_bytes(b"not a png")
        return PngWriteResult(PngWriteKind.VALIDATION_FAILED)


class DishonestWriter:
    def write_repaired_png(self, source_path: str, staged_path: str):
        Path(staged_path).write_bytes(b"not a png")
        return PngWriteResult(PngWriteKind.WRITTEN)


class TestPngRepair(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / "image.png"
        self.original = b"shifted-header-prefix" + valid_png_bytes()[8:]
        self.source.write_bytes(self.original)
        self.policy = RepairPolicy(".bak")

    def test_success_commits_verified_png_and_keeps_exact_backup(self):
        result = PngRepairService(
            ImageRepairTool(),
            self.policy,
            PillowPngValidator(),
            storage_transaction,
        ).repair(str(self.source))

        self.assertEqual(result.kind, RepairKind.REPAIRED)
        self.assertEqual(
            self.source.with_name("image.png.bak").read_bytes(), self.original
        )
        with Image.open(self.source) as image:
            self.assertEqual(image.format, "PNG")
            image.verify()
        self.assertEqual(
            result.receipt.previous_sha256, hashlib.sha256(self.original).hexdigest()
        )
        self.assertFalse(list(self.directory.glob("*.stage.png")))

    def test_validation_failure_preserves_source_and_removes_staging(self):
        result = PngRepairService(
            FailingValidationWriter(),
            self.policy,
            PillowPngValidator(),
            storage_transaction,
        ).repair(str(self.source))

        self.assertEqual(result.kind, RepairKind.VALIDATION_FAILED)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse(list(self.directory.glob("*.stage.png")))
        self.assertFalse(self.source.with_name("image.png.bak").exists())

    def test_non_repairable_file_is_rejected_without_mutation(self):
        original = b"not a png, and no IHDR"
        self.source.write_bytes(original)

        result = PngRepairService(
            ImageRepairTool(),
            self.policy,
            PillowPngValidator(),
            storage_transaction,
        ).repair(str(self.source))

        self.assertEqual(result.kind, RepairKind.REJECTED)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.source.with_name("image.png.bak").exists())
        self.assertFalse(list(self.directory.glob("*.stage.png")))

    def test_independent_verification_rejects_a_dishonest_writer(self):
        result = PngRepairService(
            DishonestWriter(),
            self.policy,
            PillowPngValidator(),
            storage_transaction,
        ).repair(str(self.source))

        self.assertEqual(result.kind, RepairKind.VALIDATION_FAILED)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse(self.source.with_name("image.png.bak").exists())


if __name__ == "__main__":
    unittest.main()
