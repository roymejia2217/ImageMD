#!/usr/bin/env python3
"""Prepare an isolated local-source context for a Flatpak build."""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "packaging" / "flatpak" / "org.roymejia.ImageMD.yml"
DEBIAN_BUILDER = ROOT / "packaging" / "debian" / "build_deb.py"


def load_stage_validator():
    spec = importlib.util.spec_from_file_location("imagemd_deb_builder", DEBIAN_BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shared stage validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(stage: Path, output: Path) -> Path:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite Flatpak context: {output}")
    stage = stage.resolve(strict=True)
    metadata = load_stage_validator().read_metadata(stage)
    if metadata.get("application_id") != "org.roymejia.ImageMD":
        raise ValueError("stage application id does not match Flatpak manifest")
    if not MANIFEST.is_file():
        raise ValueError("Flatpak manifest is missing")
    output.mkdir(parents=True)
    shutil.copyfile(MANIFEST, output / MANIFEST.name)
    shutil.copytree(stage / "rootfs", output / "payload")
    return output / MANIFEST.name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(prepare(args.stage, args.output))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Flatpak context creation failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
