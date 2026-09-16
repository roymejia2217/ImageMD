#!/usr/bin/env python3
"""Create the single, inspectable Linux staging tree consumed by package recipes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "org.roymejia.ImageMD"
PACKAGE_NAME = "imagemd"
SYSTEM_DEPENDENCIES = {
    "debian": ["ffmpeg"],
    "fedora": ["ffmpeg-free"],
    "arch": ["ffmpeg"],
}
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[a-z0-9.+~-]*)?$")


def project_version() -> str:
    namespace: dict[str, str] = {}
    exec((PROJECT_ROOT / "src" / "__init__.py").read_text(encoding="utf-8"), namespace)
    version = namespace.get("__version__")
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError("src.__version__ must be a package-compatible version")
    return version


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file(source: Path, target: Path, mode: int | None = None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if mode is not None:
        target.chmod(mode)


def create_stage(bundle: Path, destination: Path) -> dict[str, object]:
    bundle = bundle.resolve(strict=True)
    if (
        not bundle.is_file()
        or bundle.is_symlink()
        or not (bundle.stat().st_mode & stat.S_IXUSR)
    ):
        raise ValueError("bundle must be an executable regular file")
    if destination.exists():
        raise FileExistsError(f"destination already exists: {destination}")

    rootfs = destination / "rootfs"
    usr = rootfs / "usr"
    copy_file(bundle, usr / "bin" / PACKAGE_NAME, 0o755)
    common = PROJECT_ROOT / "packaging" / "common"
    copy_file(
        common / f"{PACKAGE_ID}.desktop",
        usr / "share" / "applications" / f"{PACKAGE_ID}.desktop",
        0o644,
    )
    copy_file(
        common / f"{PACKAGE_ID}.svg",
        usr / "share" / "icons" / "hicolor" / "scalable" / "apps" / f"{PACKAGE_ID}.svg",
        0o644,
    )
    copy_file(
        common / f"{PACKAGE_ID}.metainfo.xml",
        usr / "share" / "metainfo" / f"{PACKAGE_ID}.metainfo.xml",
        0o644,
    )
    copy_file(
        PROJECT_ROOT / "LICENSE",
        usr / "share" / "doc" / PACKAGE_NAME / "copyright",
        0o644,
    )
    copy_file(
        PROJECT_ROOT / "LICENSE",
        usr / "share" / "licenses" / PACKAGE_NAME / "LICENSE",
        0o644,
    )
    copy_file(
        common / f"{PACKAGE_NAME}.1",
        usr / "share" / "man" / "man1" / f"{PACKAGE_NAME}.1",
        0o644,
    )

    metadata: dict[str, object] = {
        "schema": 1,
        "package": PACKAGE_NAME,
        "application_id": PACKAGE_ID,
        "version": project_version(),
        "architecture": "x86_64",
        "bundle": {
            "filename": PACKAGE_NAME,
            "sha256": sha256(usr / "bin" / PACKAGE_NAME),
        },
        "system_dependencies": SYSTEM_DEPENDENCIES,
    }
    (destination / "release-metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        metadata = create_stage(args.bundle, args.output)
    except (OSError, ValueError) as error:
        print(f"stage creation failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
