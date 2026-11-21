"""What a DuckDB file holds, read for a file source that lists it (D403).

A file source shows a `.duckdb` as a file, and a database is not a text. Its
tables are what a person opens one to see, so the file is opened read only,
by an engine sealed as every connection's is (D388), under a clock, and its
relations listed with DuckDB's estimates. Nothing else is read: rows belong to
a connection to the file.
"""

import threading
from pathlib import Path

import duckdb

from app.adapters.content import DatabaseContent, DatabaseRelation
from app.adapters.duckdb.inspection import list_relations
from app.adapters.duckdb.session import Reading, library_version, open_read_only
from app.core.translation import say

# DuckDB's magic: eight bytes of checksum, then these four.
MAGIC_AT = 8
MAGIC = b"DUCK"
# Relations listed at most; a file with more says how many there are.
MAX_RELATIONS = 1000
SECONDS = 5.0


def is_duckdb_file(head: bytes) -> bool:
    return head[MAGIC_AT : MAGIC_AT + len(MAGIC)] == MAGIC


def tables_of(path: Path) -> DatabaseContent:
    """The relations of the file at `path`, or a refusal saying why not."""
    with path.open("rb") as file:
        if not is_duckdb_file(file.read(MAGIC_AT + len(MAGIC))):
            raise ValueError(say("The file is not a DuckDB database"))
    try:
        connection = open_read_only(path)
    except duckdb.Error:
        # Written by a newer DuckDB, damaged, or held by a program writing it.
        raise ValueError(say("The database file cannot be opened")) from None
    clock = threading.Timer(SECONDS, connection.interrupt)
    clock.start()
    try:
        relations = list_relations(Reading(connection))
    except duckdb.Error:
        raise ValueError(say("The database file cannot be read")) from None
    finally:
        clock.cancel()
        connection.close()
    return DatabaseContent(
        engine=f"DuckDB {library_version()}",
        size_bytes=path.stat().st_size,
        relations=[
            DatabaseRelation(
                # A relation outside `main` is named with its schema.
                name=str(row["name"]) if row["schema_name"] == "main" else f"{row['schema_name']}.{row['name']}",
                kind="view" if row["type"] == "view" else "table",
                row_estimate=None if row["estimated_size"] is None else int(row["estimated_size"]),
            )
            for row in relations[:MAX_RELATIONS]
        ],
        total=len(relations),
    )
