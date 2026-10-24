"""What a SQLite file holds, read for a file source that lists it (D262).

A file source shows a `.db` as a file, and a database is not a text. Its tables
are what a person opens one to see, so the file is opened the way every SQLite
connection here is opened — read only, defensively, under a clock — and its
relations listed with what ANALYZE counted. Nothing else is read: rows belong
to a connection to the file.
"""

import sqlite3
import time
from pathlib import Path

from app.adapters.content import DatabaseContent, DatabaseRelation
from app.adapters.sqlite.inspection import estimates, is_system_relation, list_relations
from app.adapters.sqlite.session import Reading, harden, library_version
from app.core.translation import say

# What every SQLite database file begins with.
HEADER = b"SQLite format 3\x00"
# Relations listed at most; a file with more says how many there are.
MAX_RELATIONS = 1000
SECONDS = 5.0


def is_sqlite_file(head: bytes) -> bool:
    return head.startswith(HEADER)


def tables_of(path: Path) -> DatabaseContent:
    """The relations of the file at `path`, or a refusal saying why not."""
    with path.open("rb") as file:
        if not is_sqlite_file(file.read(len(HEADER))):
            raise ValueError(say("The file is not a SQLite database"))
    deadline = time.monotonic() + SECONDS
    try:
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, autocommit=True)
    except sqlite3.Error:
        raise ValueError(say("The database file cannot be opened")) from None
    try:
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        harden(connection, writes=False)
        reading = Reading(connection)
        relations = [row for row in list_relations(reading) if not is_system_relation(str(row["name"]), str(row["type"]))]
        counted = estimates(reading)
    except sqlite3.DatabaseError:
        raise ValueError(say("The database file is damaged")) from None
    finally:
        connection.close()
    return DatabaseContent(
        engine=f"SQLite {library_version()}",
        size_bytes=path.stat().st_size,
        relations=[
            DatabaseRelation(
                name=str(row["name"]),
                kind="view" if row["type"] == "view" else "virtual" if row["type"] == "virtual" else "table",
                row_estimate=counted.get(str(row["name"])),
            )
            for row in relations[:MAX_RELATIONS]
        ],
        total=len(relations),
    )
