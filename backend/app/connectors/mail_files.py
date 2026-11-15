"""An attachment kept in its owner's folder (D371), and a file of that folder
attached to a letter (D374).

Under `Mail/<address>/` of the person's storage: a folder the server names,
never the client (D8), and a write that counts against the person's limit
(D324).
"""

import mimetypes
import re
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from app.adapters.actions import StorageFull
from app.adapters.explorer.storage import ROOT, is_plain_name
from app.adapters.file.storage import LocalStorage
from app.adapters.mailbox import OutgoingFile
from app.core.translation import say
from app.users.storage import used_bytes

FOLDER = "Mail"
_UNSAFE = re.compile(r'[\x00-\x1f<>:"/\\|?*]')
_MAX_NAME = 150
# Python's own table rather than the module's: on Windows that one reads the
# registry, and a CSV becomes an Excel sheet on one machine and not another.
_TYPES = mimetypes.MimeTypes()


def safe_name(name: str, fallback: str = "attachment") -> str:
    """A name both platforms take as one plain file name."""
    cleaned = _UNSAFE.sub("_", name).strip().rstrip(". ")
    if len(cleaned) > _MAX_NAME:
        path = PurePosixPath(cleaned)
        suffix = path.suffix[:20]
        cleaned = path.stem[: _MAX_NAME - len(suffix)] + suffix
    return cleaned if cleaned and is_plain_name(cleaned) else fallback


class StoredEntry(BaseModel):
    name: str
    # Its path in the storage, which is how a letter names it.
    path: str
    is_directory: bool
    size: int


class FolderListing(BaseModel):
    # The folder listed, empty for the top.
    path: str
    entries: list[StoredEntry]


class TooLarge(Exception):
    """The files named come to more than what a letter may still carry."""


def _storage(home: Path) -> LocalStorage:
    return LocalStorage(home)


def listing(home: Path, path: str) -> FolderListing:
    """One folder of the storage, folders first; links out are not listed (D374).

    Blocking work: the caller runs it in a thread.
    """
    files = _storage(home)
    place = files.place(path or None)
    entry = files.entry(place) if place != ROOT else None
    if place != ROOT and (entry is None or not entry.is_directory):
        raise ValueError(say("There is no such folder in your storage"))
    entries = [
        StoredEntry(
            name=one.name,
            path=one.place.key,
            is_directory=one.is_directory,
            size=0 if one.is_directory else one.size_bytes,
        )
        for one in files.entries(place)
        if not one.name.startswith(".")
    ]
    entries.sort(key=lambda one: (not one.is_directory, one.name.lower()))
    return FolderListing(path=place.key, entries=entries)


def read_stored(home: Path, paths: list[str], room: int) -> list[OutgoingFile]:
    """The files a letter names, each checked by the one containment rule (D8).

    A folder, a missing file and a path out of the storage are refused; what
    they come to together is measured before anything is read.
    """
    files = _storage(home)
    chosen = []
    total = 0
    for path in paths:
        place = files.place(path)
        entry = files.entry(place) if place != ROOT else None
        if entry is None or entry.is_directory:
            raise ValueError(say("There is no such file in your storage: {path}", path=path))
        total += entry.size_bytes
        if total > room:
            raise TooLarge()
        chosen.append((place, entry))
    found: list[OutgoingFile] = []
    for place, entry in chosen:
        with files.open(place) as handle:
            body = handle.read(entry.size_bytes + 1)
        if len(body) > entry.size_bytes:
            raise TooLarge()
        found.append(
            OutgoingFile(
                filename=safe_name(entry.name),
                media_type=_TYPES.guess_type(entry.name)[0] or "application/octet-stream",
                body=body,
            )
        )
    return found


def keep_attachment(
    *, home: Path, address: str, filename: str, body: bytes, limit_bytes: int | None
) -> str:
    """Write the bytes beside nothing they would replace; the path in the home.

    Blocking work: the caller runs it in a thread.
    """
    directory = home / FOLDER / safe_name(address, "mailbox")
    for one in (home, home / FOLDER, directory):
        if one.is_symlink():
            raise ValueError("The mail folder is not safe")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        directory.resolve().relative_to(home.resolve(strict=True))
    except (OSError, ValueError):
        raise ValueError("The mail folder is not safe") from None

    if limit_bytes is not None:
        after = used_bytes(home) + len(body)
        if after > limit_bytes:
            raise StorageFull(after, limit_bytes)

    name = safe_name(filename)
    stem, suffix = PurePosixPath(name).stem, PurePosixPath(name).suffix
    destination = directory / name
    number = 2
    while destination.exists():
        destination = directory / f"{stem} ({number}){suffix}"
        number += 1
    temporary = destination.with_name(destination.name + ".part")
    try:
        temporary.write_bytes(body)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination.relative_to(home).as_posix()
