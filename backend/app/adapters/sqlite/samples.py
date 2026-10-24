"""The lab, as a SQLite file in a person's storage (D261).

A SQLite source opens a file and starts no server, so its sample is not the
installer a server this application started is filled by (D80): it is a file
written beside the other sample files, which a connection then opens.

The script is this repository's own and runs whole, with SQLite's own
`executescript`, on a plain connection: the source's hardening is for files
a person brings, and this one is written here.
"""

import os
import sqlite3
from pathlib import Path

SAMPLE_FILE = "lab.db"
SCRIPT = Path(__file__).parent / "sample_data" / "sqlite_lab.sql"


def write_sample_database(path: Path) -> None:
    """The lab at `path`, made afresh.

    Written beside it first and moved into place, so a connection reading
    the old file never sees half of the new one.
    """
    making = path.with_name(path.name + ".making")
    making.unlink(missing_ok=True)
    connection = sqlite3.connect(making)
    try:
        connection.executescript(SCRIPT.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()
    os.replace(making, path)
