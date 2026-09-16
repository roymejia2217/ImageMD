from pathlib import Path
import argparse
import json
import re
import sys


_PACKAGE_EXTENSIONS = {
    "deb": ".deb",
    "rpm": ".rpm",
    "arch": ".pkg.tar.zst",
    "appimage": ".AppImage",
    "flatpak": ".flatpak",
}
_SEMVER = re.compile(
    r""
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"\Z"
)


def _metadata_values(metadata: dict[str, object]) -> tuple[str, str, str]:
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a dictionary")

    package = metadata.get("package")
    version = metadata.get("version")
    architecture = metadata.get("architecture")
    if package != "imagemd":
        raise ValueError("metadata package must be imagemd")
    if architecture != "x86_64":
        raise ValueError("metadata architecture must be x86_64")
    if not isinstance(version, str) or _SEMVER.fullmatch(version) is None:
        raise ValueError("metadata version must be SemVer")
    return package, version, architecture


def release_asset_names(metadata: dict[str, object]) -> dict[str, str]:
    package, version, architecture = _metadata_values(metadata)
    del package
    return {
        "deb": f"ImageMD-{version}-{architecture}.deb",
        "rpm": f"ImageMD-{version}-{architecture}.rpm",
        "arch": f"ImageMD-{version}-{architecture}.pkg.tar.zst",
        "appimage": f"ImageMD-{version}-{architecture}.AppImage",
        "flatpak": f"ImageMD-{version}-{architecture}.flatpak",
        "metadata": f"ImageMD-{version}-release-metadata.json",
        "sbom": f"ImageMD-{version}.spdx.json",
        "checksums": f"ImageMD-{version}-SHA256SUMS",
    }


def normalize_release_assets(
    directory: Path, metadata: dict[str, object]
) -> dict[str, Path]:
    if not isinstance(directory, Path) or not directory.exists():
        raise ValueError("asset directory must exist")
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("asset directory must be a real directory")

    names = release_asset_names(metadata)
    children = [
        child
        for child in directory.iterdir()
        if child.is_file() and not child.is_symlink()
    ]
    destinations = {key: directory / names[key] for key in _PACKAGE_EXTENSIONS}
    if any(
        destination.exists() or destination.is_symlink()
        for destination in destinations.values()
    ):
        raise FileExistsError("canonical release asset destination already exists")

    sources: dict[str, Path] = {}
    for key, extension in _PACKAGE_EXTENSIONS.items():
        matches = [child for child in children if child.name.endswith(extension)]
        if len(matches) != 1:
            raise ValueError(
                f"expected exactly one {extension} package, found {len(matches)}"
            )
        sources[key] = matches[0]

    for key, source in sources.items():
        source.rename(destinations[key])
    return destinations


def main() -> int:
    parser = argparse.ArgumentParser()
    metadata_source = parser.add_mutually_exclusive_group(required=True)
    metadata_source.add_argument("--metadata", type=Path)
    metadata_source.add_argument("--version")
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--name")
    operation.add_argument("--normalize-directory", type=Path)
    args = parser.parse_args()

    try:
        if args.metadata is not None:
            with args.metadata.open(encoding="utf-8") as metadata_file:
                metadata = json.load(metadata_file)
        else:
            metadata = {
                "package": "imagemd",
                "version": args.version,
                "architecture": "x86_64",
            }
        if args.normalize_directory is not None:
            normalize_release_assets(args.normalize_directory, metadata)
            return 0
        names = release_asset_names(metadata)
        if args.name not in names:
            raise ValueError(f"unknown canonical asset name: {args.name}")
        sys.stdout.write(f"{names[args.name]}\n")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        sys.stderr.write(f"release asset error: {error}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
