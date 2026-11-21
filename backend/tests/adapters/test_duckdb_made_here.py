"""A new DuckDB database made in its owner's storage (D404)."""

from pathlib import Path

import duckdb
import pytest

from app.adapters.duckdb.adapter import DuckdbAdapter
from app.adapters.duckdb.options import DuckdbOptions
from app.adapters.protocol import MakeChoice, MakesSourceHere
from app.adapters.registry import get
from app.adapters.routes import info


def _tables(path: Path) -> list[str]:
    connection = duckdb.connect(str(path))
    try:
        return [str(row[0]) for row in connection.execute("SELECT table_name FROM duckdb_tables()").fetchall()]
    finally:
        connection.close()


def test_the_type_makes_a_source_here_without_a_journal_to_choose() -> None:
    assert issubclass(DuckdbAdapter, MakesSourceHere)
    said = info(get("duckdb"))
    assert said.makes_here is True and said.makes_here_wal is False
    assert info(get("sqlite")).makes_here_wal is True


async def test_left_to_the_server_it_is_dataplayer_duckdb_with_the_lab(tmp_path: Path) -> None:
    made = DuckdbAdapter.make_source_here(tmp_path, MakeChoice())

    path = tmp_path / "databases" / "dataplayer.duckdb"
    assert made.options == {"path": "databases/dataplayer.duckdb"}
    assert made.name == "dataplayer"
    assert {"organizations", "tasks", "projects"} <= set(_tables(path))
    check = await DuckdbAdapter(DuckdbOptions.model_validate(made.options), tmp_path).check_connection()
    assert check.ok, check


async def test_chosen_it_is_named_numbered_and_may_be_empty(tmp_path: Path) -> None:
    first = DuckdbAdapter.make_source_here(tmp_path, MakeChoice(name="Sales 2026", folder="work/db", sample_data=False))
    second = DuckdbAdapter.make_source_here(tmp_path, MakeChoice(name="Sales 2026", folder="work/db", sample_data=False))

    assert first.options == {"path": "work/db/Sales-2026.duckdb"}
    assert second.options == {"path": "work/db/Sales-2026-2.duckdb"}
    path = tmp_path / "work" / "db" / "Sales-2026.duckdb"
    assert path.read_bytes()[8:12] == b"DUCK"
    assert _tables(path) == []


def test_a_folder_outside_the_storage_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        DuckdbAdapter.make_source_here(tmp_path, MakeChoice(folder="../elsewhere"))


def test_the_file_and_its_log_are_removed_together(tmp_path: Path) -> None:
    made = DuckdbAdapter.make_source_here(tmp_path, MakeChoice(sample_data=False))
    path = str(made.options["path"])
    (tmp_path / f"{path}.wal").write_bytes(b"log")

    assert DuckdbAdapter.source_file_here(made.options) == path
    DuckdbAdapter.remove_source_here(tmp_path, path)

    assert sorted(entry.name for entry in (tmp_path / "databases").iterdir()) == []
