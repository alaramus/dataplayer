"""Reading a ZIP archive: its tree, and one entry at a time.

An archive is a directory that happens to be one file (D53). Listing it reads
the central directory and inflates nothing; reading one entry expands it into a
temporary file bounded at both ends, so every reader in this source — which all
read a path — works inside an archive without a second implementation.

Nothing here trusts a name written inside the file: an entry name goes through
the same containment rule as every other path, and an archive holding one that
fails it is refused whole.
"""

import os
import stat
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from app.adapters.explorer.storage import stays_inside_root
from app.core.translation import say

# The same number D49 refuses to build an archive past. Listing inflates
# nothing, so this is about how many nodes the catalog would have to carry.
MAX_ENTRIES = 10_000

# One entry is expanded whole, so one ceiling covers every viewer; each viewer
# then applies its own on top of it.
MAX_ENTRY_BYTES = 32 * 1024 * 1024

EXPAND_CHUNK_BYTES = 256 * 1024


class NotAnArchive(ValueError):
    """The bytes under an archive's name are not one."""


class UnsafeArchive(ValueError):
    """An entry names a place outside the archive it is in."""


@dataclass(frozen=True)
class Entry:
    """One member of an archive, as the central directory describes it."""

    # The path inside the archive, already judged safe.
    path: str
    name: str
    is_directory: bool
    size_bytes: int
    compressed_bytes: int
    modified_at: datetime | None
    # Listed, never followed, never read (D53).
    is_link: bool = False
    is_encrypted: bool = False

    @property
    def readable(self) -> bool:
        return not (self.is_directory or self.is_link or self.is_encrypted)


def children(path: Path, inside: str | None) -> list[Entry]:
    """The entries one level below `inside`, directories included. Blocking.

    Directories are synthesized from the paths of the entries under them: an
    archive may name a folder in an entry of its own or not name it at all, and
    a reader should see the same tree either way.
    """
    prefix = "" if inside is None or inside == "" else f"{inside.rstrip('/')}/"
    files: dict[str, Entry] = {}
    directories: dict[str, Entry] = {}

    for entry in _entries(path):
        if not entry.path.startswith(prefix):
            continue
        rest = entry.path[len(prefix) :]
        if rest == "":
            continue
        head, _, tail = rest.partition("/")
        if tail != "":
            directories.setdefault(head, _implied(prefix + head, head))
        elif entry.is_directory:
            # A folder the archive named itself, with its own date.
            directories[head] = entry
        else:
            files[head] = entry

    listed = [*directories.values(), *files.values()]
    return sorted(
        listed, key=lambda item: (not item.is_directory, item.name.casefold())
    )


@dataclass(frozen=True)
class Totals:
    """The whole archive counted from its central directory. Nothing inflated."""

    entries: int
    files: int
    directories: int
    size_bytes: int
    compressed_bytes: int
    encrypted: int
    links: int


def totals(path: Path) -> Totals:
    """What the archive holds, as it declares it. Blocking.

    Only the entries the archive names, so a folder implied by the path of an
    entry is not counted: this is what is in the file, and `children` is what a
    reader walks.
    """
    entries = _entries(path)
    files = [entry for entry in entries if not entry.is_directory]
    return Totals(
        entries=len(entries),
        files=len(files),
        directories=len(entries) - len(files),
        size_bytes=sum(entry.size_bytes for entry in files),
        compressed_bytes=sum(entry.compressed_bytes for entry in files),
        encrypted=sum(1 for entry in entries if entry.is_encrypted),
        links=sum(1 for entry in entries if entry.is_link),
    )


def entry_at(path: Path, inside: str) -> Entry:
    """One entry named by its path inside the archive. Blocking."""
    wanted = inside.strip("/")
    if wanted == "":
        raise ValueError(say("An archive is not an entry of itself"))
    below = f"{wanted}/"
    implied = False
    for entry in _entries(path):
        if entry.path == wanted:
            return entry
        implied = implied or entry.path.startswith(below)
    if implied:
        # A folder the archive never named, but which its entries imply.
        return _implied(wanted, PurePosixPath(wanted).name)
    raise ValueError(say("No such entry in this archive: {inside}", inside=inside))


