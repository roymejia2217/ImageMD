from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "packaging" / "flatpak" / "org.roymejia.ImageMD.yml"


class FlatpakManifestContractTests(unittest.TestCase):
    def test_runtime_and_sdk_are_pinned_to_the_same_supported_branch(self) -> None:
        contents = MANIFEST.read_text(encoding="utf-8")

        self.assertIn("runtime: org.freedesktop.Platform", contents)
        self.assertIn("runtime-version: '25.08'", contents)
        self.assertIn("sdk: org.freedesktop.Sdk", contents)

    def test_bundled_ffmpeg_and_adapter_environment_agree(self) -> None:
        contents = MANIFEST.read_text(encoding="utf-8")

        self.assertIn("IMAGEMD_FFMPEG_EXECUTABLE: /app/bin/ffmpeg", contents)
        self.assertIn("IMAGEMD_FFPROBE_EXECUTABLE: /app/bin/ffprobe", contents)
        self.assertIn("--enable-ffmpeg", contents)
        self.assertIn("--enable-ffprobe", contents)

    def test_ffmpeg_source_is_an_https_archive_with_a_full_sha256(self) -> None:
        contents = MANIFEST.read_text(encoding="utf-8")

        self.assertIn("url: https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz", contents)
        checksum = re.search(r"sha256: ([0-9a-f]{64})$", contents, re.MULTILINE)
        self.assertIsNotNone(checksum)


if __name__ == "__main__":
    unittest.main()
