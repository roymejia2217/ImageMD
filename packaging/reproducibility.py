from __future__ import annotations

import gzip
import os
import stat
import tarfile
from pathlib import Path


def source_date_epoch() -> int:
    value = os.environ.get("SOURCE_DATE_EPOCH")
    if value is None:
        raise ValueError("SOURCE_DATE_EPOCH must be set to a non-negative integer")
    try:
        epoch = int(value, 10)
    except ValueError as error:
        raise ValueError(
            "SOURCE_DATE_EPOCH must be set to a non-negative integer"
        ) from error
    if epoch < 0:
        raise ValueError("SOURCE_DATE_EPOCH must be set to a non-negative integer")
    return epoch


def write_reproducible_tar_gz(source: Path, destination: Path, arcname: str) -> None:
    epoch = source_date_epoch()
    source = Path(source)
    destination = Path(destination)
    entries = [(source, arcname.rstrip("/"))]
    entries.extend(
        (path, f"{arcname.rstrip('/')}/{path.relative_to(source).as_posix()}")
        for path in source.rglob("*")
    )
    entries.sort(key=lambda entry: entry[1])

    with destination.open("wb") as raw_output:
        with gzip.GzipFile(
            filename="", fileobj=raw_output, mode="wb", mtime=epoch
        ) as compressed_output:
            with tarfile.open(
                fileobj=compressed_output, mode="w", format=tarfile.PAX_FORMAT
            ) as archive:
                for path, member_name in entries:
                    metadata = path.lstat()
                    info = tarfile.TarInfo(member_name)
                    info.mode = stat.S_IMODE(metadata.st_mode)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = epoch
                    info.pax_headers = {}

                    if stat.S_ISDIR(metadata.st_mode):
                        info.name = member_name.rstrip("/") + "/"
                        info.type = tarfile.DIRTYPE
                        archive.addfile(info)
                    elif stat.S_ISREG(metadata.st_mode):
                        info.size = metadata.st_size
                        with path.open("rb") as file_contents:
                            archive.addfile(info, file_contents)
                    elif stat.S_ISLNK(metadata.st_mode):
                        info.type = tarfile.SYMTYPE
                        info.linkname = os.readlink(path)
                        archive.addfile(info)
                    else:
                        raise ValueError(f"unsupported source entry type: {path}")
