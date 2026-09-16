#!/usr/bin/env python3
"""Create a specification-conformant AppDir from shared ImageMD staging."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import stat
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEBIAN_BUILDER = ROOT / "packaging" / "debian" / "build_deb.py"
PACKAGE_ID = "org.roymejia.ImageMD"

APPRUN = """#!/bin/sh
set -eu
APPDIR=${APPDIR:-$(CDPATH= cd -- \"$(dirname -- \"$0\")\" && pwd)}
export IMAGEMD_FFMPEG_EXECUTABLE=\"$APPDIR/usr/bin/ffmpeg\"
export IMAGEMD_FFPROBE_EXECUTABLE=\"$APPDIR/usr/bin/ffprobe\"
exec \"$APPDIR/usr/bin/imagemd\" \"$@\"
"""


def load_stage_validator():
    spec = importlib.util.spec_from_file_location("imagemd_deb_builder", DEBIAN_BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shared stage validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create(stage: Path, appdir: Path, ffmpeg: Path, ffprobe: Path) -> Path:
    stage = stage.resolve(strict=True)
    runtime_binaries = []
    for binary in (ffmpeg, ffprobe):
        try:
            if binary.is_symlink():
                raise ValueError(f"runtime binary must not be a symlink: {binary}")
            resolved = binary.resolve(strict=True)
            mode = resolved.stat().st_mode
        except (OSError, RuntimeError) as error:
            raise ValueError(f"invalid runtime binary: {binary}") from error
        if not stat.S_ISREG(mode) or not mode & stat.S_IXUSR:
            raise ValueError(
                f"runtime binary must be a regular owner-executable file: {binary}"
            )
        runtime_binaries.append(resolved)
    if appdir.exists():
        raise FileExistsError(f"refusing to overwrite AppDir: {appdir}")
    load_stage_validator().read_metadata(stage)
    shutil.copytree(stage / "rootfs", appdir)
    for binary, name in zip(runtime_binaries, ("ffmpeg", "ffprobe")):
        target = appdir / "usr" / "bin" / name
        shutil.copyfile(binary, target)
        target.chmod(0o755)
    desktop = f"usr/share/applications/{PACKAGE_ID}.desktop"
    icon = f"usr/share/icons/hicolor/scalable/apps/{PACKAGE_ID}.svg"
    os.symlink(
        f"{PACKAGE_ID}.metainfo.xml",
        appdir / "usr" / "share" / "metainfo" / f"{PACKAGE_ID}.appdata.xml",
    )
    for target, source in (
        (f"{PACKAGE_ID}.desktop", desktop),
        (f"{PACKAGE_ID}.svg", icon),
        (".DirIcon", f"{PACKAGE_ID}.svg"),
    ):
        os.symlink(source, appdir / target)
    apprun = appdir / "AppRun"
    apprun.write_text(APPRUN, encoding="utf-8")
    apprun.chmod(0o755)
    return appdir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--appdir", required=True, type=Path)
    parser.add_argument("--ffmpeg", required=True, type=Path)
    parser.add_argument("--ffprobe", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(create(args.stage, args.appdir, args.ffmpeg, args.ffprobe))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"AppDir creation failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
