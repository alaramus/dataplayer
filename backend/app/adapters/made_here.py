"""A new database file, made in its owner's storage (D263, D404).

The counterpart of starting a server here (D80) for a type that starts
nothing: making one is making a file. Shared by SQLite and DuckDB, which
differ in the file's suffix, what is kept beside it, and how it is filled.
"""

import re
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from app.adapters.file.storage import LocalStorage
from app.adapters.protocol import MadeSource, MakeChoice
from app.core.translation import say

FOLDER = "databases"
STEM = "dataplayer"
# Long enough for any name a person types, short enough for every file system.
STEM_LIMIT = 100
_UNSAFE = re.compile(r"[^\w.-]+")


def stem_of(name: str) -> str:
    """A file name made of a connection's name: what a person would have typed,
    with everything a path could misread replaced."""
    stem = _UNSAFE.sub("-", name).strip("-.")[:STEM_LIMIT].strip("-.")
    return stem or STEM


def _folder(storage: LocalStorage, folder: str) -> str:
    """The folder, made level by level where it is missing, as a path below
    the home. Every level goes through the storage's containment rule (D8)."""
    parts = PurePosixPath(folder.strip().strip("/") or FOLDER).parts
    made: list[str] = []
    for part in parts:
        made.append(part)
        place = storage.place("/".join(made))
        found = storage.entry(place)
        if found is None:
            storage.make_directory(place)
        elif not found.is_directory:
            raise ValueError(say("{folder} is a file, not a folder", folder="/".join(made)))
    return "/".join(made)


def make_file(
    home_dir: Path, choice: MakeChoice, *, suffix: str, write: Callable[[Path, MakeChoice], None]
) -> MadeSource:
    """The file, made by `write`, and the options a connection to it takes.

    A taken name is numbered rather than replaced: an existing database is
    somebody's data.
    """
    storage = LocalStorage(home_dir)
    folder = _folder(storage, choice.folder or FOLDER)
    folder_place = storage.place(folder)
    named = (choice.name or "").strip()
    stem = stem_of(named)
    number = 1
    while True:
        filename = f"{stem}{suffix}" if number == 1 else f"{stem}-{number}{suffix}"
        place = storage.child(folder_place, filename)
        if storage.entry(place) is None:
            break
        number += 1
    write(storage.path_of(place), choice)
    relative = f"{folder}/{filename}"
    return MadeSource(
        options={"path": relative},
        where=relative,
        # Named as asked, or after the file when the server chose.
        name=named or PurePosixPath(filename).stem,
    )


def file_of(options: Mapping[str, Any]) -> str | None:
    """The file a connection holds: every such connection's path is below its
    owner's home (D247, D387)."""
    path = options.get("path")
    if not isinstance(path, str):
        return None
    below_home = path.strip().strip("/")
    return below_home or None


def remove(home_dir: Path, path: str, sidecars: tuple[str, ...]) -> None:
    """The database and what is kept beside it, each judged by the storage's rule (D8)."""
    storage = LocalStorage(home_dir)
    for suffix in ("", *sidecars):
        place = storage.place(f"{path}{suffix}")
        found = storage.entry(place)
        if found is not None and not found.is_directory:
            storage.remove(place)


def unmake(home_dir: Path, made: MadeSource) -> None:
    """Take a file back that no connection came to hold."""
    storage = LocalStorage(home_dir)
    place = storage.place(str(made.options["path"]))
    if storage.entry(place) is not None:
        storage.remove(place)
