#!/usr/bin/env python3
"""Build an RPM from the shared ImageMD staging tree."""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEBIAN_BUILDER = ROOT / "packaging" / "debian" / "build_deb.py"
TEMPLATE = ROOT / "packaging" / "rpm" / "imagemd-rpm.spec.in"
_REPRODUCIBILITY_SPEC = importlib.util.spec_from_file_location(
    "imagemd_reproducibility", ROOT / "packaging" / "reproducibility.py"
)
if _REPRODUCIBILITY_SPEC is None or _REPRODUCIBILITY_SPEC.loader is None:
    raise RuntimeError("cannot load reproducible archive writer")
_REPRODUCIBILITY_MODULE = importlib.util.module_from_spec(_REPRODUCIBILITY_SPEC)
_REPRODUCIBILITY_SPEC.loader.exec_module(_REPRODUCIBILITY_MODULE)
write_reproducible_tar_gz = _REPRODUCIBILITY_MODULE.write_reproducible_tar_gz


def load_debian_builder():
    spec = importlib.util.spec_from_file_location("imagemd_deb_builder", DEBIAN_BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shared stage validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rpm_version(version: str) -> str:
    """RPM sorts `~` before a final version, as required for development builds."""
    return version.replace(".dev", "~dev", 1)


def build(stage: Path, output_directory: Path) -> Path:
    stage = stage.resolve(strict=True)
    metadata = load_debian_builder().read_metadata(stage)
    version = metadata["version"]
    if not isinstance(version, str):
        raise ValueError("stage metadata version must be text")
    output_directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="imagemd-rpm-") as temporary:
        topdir = Path(temporary) / "rpmbuild"
        sources = topdir / "SOURCES"
        specs = topdir / "SPECS"
        sources.mkdir(parents=True)
        specs.mkdir()
        source_archive = sources / "imagemd-stage.tar.gz"
        write_reproducible_tar_gz(stage / "rootfs", source_archive, "rootfs")
        rendered = TEMPLATE.read_text(encoding="utf-8").replace(
            "@VERSION@", rpm_version(version)
        )
        spec_path = specs / "imagemd-rpm.spec"
        spec_path.write_text(rendered, encoding="utf-8")
        subprocess.run(
            ["rpmbuild", "--define", f"_topdir {topdir}", "-bb", str(spec_path)],
            check=True,
        )
        packages = list((topdir / "RPMS" / "x86_64").glob("imagemd-*.x86_64.rpm"))
        if len(packages) != 1:
            raise RuntimeError("rpmbuild did not produce exactly one x86_64 package")
        package = packages[0]
        result = output_directory / package.name
        if result.exists():
            raise FileExistsError(f"refusing to overwrite package: {result}")
        shutil.copyfile(package, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(build(args.stage, args.output_directory))
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"RPM package build failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
