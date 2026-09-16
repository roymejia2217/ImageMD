#!/usr/bin/env python3
"""Build a Debian package from the shared ImageMD staging tree."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REQUIRED_PATHS = (
    "usr/bin/imagemd",
    "usr/share/applications/org.roymejia.ImageMD.desktop",
    "usr/share/icons/hicolor/scalable/apps/org.roymejia.ImageMD.svg",
    "usr/share/metainfo/org.roymejia.ImageMD.metainfo.xml",
    "usr/share/doc/imagemd/copyright",
    "usr/share/man/man1/imagemd.1",
)


def debian_version(version: str) -> str:
    """Map Python developmental versions to Debian's pre-release ordering."""
    return version.replace(".dev", "~dev", 1)


def read_metadata(stage: Path) -> dict[str, object]:
    with (stage / "release-metadata.json").open(encoding="utf-8") as source:
        metadata = json.load(source)
    if metadata.get("package") != "imagemd" or metadata.get("architecture") != "x86_64":
        raise ValueError("stage does not describe the supported ImageMD x86_64 package")
    rootfs = stage / "rootfs"
    for relative in REQUIRED_PATHS:
        if not (rootfs / relative).is_file():
            raise ValueError(f"stage is missing required file: {relative}")
    return metadata


def control_contents(metadata: dict[str, object]) -> str:
    version = metadata["version"]
    if not isinstance(version, str):
        raise ValueError("stage metadata version must be text")
    return "\n".join(
        (
            "Package: imagemd",
            f"Version: {debian_version(version)}",
            "Architecture: amd64",
            "Maintainer: Roy Mejia",
            "Depends: ffmpeg, libc6 (>= 2.36)",
            "Section: graphics",
            "Priority: optional",
            "Homepage: https://github.com/roymejia2217/ImageMD",
            "Description: Desktop metadata analysis and repair tool",
            " ImageMD analyzes image and video timestamps and applies approved repairs.",
            "",
        )
    )


def build(stage: Path, output: Path) -> Path:
    stage = stage.resolve(strict=True)
    metadata = read_metadata(stage)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite package: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="imagemd-deb-") as temporary:
        root = Path(temporary) / "root"
        shutil.copytree(stage / "rootfs", root)
        control = root / "DEBIAN" / "control"
        control.parent.mkdir()
        control.write_text(control_contents(metadata), encoding="utf-8")
        subprocess.run(
            ["dpkg-deb", "--root-owner-group", "--build", str(root), str(output)],
            check=True,
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        package = build(args.stage, args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Debian package build failed: {error}", file=sys.stderr)
        return 2
    print(package)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
