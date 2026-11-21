"""A new DuckDB database, made in its owner's storage (D404).

Left to the server, it is `databases/dataplayer.duckdb` filled with the lab of
D402; chosen, it is the folder, the name, and the lab or an empty database.
There is no journal to choose: DuckDB always keeps its log. Where and under
what name is the shared rule of `app.adapters.made_here`.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import duckdb

from app.adapters import made_here
from app.adapters.duckdb.samples import write_sample_database
from app.adapters.protocol import MadeSource, MakeChoice

SUFFIX = ".duckdb"
# What DuckDB keeps beside a database while it is written.
SIDECARS = (".wal",)


def _write(path: Path, choice: MakeChoice) -> None:
    if choice.sample_data:
        write_sample_database(path)
        return
    # Opened and closed by DuckDB, so the file has DuckDB's header (D403).
    duckdb.connect(str(path)).close()


def make(home_dir: Path, choice: MakeChoice) -> MadeSource:
    return made_here.make_file(home_dir, choice, suffix=SUFFIX, write=_write)


def file_of(options: Mapping[str, Any]) -> str | None:
    return made_here.file_of(options)


def remove(home_dir: Path, path: str) -> None:
    made_here.remove(home_dir, path, SIDECARS)


def unmake(home_dir: Path, made: MadeSource) -> None:
    made_here.unmake(home_dir, made)
