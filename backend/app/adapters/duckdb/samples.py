"""The lab, as a DuckDB file in a person's storage (D402).

A DuckDB source opens a file and starts no server, so its sample is a file
written beside the other sample files, which a connection then opens, as
SQLite's is (D261).

The script is this repository's own and runs whole on a plain connection: the
source's lock is for files a person brings, and this one is written here.
"""

import os
from pathlib import Path

import duckdb

SAMPLE_FILE = "lab.duckdb"
SCRIPT = Path(__file__).parent / "sample_data" / "duckdb_lab.sql"


def write_sample_database(path: Path) -> None:
    """The lab at `path`, made afresh.

    Written beside it first and moved into place, so a connection reading the
    old file never sees half of the new one. Closing the connection writes the
    log into the file, so nothing is left beside it.
    """
    making = path.with_name(path.name + ".making")
    making.unlink(missing_ok=True)
    Path(f"{making}.wal").unlink(missing_ok=True)
    connection = duckdb.connect(str(making))
    try:
        connection.execute(SCRIPT.read_text(encoding="utf-8"))
    finally:
        connection.close()
    os.replace(making, path)
