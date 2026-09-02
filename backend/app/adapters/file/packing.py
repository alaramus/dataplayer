"""Making an archive out of a selection, and taking one apart again.

Reading an archive in place is `archive.py`, and that is ZIP only because
listing a tar means reading it end to end (D53). Packing and unpacking have no
such requirement: both are one pass over the whole file, so the tar family is
here beside ZIP.

Nothing here trusts a name written inside an archive. An entry goes through
the same containment rule as every other path in this source, and an archive
holding one that fails it is refused whole rather than half-extracted — the
half being whatever the entry decided to write.
"""

import bz2
import gzip
import lzma
import os
import tarfile
import tempfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO, Literal, cast

from app.adapters.actions import ActionRefused
from app.adapters.file.session import stays_inside_root

# The formats one may be made in. Every one of them is in the standard
# library, and every one of them is something a person receives by email.
PackFormat = Literal["zip", "tar", "tar.gz", "tar.bz2", "tar.xz"]

PACK_SUFFIX: dict[PackFormat, str] = {
    "zip": ".zip",
    "tar": ".tar",
    "tar.gz": ".tar.gz",
    "tar.bz2": ".tar.bz2",
    "tar.xz": ".tar.xz",
}

# How a tar is opened for writing, per format. `w` is no compression at all.
# Typed as the literals `tarfile.open` declares, so a mode that is not one of
# them fails here rather than at the call.
TarWriteMode = Literal["w", "w:gz", "w:bz2", "w:xz"]

_TAR_MODE: dict[PackFormat, TarWriteMode] = {
    "tar": "w",
    "tar.gz": "w:gz",
    "tar.bz2": "w:bz2",
    "tar.xz": "w:xz",
}

# What can be taken apart, longest suffix first: `.tar.gz` must be recognised
# as a tar before `.gz` calls it one compressed file.
_UNPACK_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".tar.gz", "tar"),
    (".tar.bz2", "tar"),
    (".tar.xz", "tar"),
    (".tgz", "tar"),
    (".tbz2", "tar"),
    (".txz", "tar"),
    (".tar", "tar"),
    (".zip", "zip"),
    (".gz", "gzip"),
    (".bz2", "bzip2"),
    (".xz", "xz"),
)

# The same ceilings a download is held to. An archive somebody unpacks lands
# in their own storage, so the bound is about the disk as well as the wait.
MAX_ENTRIES = 10_000
MAX_BYTES = 2 * 1024 * 1024 * 1024
CHUNK_BYTES = 256 * 1024


class NotUnpackable(ValueError):
    """The name says this file is not an archive this source can open."""


@dataclass(frozen=True)
class Unpacked:
    """What came out of one archive."""

    entries: int
    bytes_written: int


def unpack_kind(name: str) -> str | None:
    """Which kind of archive a name says this is, or nothing.

    By name, like every other classification in this source: opening one file
    per row to find out would cost a read per catalog entry (see formats.py).
    """
    lowered = name.lower()
    for suffix, kind in _UNPACK_SUFFIXES:
        if lowered.endswith(suffix) and len(lowered) > len(suffix):
            return kind
    return None


def is_unpackable(name: str) -> bool:
    return unpack_kind(name) is not None


def unpacked_name(name: str) -> str:
    """What the folder or file an archive is unpacked into is called.

    The name without the suffix that made it an archive: `reports.tar.gz`
    becomes `reports`, and a single compressed `notes.txt.gz` becomes
    `notes.txt`.
    """
    lowered = name.lower()
    for suffix, _ in _UNPACK_SUFFIXES:
        if lowered.endswith(suffix) and len(lowered) > len(suffix):
            return name[: -len(suffix)]
    return name


def pack(targets: Sequence[Path], into: Path, format: PackFormat) -> None:
    """Write one archive of `targets` at `into`, or leave nothing behind.

    Built beside its destination and moved into place, so a failure halfway
    through leaves no half-archive with the name somebody will look for.
    """
    descriptor, temporary = tempfile.mkstemp(
        prefix=".dataplayer-packing-", dir=str(into.parent)
    )
    os.close(descriptor)
    staged = Path(temporary)
    try:
        if format == "zip":
            _pack_zip(targets, staged)
        else:
            _pack_tar(targets, staged, format)
        os.replace(staged, into)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def unpack(source: Path, into: Path) -> Unpacked:
    """Expand one archive into a directory that must already exist.

    Every member is judged before anything is written: an archive holding one
    name that escapes is refused whole, because a caller who is told "that was
    refused" must not have to wonder what landed first.
    """
    kind = unpack_kind(source.name)
    if kind is None:
        raise NotUnpackable(f"{source.name} is not an archive this source opens")
    if kind == "zip":
        return _unpack_zip(source, into)
    if kind == "tar":
        return _unpack_tar(source, into)
    return _unpack_single(source, into, kind)


def _pack_zip(targets: Sequence[Path], staged: Path) -> None:
    with zipfile.ZipFile(
        staged, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
    ) as output:
        state = _Budget()
        for target in targets:
            _add_to_zip(output, target, target.name, state)


def _pack_tar(targets: Sequence[Path], staged: Path, format: PackFormat) -> None:
    with tarfile.open(staged, _TAR_MODE[format]) as output:
        state = _Budget()
        for target in targets:
            _add_to_tar(output, target, target.name, state)