def extract(path: Path, inside: str) -> Path:
    """One entry as a temporary file the caller owns. Blocking.

    Bounded at both ends: the size the archive declares is checked before
    anything is read, and the bytes are counted as they are written. The second
    bound is this module's own — `zipfile` stops at the declared size itself,
    and an entry holding more than it admits to fails its checksum there — but
    the ceiling should rest on something this module can see (D53).
    """
    entry = entry_at(path, inside)
    if entry.is_directory:
        raise ValueError(say("A folder inside an archive cannot be read"))
    if entry.is_link:
        raise ValueError(say("A link inside an archive is not followed"))
    if entry.is_encrypted:
        raise ValueError(say("This entry is encrypted and cannot be read here"))
    if entry.size_bytes > MAX_ENTRY_BYTES:
        raise ValueError(
            say(
                "This entry is larger than {megabytes} MB",
                megabytes=MAX_ENTRY_BYTES // (1024 * 1024),
            )
        )

    descriptor, temporary = tempfile.mkstemp(prefix="dataplayer-entry-")
    os.close(descriptor)
    target = Path(temporary)
    try:
        with _opened(path) as opened, opened.open(entry.path) as source:
            written = 0
            with target.open("wb") as sink:
                while chunk := source.read(EXPAND_CHUNK_BYTES):
                    written += len(chunk)
                    if written > MAX_ENTRY_BYTES:
                        raise ValueError(say("This entry expands to more than it declares"))
                    sink.write(chunk)
    except zipfile.BadZipFile:
        target.unlink(missing_ok=True)
        raise ValueError(say("This entry is damaged and could not be read")) from None
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


@contextmanager
def expanded(path: Path, inside: str) -> Iterator[Path]:
    """The same file, for a reader that is done with it when it returns."""
    target = extract(path, inside)
    try:
        yield target
    finally:
        target.unlink(missing_ok=True)


def _entries(path: Path) -> list[Entry]:
    """Every entry of the archive, with every name already judged."""
    with _opened(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ValueError(
                say("This archive holds more than {count} entries", count=MAX_ENTRIES)
            )
        return [_entry(info) for info in infos]


def _entry(info: zipfile.ZipInfo) -> Entry:
    name = info.filename.rstrip("/")
    # The one containment rule, for a name written inside the file (D53).
    if not stays_inside_root(name):
        raise UnsafeArchive(
            say("This archive holds an entry that leaves it: {name}", name=info.filename)
        )
    mode = info.external_attr >> 16
    return Entry(
        path=name,
        name=PurePosixPath(name).name,
        is_directory=info.is_dir(),
        size_bytes=info.file_size,
        compressed_bytes=info.compress_size,
        modified_at=_modified(info),
        is_link=stat.S_ISLNK(mode),
        is_encrypted=bool(info.flag_bits & 0x1),
    )


def _implied(path: str, name: str) -> Entry:
    """A folder the archive did not name, but whose contents say it is there."""
    return Entry(
        path=path,
        name=name,
        is_directory=True,
        size_bytes=0,
        compressed_bytes=0,
        modified_at=None,
    )


def _modified(info: zipfile.ZipInfo) -> datetime | None:
    try:
        return datetime(*info.date_time, tzinfo=UTC)
    except ValueError:
        # A zip may state a date no calendar has; the entry is still an entry.
        return None


@contextmanager
def _opened(path: Path) -> Iterator[zipfile.ZipFile]:
    """The archive, with only the opening judged.

    The `try` covers the open and nothing else on purpose: a checksum that
    fails while an entry is being read is a damaged entry, and reporting it as
    "this file is not an archive" would name the wrong thing.
    """
    try:
        opened = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise NotAnArchive(say("This file is not an archive")) from None
    try:
        yield opened
    finally:
        opened.close()
