"""Write repaired PNG bytes to a caller-owned staging file."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from pathlib import Path

from PIL import Image


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


class ImageRepairTool:
    """Detect the known shifted-IHDR corruption and write only to a stage."""

    png_magic = b"\x89PNG\r\n\x1a\n"

    def is_corrupted_png(self, filepath: str) -> bool:
        path = Path(filepath)
        if path.suffix.lower() != ".png":
            return False
        try:
            with Image.open(path) as image:
                image.verify()
            return False
        except Exception:
            try:
                data = path.read_bytes()
            except OSError:
                return False
            candidate = self._candidate(data)
            return candidate is not None and self._valid_png(candidate)

    def write_repaired_png(self, source_path: str, staged_path: str) -> PngWriteResult:
        """Write a verified PNG to an already-created stage; never mutate source."""
        source = Path(source_path)
        staged = Path(staged_path)
        if source.suffix.lower() != ".png" or source.resolve() == staged.resolve():
            return PngWriteResult(PngWriteKind.NOT_REPAIRABLE)
        try:
            if not staged.is_file() or staged.stat().st_size != 0:
                return PngWriteResult(PngWriteKind.WRITE_FAILED)
        except OSError:
            return PngWriteResult(PngWriteKind.WRITE_FAILED)
        try:
            original = source.read_bytes()
        except OSError:
            return PngWriteResult(PngWriteKind.NOT_REPAIRABLE)
        candidate = self._candidate(original)
        if candidate is None:
            return PngWriteResult(PngWriteKind.NOT_REPAIRABLE)
        try:
            with staged.open("wb") as stream:
                stream.write(candidate)
                stream.flush()
        except OSError:
            return PngWriteResult(PngWriteKind.WRITE_FAILED)
        if not self.verify_repaired_png(str(staged)):
            return PngWriteResult(PngWriteKind.VALIDATION_FAILED)
        return PngWriteResult(PngWriteKind.WRITTEN)

    def verify_repaired_png(self, staged_path: str) -> bool:
        """Verify a staged PNG independently before a transaction can commit it."""
        return self._valid_png_file(Path(staged_path))

    def repair_file(self, filepath: str, dry_run: bool = False) -> bool:
        """Deprecated compatibility shim: in-place repair is intentionally disabled."""
        return False

    def _candidate(self, data: bytes) -> bytes | None:
        ihdr_pos = data.find(b"IHDR")
        if ihdr_pos <= 12:
            return None
        chunk_start = ihdr_pos - 4
        if chunk_start < 0 or data[chunk_start:ihdr_pos] != b"\x00\x00\x00\x0d":
            return None
        repaired = self.png_magic + data[chunk_start:]
        return repaired if self._valid_png(repaired) else None

    @staticmethod
    def _valid_png(data: bytes) -> bool:
        try:
            with Image.open(BytesIO(data)) as image:
                if image.format != "PNG":
                    return False
                image.verify()
            return True
        except Exception:
            return False

    @staticmethod
    def _valid_png_file(path: Path) -> bool:
        try:
            with Image.open(path) as image:
                if image.format != "PNG":
                    return False
                image.verify()
            return True
        except Exception:
            return False
