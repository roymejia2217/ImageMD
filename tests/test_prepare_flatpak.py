from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "packaging" / "flatpak" / "prepare_flatpak.py"


def load_module():
    spec = importlib.util.spec_from_file_location("prepare_flatpak", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PrepareFlatpakTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def test_prepare_copies_only_validated_stage_rootfs_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            rootfs = stage / "rootfs"
            required = (
                "usr/bin/imagemd",
                "usr/share/applications/org.roymejia.ImageMD.desktop",
                "usr/share/icons/hicolor/scalable/apps/org.roymejia.ImageMD.svg",
                "usr/share/metainfo/org.roymejia.ImageMD.metainfo.xml",
                "usr/share/doc/imagemd/copyright",
                "usr/share/man/man1/imagemd.1",
            )
            for relative in required:
                target = rootfs / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture", encoding="utf-8")
            (stage / "release-metadata.json").write_text(
                '{"package":"imagemd","architecture":"x86_64","application_id":"org.roymejia.ImageMD"}',
                encoding="utf-8",
            )

            manifest = self.module.prepare(stage, root / "context")

            self.assertEqual(manifest.name, "org.roymejia.ImageMD.yml")
            self.assertTrue(
                (root / "context" / "payload" / "usr/bin/imagemd").is_file()
            )
            self.assertTrue(manifest.is_file())

    def test_prepare_refuses_existing_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "context"
            output.mkdir()
            with self.assertRaises(FileExistsError):
                self.module.prepare(root / "missing", output)
