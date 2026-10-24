"""A SQLite file in a file source opens as the tables it holds (D262)."""

import sqlite3
from pathlib import Path

import pytest

import app.adapters.sqlite  # noqa: F401 — registers the reader the explorer asks for
from app.adapters.content import ContentRequest, ContentResult, DatabaseContent
from app.adapters.explorer.content import ExplorerContent
from app.adapters.explorer.formats import representations_of
from app.adapters.file.storage import LocalStorage
from tests.adapters.sqlite_fixture import FILE, analyze, build


@pytest.fixture
def root(tmp_path: Path) -> Path:
    build(tmp_path)
    analyze(tmp_path / FILE)
    return tmp_path


async def _read(root: Path, node_id: str) -> ContentResult:
    return await ExplorerContent(LocalStorage(root)).read_content(
        ContentRequest(node_id=node_id, representation="database")
    )


def test_a_database_file_is_offered_as_a_database_and_nothing_else() -> None:
    for name in ("shop.db", "shop.sqlite", "shop.sqlite3", "shop.db3"):
        assert [item.kind for item in representations_of(name)] == ["database"]


async def test_its_tables_views_and_estimates_are_read_without_its_own(root: Path) -> None:
    result = await _read(root, FILE)

    assert isinstance(result, DatabaseContent)
    by_name = {relation.name: relation for relation in result.relations}
    assert result.engine.startswith("SQLite ")
    assert by_name["items"].kind == "table"
    assert by_name["items"].row_estimate == 4
    assert by_name["cheap"].kind == "view"
    assert by_name["notes"].kind == "virtual"
    # SQLite's own tables and the ones a virtual table keeps are not the file's.
    assert not any(name.startswith("sqlite_") or name.startswith("notes_") for name in by_name)
    assert result.total == len(result.relations)


async def test_reading_it_changes_nothing_in_the_file(root: Path) -> None:
    before = (root / FILE).read_bytes()

    await _read(root, FILE)

    assert (root / FILE).read_bytes() == before


async def test_a_file_named_like_a_database_that_is_not_one_says_so(root: Path) -> None:
    (root / "notes.db").write_text("just text", encoding="utf-8")

    with pytest.raises(ValueError, match="not a SQLite database"):
        await _read(root, "notes.db")


async def test_a_view_that_calls_a_refused_function_cannot_run_while_it_is_listed(root: Path) -> None:
    connection = sqlite3.connect(root / FILE)
    connection.execute("CREATE VIEW sneaky AS SELECT load_extension('x')")
    connection.commit()
    connection.close()

    result = await _read(root, FILE)

    assert isinstance(result, DatabaseContent)
    assert "sneaky" in {relation.name for relation in result.relations}
