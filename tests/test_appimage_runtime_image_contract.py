from __future__ import annotations

import re
import unittest
from pathlib import Path


DOCKERFILE = (
    Path(__file__).resolve().parents[1]
    / "packaging"
    / "container"
    / "Dockerfile.appimage-runtime"
)
BASE_IMAGE = (
    "debian@sha256:6ebd97fa83deb272194a2cf015b3d26a4d538e9ad3a7a79d544c8af5b0a01443"
)
FFMPEG_URL = "https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz"
FFMPEG_SHA256 = "733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1"
RUNTIME_BIN_DIR = "/opt/imagemd-runtime/bin/"


class AppImageRuntimeImageContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not DOCKERFILE.is_file():
            raise AssertionError(f"missing required Dockerfile: {DOCKERFILE}")
        cls.contents = DOCKERFILE.read_text(encoding="utf-8")

    def test_uses_pinned_debian_bookworm_base(self) -> None:
        self.assertRegex(
            self.contents,
            rf"(?m)^FROM\s+{re.escape(BASE_IMAGE)}(?:\s|$)",
        )

    def test_downloads_only_verified_ffmpeg_archive_before_extracting(self) -> None:
        urls = re.findall(r"https?://[^\s\"'\\)]+", self.contents)
        self.assertEqual(urls, [FFMPEG_URL])
        self.assertEqual(self.contents.count(FFMPEG_URL), 1)

        checksum_position = self.contents.find(FFMPEG_SHA256)
        self.assertGreaterEqual(checksum_position, 0)
        verification_line = next(
            (line for line in self.contents.splitlines() if FFMPEG_SHA256 in line),
            "",
        )
        self.assertRegex(verification_line, r"(?i)sha256sum")

        extraction = re.search(
            r"(?im)^\s*(?:tar\s+[^\n]*-x[^\n]*|un(?:tar|xz)\b[^\n]*)",
            self.contents,
        )
        self.assertIsNotNone(extraction)
        assert extraction is not None
        self.assertLess(checksum_position, extraction.start())

    def test_excludes_untrusted_or_streamed_download_patterns(self) -> None:
        self.assertNotIn("latest", self.contents.lower())
        self.assertNotIn("continuous", self.contents.lower())
        self.assertNotRegex(self.contents, r"(?i)curl\s*\|")
        self.assertNotRegex(self.contents, r"(?i)wget\s*\|")

    def test_builds_static_non_network_ffmpeg(self) -> None:
        for option in ("--disable-shared", "--enable-static", "--disable-network"):
            with self.subTest(option=option):
                self.assertIn(option, self.contents)

    def test_installs_ffmpeg_and_ffprobe_in_runtime_bin(self) -> None:
        self.assertIn(RUNTIME_BIN_DIR, self.contents)
        for binary in ("ffmpeg", "ffprobe"):
            with self.subTest(binary=binary):
                self.assertRegex(
                    self.contents,
                    rf"{re.escape(RUNTIME_BIN_DIR)}{binary}(?:\s|\"|$)",
                )


if __name__ == "__main__":
    unittest.main()
