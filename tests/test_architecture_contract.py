"""Executable hexagonal boundary guards for domain and application layers.

The checks parse Python with :mod:`ast`; they never grep raw source text.
"""

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_ROOT = ROOT / "src" / "domain"
APPLICATION_ROOT = ROOT / "src" / "application"

DOMAIN_FORBIDDEN = (
    "src.application",
    "src.adapters",
    "src.gui",
    "src.media_ops",
    "src.repair",
    "tkinter",
    "ttkbootstrap",
    "PIL",
    "piexif",
    "ffmpeg",
    "pathlib",
    "subprocess",
)

APPLICATION_ALLOWED = (
    "src.application",
    "src.domain",
)

APPLICATION_FORBIDDEN_EXTERNAL = (
    "tkinter",
    "ttkbootstrap",
    "PIL",
    "piexif",
    "ffmpeg",
)


def is_forbidden(module, forbidden):
    """Return True when module is a forbidden root or one of its submodules."""
    return any(module == root or module.startswith(root + ".") for root in forbidden)


def is_application_forbidden(module):
    """Application may only depend inward on application/domain contracts.

    Any other absolute ``src.*`` dependency is forbidden, as are the
    external UI/media/process infrastructure roots.
    """
    if module == "src" or module.startswith("src."):
        return not any(
            module == root or module.startswith(root + ".")
            for root in APPLICATION_ALLOWED
        )
    return is_forbidden(module, APPLICATION_FORBIDDEN_EXTERNAL)


def imported_modules(source, package):
    """Resolve absolute module names imported by source using the AST."""
    tree = ast.parse(source)
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    modules.append(node.module)
            else:
                base = package
                for _ in range(node.level - 1):
                    base = base.rpartition(".")[0]
                if node.module:
                    resolved = f"{base}.{node.module}" if base else node.module
                    modules.append(resolved)
                else:
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        resolved = f"{base}.{alias.name}" if base else alias.name
                        modules.append(resolved)
    return modules


def find_violations(root, package, forbidden):
    """Collect (path, module) pairs violating the boundary."""
    violations = []
    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for module in imported_modules(source, package):
            if is_forbidden(module, forbidden):
                violations.append((str(path), module))
    return violations


def find_application_violations(root, package):
    """Collect (path, module) pairs violating the application allowlist."""
    violations = []
    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for module in imported_modules(source, package):
            if is_application_forbidden(module):
                violations.append((str(path), module))
    return violations


class DomainBoundaryTests(unittest.TestCase):
    def test_domain_has_no_forbidden_imports(self):
        violations = find_violations(DOMAIN_ROOT, "src.domain", DOMAIN_FORBIDDEN)
        for path, module in violations:
            print(f"boundary violation: {path} imports {module}")
        self.assertEqual(violations, [])

    def test_detector_flags_infrastructure_in_domain(self):
        modules = imported_modules("import pathlib\n", "src.domain")
        self.assertTrue(
            any(is_forbidden(module, DOMAIN_FORBIDDEN) for module in modules)
        )

    def test_detector_allows_pure_stdlib_in_domain(self):
        source = (
            "from dataclasses import dataclass\n"
            "from datetime import datetime, timezone\n"
            "from enum import Enum\n"
            "from zoneinfo import ZoneInfo\n"
        )
        modules = imported_modules(source, "src.domain")
        self.assertTrue(modules)
        self.assertFalse(
            [module for module in modules if is_forbidden(module, DOMAIN_FORBIDDEN)]
        )


class ApplicationBoundaryTests(unittest.TestCase):
    def test_application_has_no_forbidden_imports(self):
        violations = find_application_violations(APPLICATION_ROOT, "src.application")
        for path, module in violations:
            print(f"boundary violation: {path} imports {module}")
        self.assertEqual(violations, [])

    def test_detector_flags_adapter_import_in_application(self):
        source = "from src.adapters.storage_transaction import snapshot_file\n"
        modules = imported_modules(source, "src.application")
        flagged = [module for module in modules if is_application_forbidden(module)]
        self.assertEqual(flagged, ["src.adapters.storage_transaction"])

    def test_detector_flags_outer_compatibility_imports_in_application(self):
        for source, expected in (
            (
                "from src.adapters.storage_transaction import snapshot_file\n",
                ["src.adapters.storage_transaction"],
            ),
            ("from src.repair import ImageRepairTool\n", ["src.repair"]),
            ("from src.media_ops import MediaMetadataManager\n", ["src.media_ops"]),
        ):
            with self.subTest(source=source):
                modules = imported_modules(source, "src.application")
                flagged = [
                    module for module in modules if is_application_forbidden(module)
                ]
                self.assertEqual(flagged, expected)

    def test_detector_flags_gui_toolkit_in_application(self):
        for source, expected in (
            ("import tkinter\n", ["tkinter"]),
            ("from PIL import Image\n", ["PIL"]),
        ):
            with self.subTest(source=source):
                modules = imported_modules(source, "src.application")
                flagged = [
                    module for module in modules if is_application_forbidden(module)
                ]
                self.assertEqual(flagged, expected)

    def test_detector_allows_domain_and_intra_package_imports(self):
        source = (
            "from src.domain.temporal import DateCandidate\n"
            "from src.application.date_decision import DateDecision\n"
            "from .scan_media import ScanResult\n"
        )
        modules = imported_modules(source, "src.application")
        self.assertIn("src.application.scan_media", modules)
        self.assertFalse(
            [module for module in modules if is_application_forbidden(module)]
        )

    def test_detector_application_allowlist_matrix(self):
        rejected = (
            "from src.adapters.storage_transaction import snapshot_file\n",
            "from src.repair import ImageRepairTool\n",
            "from src.media_ops import MediaMetadataManager\n",
        )
        for source in rejected:
            with self.subTest(source=source):
                modules = imported_modules(source, "src.application")
                self.assertTrue(modules)
                self.assertTrue(
                    all(is_application_forbidden(module) for module in modules)
                )
        accepted_sources = (
            "from src.domain.temporal import DateCandidate\n",
            "from src.application.date_decision import DateDecision\n",
            "from .scan_media import ScanResult\n",
        )
        for source in accepted_sources:
            with self.subTest(source=source):
                modules = imported_modules(source, "src.application")
                self.assertTrue(modules)
                self.assertFalse(
                    [module for module in modules if is_application_forbidden(module)]
                )
        relative = imported_modules(
            "from .scan_media import ScanResult\n", "src.application"
        )
        self.assertIn("src.application.scan_media", relative)
        self.assertFalse(
            [module for module in relative if is_application_forbidden(module)]
        )


if __name__ == "__main__":
    unittest.main()
