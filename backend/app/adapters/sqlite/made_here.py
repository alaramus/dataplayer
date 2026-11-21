"""A new SQLite database, made in its owner's storage (D263).

Left to the server, it is `databases/dataplayer.db` filled with the lab of
D261; chosen, it is the folder, the name, the lab or not, and the journal a
person asked for. Where and under what name is the shared rule of
`app.adapters.made_here`.
"""

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.adapters import made_here
from app.adapters.protocol import MadeSource, MakeChoice
from app.adapters.sqlite.samples import write_sample_database

SUFFIX = ".db"
# What SQLite keeps beside a database while it is open or was left mid-write.
SIDECARS = ("-wal", "-shm", "-journal")


def _write(path: Path, choice: MakeChoice) -> None:
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


def make(home_dir: Path, choice: MakeChoice) -> MadeSource:
    return made_here.make_file(home_dir, choice, suffix=SUFFIX, write=_write)


def file_of(options: Mapping[str, Any]) -> str | None:
    return made_here.file_of(options)


def remove(home_dir: Path, path: str) -> None:
    made_here.remove(home_dir, path, SIDECARS)


def unmake(home_dir: Path, made: MadeSource) -> None:
    made_here.unmake(home_dir, made)
