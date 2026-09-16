#!/usr/bin/env python3
"""Write SHA-256 checksums for regular files in one artifact directory."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError(f"artifact is not a regular file: {path.name}")
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(artifacts: Path, output: Path) -> Path:
    """Write sorted SHA-256 records for direct regular-file children."""
    artifacts = Path(artifacts)
    output = Path(output)
    root = artifacts.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"artifacts must be an existing directory: {artifacts}")

    destination = output.resolve(strict=False)
    try:
        destination.relative_to(root)
    except ValueError as error:
        raise ValueError("output must be inside the artifacts directory") from error

    if os.path.lexists(destination):
        raise FileExistsError(f"output already exists: {destination}")

    entries: list[Path] = []
    with os.scandir(root) as children:
        for child in children:
            if child.is_file(follow_symlinks=False):
                entries.append(Path(child.path))
    entries.sort(key=lambda path: path.name)
    if not entries:
        raise ValueError("artifacts directory contains no eligible files")

    created = False
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as manifest:
            created = True
            for artifact in entries:
                manifest.write(f"{_sha256(artifact)}  {artifact.name}\n")
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        write_checksums(args.artifacts, args.output)
    except (OSError, ValueError) as error:
        print(f"checksum generation failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
