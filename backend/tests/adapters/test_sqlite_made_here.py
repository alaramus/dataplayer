"""A new SQLite database made in its owner's storage (D263)."""

import sqlite3
from pathlib import Path

import pytest

from app.adapters.protocol import MakeChoice, MakesSourceHere
from app.adapters.sqlite.adapter import SqliteAdapter
from app.adapters.sqlite.made_here import stem_of
from app.adapters.sqlite.options import SqliteOptions


def _tables(path: Path) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        return [row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")]
    finally:
        connection.close()


def _journal(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        return str(connection.execute("PRAGMA journal_mode").fetchone()[0])
    finally:
        connection.close()


def test_the_type_says_it_makes_a_source_here() -> None:
    assert issubclass(SqliteAdapter, MakesSourceHere)


@pytest.mark.parametrize(
    ("name", "stem"),
    [
        ("Sales 2026", "Sales-2026"),
        ("../../etc/passwd", "etc-passwd"),
        ("отчёты", "отчёты"),
        ("  ", "dataplayer"),
        ("a" * 300, "a" * 100),
    ],
)
def test_a_name_becomes_a_file_name_a_path_cannot_misread(name: str, stem: str) -> None:
    assert stem_of(name) == stem


async def test_left_to_the_server_it_is_dataplayer_db_with_the_lab(tmp_path: Path) -> None:
    made = SqliteAdapter.make_source_here(tmp_path, MakeChoice())

    path = tmp_path / "databases" / "dataplayer.db"
    assert made.options == {"path": "databases/dataplayer.db"}
    assert made.where == "databases/dataplayer.db"
    assert made.name == "dataplayer"
    assert {"organizations", "tasks", "projects"} <= set(_tables(path))
    assert _journal(path) == "delete"
    check = await SqliteAdapter(SqliteOptions.model_validate(made.options), tmp_path).check_connection()
    assert check.ok, check


async def test_chosen_it_is_the_folder_name_and_journal_asked_for(tmp_path: Path) -> None:
    made = SqliteAdapter.make_source_here(
        tmp_path, MakeChoice(name="Sales 2026", folder="/work/db/", sample_data=False, wal=True)
    )

    path = tmp_path / "work" / "db" / "Sales-2026.db"
    assert made.where == "work/db/Sales-2026.db"
    assert made.name == "Sales 2026"
    assert path.read_bytes().startswith(b"SQLite format 3\x00")
    assert _tables(path) == []
    assert _journal(path) == "wal"
    check = await SqliteAdapter(SqliteOptions.model_validate(made.options), tmp_path).check_connection()
    assert check.ok, check


def test_a_taken_name_is_numbered_rather_than_replaced(tmp_path: Path) -> None:
    first = SqliteAdapter.make_source_here(tmp_path, MakeChoice())
    second = SqliteAdapter.make_source_here(tmp_path, MakeChoice(sample_data=False))

    assert first.where == "databases/dataplayer.db"
    assert second.where == "databases/dataplayer-2.db"
    assert second.name == "dataplayer-2"
    assert "tasks" in _tables(tmp_path / "databases" / "dataplayer.db")


@pytest.mark.parametrize("folder", ["../outside", "/../../etc"])
def test_a_folder_outside_the_storage_is_refused(tmp_path: Path, folder: str) -> None:
    home = tmp_path / "home"
    home.mkdir()

    with pytest.raises(ValueError):
        SqliteAdapter.make_source_here(home, MakeChoice(folder=folder))

    assert sorted(path.name for path in tmp_path.iterdir()) == ["home"]


def test_a_file_where_the_folder_should_be_is_refused(tmp_path: Path) -> None:
    (tmp_path / "databases").write_text("not a folder", encoding="utf-8")

    with pytest.raises(ValueError, match="not a folder"):
        SqliteAdapter.make_source_here(tmp_path, MakeChoice())


def test_unmaking_takes_the_file_back(tmp_path: Path) -> None:
    made = SqliteAdapter.make_source_here(tmp_path, MakeChoice(sample_data=False))

    SqliteAdapter.unmake_source_here(tmp_path, made)

    assert not (tmp_path / "databases" / "dataplayer.db").exists()