class _Budget:
    """The two ceilings, carried down the walk rather than counted twice."""

    def __init__(self) -> None:
        self.entries = 0
        self.total = 0

    def entry(self) -> None:
        self.entries += 1
        if self.entries > MAX_ENTRIES:
            raise ActionRefused("too_large", "That is too many files to archive")

    def bytes(self, more: int) -> None:
        self.total += more
        if self.total > MAX_BYTES:
            raise ActionRefused("too_large", "That is too much data to archive")


def _add_to_zip(
    output: zipfile.ZipFile, target: Path, name: str, state: _Budget
) -> None:
    if target.is_symlink():
        raise ActionRefused("not_applicable", "Symbolic links are not archived")
    state.entry()
    if target.is_dir():
        output.writestr(f"{name}/", b"")
        for child in sorted(target.iterdir(), key=lambda one: one.name.casefold()):
            _add_to_zip(output, child, f"{name}/{child.name}", state)
        return
    if not target.is_file():
        raise ActionRefused("not_applicable", f"{target.name} cannot be archived")
    with target.open("rb") as source, output.open(name, "w") as destination:
        while chunk := source.read(CHUNK_BYTES):
            state.bytes(len(chunk))
            destination.write(chunk)


def _add_to_tar(
    output: tarfile.TarFile, target: Path, name: str, state: _Budget
) -> None:
    if target.is_symlink():
        raise ActionRefused("not_applicable", "Symbolic links are not archived")
    state.entry()
    if target.is_dir():
        output.add(target, arcname=name, recursive=False)
        for child in sorted(target.iterdir(), key=lambda one: one.name.casefold()):
            _add_to_tar(output, child, f"{name}/{child.name}", state)
        return
    if not target.is_file():
        raise ActionRefused("not_applicable", f"{target.name} cannot be archived")
    state.bytes(target.stat().st_size)
    output.add(target, arcname=name, recursive=False)


def _safe_member(name: str) -> PurePosixPath:
    """One member's path inside the destination, or a refusal.

    The one containment rule this source has, applied to a string that came
    out of a file somebody else wrote — which is the same kind of string as a
    node id from a browser.
    """
    cleaned = name.replace("\\", "/").rstrip("/")
    if not cleaned or not stays_inside_root(cleaned):
        raise ActionRefused(
            "not_applicable", f"The archive holds a name that leaves it: {name}"
        )
    return PurePosixPath(cleaned)


def _unpack_zip(source: Path, into: Path) -> Unpacked:
    with zipfile.ZipFile(source) as opened:
        infos = opened.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ActionRefused("too_large", "The archive holds too many files")
        planned = [(info, _safe_member(info.filename)) for info in infos]
        total = sum(info.file_size for info, _ in planned)
        if total > MAX_BYTES:
            raise ActionRefused("too_large", "The archive expands to too much data")
        written = 0
        for info, member in planned:
            target = into / member
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with opened.open(info) as reading, target.open("wb") as writing:
                while chunk := reading.read(CHUNK_BYTES):
                    written += len(chunk)
                    writing.write(chunk)
        return Unpacked(entries=len(planned), bytes_written=written)


def _unpack_tar(source: Path, into: Path) -> Unpacked:
    with tarfile.open(source) as opened:
        members = opened.getmembers()
        if len(members) > MAX_ENTRIES:
            raise ActionRefused("too_large", "The archive holds too many files")
        total = 0
        for member in members:
            if member.islnk() or member.issym():
                raise ActionRefused(
                    "not_applicable", "The archive holds a link, which is not expanded"
                )
            if not (member.isfile() or member.isdir()):
                raise ActionRefused(
                    "not_applicable",
                    f"The archive holds something that is not a file: {member.name}",
                )
            _safe_member(member.name)
            total += member.size
        if total > MAX_BYTES:
            raise ActionRefused("too_large", "The archive expands to too much data")
        # `data` refuses absolute paths, links and device files on its own; the
        # walk above is this source's own rule, and both run.
        opened.extractall(into, filter="data")
        return Unpacked(entries=len(members), bytes_written=total)


def _open_compressed(source: Path, kind: str) -> IO[bytes]:
    """One decompressing reader, chosen from a closed set of three.

    The three return three different classes that read bytes the same way, so
    the shared interface is what this is typed as.
    """
    if kind == "gzip":
        return cast("IO[bytes]", gzip.open(source, "rb"))
    if kind == "bzip2":
        return cast("IO[bytes]", bz2.open(source, "rb"))
    return cast("IO[bytes]", lzma.open(source, "rb"))


def _unpack_single(source: Path, into: Path, kind: str) -> Unpacked:
    """One compressed file, which is a file rather than an archive.

    `notes.txt.gz` is not a container: it holds one stream and no names at
    all, so there is nothing to check for containment beyond the name this
    source gives the result.
    """
    target = into / unpacked_name(source.name)
    written = 0
    with _open_compressed(source, kind) as reading, target.open("wb") as writing:
        while chunk := reading.read(CHUNK_BYTES):
            written += len(chunk)
            if written > MAX_BYTES:
                target.unlink(missing_ok=True)
                raise ActionRefused(
                    "too_large", "The archive expands to too much data"
                )
            writing.write(chunk)
    return Unpacked(entries=1, bytes_written=written)
