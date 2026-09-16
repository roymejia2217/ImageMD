#!/usr/bin/env python3
"""Render an Arch PKGBUILD and pinned source archive from shared staging."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEBIAN_BUILDER = ROOT / "packaging" / "debian" / "build_deb.py"
TEMPLATE = ROOT / "packaging" / "arch" / "PKGBUILD.in"
_REPRODUCIBILITY_SPEC = importlib.util.spec_from_file_location(
    "imagemd_reproducibility", ROOT / "packaging" / "reproducibility.py"
)
if _REPRODUCIBILITY_SPEC is None or _REPRODUCIBILITY_SPEC.loader is None:
    raise RuntimeError("cannot load reproducible archive writer")
_REPRODUCIBILITY_MODULE = importlib.util.module_from_spec(_REPRODUCIBILITY_SPEC)
_REPRODUCIBILITY_SPEC.loader.exec_module(_REPRODUCIBILITY_MODULE)
write_reproducible_tar_gz = _REPRODUCIBILITY_MODULE.write_reproducible_tar_gz


def load_stage_validator():
    spec = importlib.util.spec_from_file_location("imagemd_deb_builder", DEBIAN_BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shared stage validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def arch_version(version: str) -> str:
    """Arch package versions cannot use Python's `.dev` separator."""
    return version.replace(".dev", ".dev", 1)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def create_recipe(stage: Path, output: Path) -> Path:
    stage = stage.resolve(strict=True)
    metadata = load_stage_validator().read_metadata(stage)
    version = metadata["version"]
    if not isinstance(version, str):
        raise ValueError("stage metadata version must be text")
    if output.is_symlink():
        raise FileExistsError(f"refusing to use symlink recipe directory: {output}")
    if output.exists():
        if not output.is_dir():
            raise FileExistsError(
                f"refusing to use non-directory recipe path: {output}"
            )
        if any(output.iterdir()):
            raise FileExistsError(
                f"refusing to use non-empty recipe directory: {output}"
            )
    else:
        output.mkdir(parents=True)
    package_version = arch_version(version)
    archive = output / f"imagemd-{package_version}.tar.gz"
    write_reproducible_tar_gz(stage / "rootfs", archive, "rootfs")
    pkbuild = TEMPLATE.read_text(encoding="utf-8")
    pkbuild = pkbuild.replace("@VERSION@", package_version).replace(
        "@SHA256@", digest(archive)
    )
    (output / "PKGBUILD").write_text(pkbuild, encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(create_recipe(args.stage, args.output))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Arch recipe creation failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
