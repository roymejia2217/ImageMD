from __future__ import annotations

import re
import unittest
from pathlib import Path


DOCKERFILE = (
    Path(__file__).resolve().parents[1]
    / "packaging"
    / "container"
    / "Dockerfile.pyinstaller"
)
BASE_IMAGE = "python:3.12-bookworm@sha256:581429e3df12d76e6af4be5ab7d0e7fc2013eb57dc23d2de691411c8efdbb970"


class PyInstallerContainerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not DOCKERFILE.is_file():
            raise AssertionError(f"missing required Dockerfile: {DOCKERFILE}")
        cls.contents = DOCKERFILE.read_text(encoding="utf-8")

    def test_uses_pinned_python_3_12_bookworm_base(self) -> None:
        self.assertRegex(
            self.contents,
            rf"(?m)^FROM\s+{re.escape(BASE_IMAGE)}(?:\s|$)",
        )

    def test_installs_xvfb_and_xauth_in_the_same_apt_transaction(self) -> None:
        install = re.search(
            r"(?ims)apt-get\s+install\s+-y\s+--no-install-recommends\s+(.*?)(?=\s*\\\s*$|\n\s*&&)",
            self.contents,
        )
        self.assertIsNotNone(
            install, "Dockerfile must contain a pinned apt install transaction"
        )
        assert install is not None
        packages = install.group(1).split()
        self.assertIn("xvfb", packages)
        self.assertIn("xauth", packages)

    def test_installs_pyinstaller_build_dependencies_in_the_same_apt_transaction(
        self,
    ) -> None:
        install = re.search(
            r"(?ims)apt-get\s+install\s+-y\s+--no-install-recommends\s+(.*?)(?=\s*\\\s*$|\n\s*&&)",
            self.contents,
        )
        self.assertIsNotNone(
            install, "Dockerfile must contain a pinned apt install transaction"
        )
        assert install is not None
        packages = install.group(1).split()
        self.assertIn("build-essential", packages)
        self.assertIn("zlib1g-dev", packages)

    def test_applies_bootloader_compile_flag_to_pyinstaller_installation(self) -> None:
        self.assertRegex(
            self.contents,
            r"(?is)PYINSTALLER_COMPILE_BOOTLOADER=1\s+(?:python\s+-m\s+pip|pip3?)\s+install\b.*?pyinstaller",
        )

    def test_applies_full_relro_linker_flags_to_bootloader_compilation(self) -> None:
        self.assertRegex(
            self.contents,
            r"(?is)LDFLAGS\s*=\s*(['\"])(?=[^'\"]*-z,relro)(?=[^'\"]*-z,now)[^'\"]*\1\s*(?:\\\s*)?PYINSTALLER_COMPILE_BOOTLOADER=1\s+(?:python\s+-m\s+pip|pip3?)\s+install\b.*?pyinstaller",
            "PyInstaller bootloader compilation must use Full RELRO linker flags",
        )

    def test_installs_pyinstaller_from_source_distribution(self) -> None:
        self.assertRegex(
            self.contents,
            r"(?is)(?:python\s+-m\s+pip|pip3?)\s+install\b.*?--no-binary(?:=|\s+)pyinstaller.*?pyinstaller",
        )


if __name__ == "__main__":
    unittest.main()
