# ImageMD _(imagemd)_

![Python](https://img.shields.io/badge/Python-3.12%20%E2%80%93%203.14-blue)
![Status](https://img.shields.io/badge/Status-Beta-yellow)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

Desktop metadata analysis and repair tool for image and video files

ImageMD is a desktop application for inspecting, normalizing, and repairing
metadata in image and video files. It can recover timestamps from file names,
read standard and embedded metadata, update media timestamps, and repair
supported PNG corruption.

The repository and application use the `ImageMD` name. The Python project
metadata uses the normalized distribution name `imagemd`.

## Install

ImageMD requires Python 3.12 through 3.14. Clone the repository and install the
locked environment with uv:

```sh
git clone https://github.com/roymejia2217/ImageMD.git
cd ImageMD
uv sync --locked
```

### Dependencies

FFmpeg and FFprobe must be available on `PATH` for full video metadata
support. Without FFmpeg, video metadata updates are limited to filesystem
timestamps.

## Usage

Launch the desktop application from the synchronized environment:

```sh
uv run imagemd
```

### CLI

ImageMD also provides a PNG repair command. Start with `--dry-run` to inspect
what would be repaired without modifying files:

```sh
uv run imagemd-repair /path/to/file-or-directory --dry-run
```

Remove `--dry-run` to apply supported repairs. Add `--verbose` or `-v` for
more detailed output.

## Architecture

- `src/gui.py` contains the desktop interface.
- `src/media_ops.py` handles image and video metadata operations.
- `src/date_utils.py` provides filename-date extraction and normalization.
- `src/repair.py` contains low-level PNG inspection and repair behavior.
- `main.py` and `repair_tool.py` expose the application entry points.

## Development

The repository uses locked dependencies, Ruff, the Python unittest suite,
package builds, Conventional Commits, and required GitHub checks. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the authoritative contribution and
verification workflow.

## Releases

Prebuilt releases are published through the repository's
[GitHub Releases](https://github.com/roymejia2217/ImageMD/releases).

## Contributing

Pull requests are accepted when they follow the repository's governed change
process. Read [CONTRIBUTING.md](CONTRIBUTING.md) before making changes.

Use [GitHub Issues](https://github.com/roymejia2217/ImageMD/issues) for project
questions and defect reports. Contributions must satisfy the repository's
branch, Conventional Commit, verification, and required-check policies.

## License

MIT © 2026 Roy Mejia. See [LICENSE](LICENSE).
