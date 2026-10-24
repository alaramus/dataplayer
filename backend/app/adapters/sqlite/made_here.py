"""A new SQLite database, made in its owner's storage (D263).

The counterpart of starting a server here (D80): a SQLite source starts
nothing, so making one is making a file. Left to the server, it is
`databases/dataplayer.db` filled with the lab of D261; chosen, it is the folder,
the name, the lab or not, and the journal a person asked for.
"""

import re
import sqlite3
from pathlib import Path, PurePosixPath

from app.adapters.file.storage import LocalStorage
from app.adapters.protocol import MadeSource, MakeChoice
from app.adapters.sqlite.samples import write_sample_database
from app.core.translation import say

FOLDER = "databases"
STEM = "dataplayer"
SUFFIX = ".db"
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


def make(home_dir: Path, choice: MakeChoice) -> MadeSource:
    """The file, made, and the options a connection to it takes.

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
        filename = f"{stem}{SUFFIX}" if number == 1 else f"{stem}-{number}{SUFFIX}"
        place = storage.child(folder_place, filename)
        if storage.entry(place) is None:
            break
        number += 1
    path = storage.path_of(place)
    if choice.sample_data:
        write_sample_database(path)
    connection = sqlite3.connect(path)
    try:
        # An empty file is written with SQLite's header, by SQLite: an empty
        # file is a database to SQLite and not one to whatever reads the
        # header (D262).
        if not choice.sample_data:
            connection.execute("VACUUM")
        if choice.wal:
            connection.execute("PRAGMA journal_mode = WAL")
    finally:
        connection.close()
    relative = f"{folder}/{filename}"
    return MadeSource(
        options={"path": relative},
        where=relative,
        # Named as asked, or after the file when the server chose.
        name=named or PurePosixPath(filename).stem,
    )


def unmake(home_dir: Path, made: MadeSource) -> None:
    """Take a file back that no connection came to hold."""
    storage = LocalStorage(home_dir)
    place = storage.place(str(made.options["path"]))
    if storage.entry(place) is not None:
        storage.remove(place)
