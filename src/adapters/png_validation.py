"""Pillow-backed validation adapter for staged PNG repair output."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


class PillowPngValidator:
    """Validate format and image integrity without changing the file."""

    def is_valid(self, path: str) -> bool:
        try:
            with Image.open(Path(path)) as image:
                if image.format != "PNG":
                    return False
                image.verify()
            return True
        except Exception:
            return False
