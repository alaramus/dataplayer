"""A DuckDB file in a file source opens as the tables it holds (D403)."""

from pathlib import Path

import pytest

import app.adapters.duckdb  # noqa: F401 — registers the reader the explorer asks for
from app.adapters.content import ContentRequest, ContentResult, DatabaseContent
from app.adapters.explorer.content import ExplorerContent
from app.adapters.explorer.formats import database_engine, representations_of
from app.adapters.file.storage import LocalStorage
from tests.adapters.duckdb_fixture import FILE, add_reaching_view, build


@pytest.fixture
def root(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


async def _read(root: Path, node_id: str) -> ContentResult:
    return await ExplorerContent(LocalStorage(root)).read_content(
        ContentRequest(node_id=node_id, representation="database")
    )


def test_a_duckdb_file_is_offered_as_a_database_read_by_duckdb() -> None:
    for name in ("shop.duckdb", "shop.DDB"):
        assert [item.kind for item in representations_of(name)] == ["database"]
        assert database_engine(name) == "duckdb"
    assert database_engine("shop.db") == "sqlite"
    assert database_engine("shop.csv") is None


async def test_its_tables_views_and_estimates_are_read(root: Path) -> None:
    result = await _read(root, FILE)

    assert isinstance(result, DatabaseContent)
    by_name = {relation.name: relation for relation in result.relations}
    assert result.engine.startswith("DuckDB ")
    assert by_name["items"].kind == "table" and by_name["items"].row_estimate == 4
    assert by_name["cheap"].kind == "view"
    # Outside `main`, a relation is named with its schema.
    assert "sales.eu.orders" in by_name
    assert result.total == len(result.relations)


async def test_reading_it_changes_nothing_and_leaves_nothing_beside_it(root: Path) -> None:
    before = (root / FILE).read_bytes()
    listed = sorted(path.name for path in (root / FILE).parent.iterdir())

    await _read(root, FILE)

    assert (root / FILE).read_bytes() == before
    assert sorted(path.name for path in (root / FILE).parent.iterdir()) == listed


async def test_a_view_reaching_past_the_folder_is_listed_and_not_run(root: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside") / "secret.csv"
    outside.write_text("a\n1\n", encoding="utf-8")
    add_reaching_view(root / FILE, outside)

    result = await _read(root, FILE)

    assert isinstance(result, DatabaseContent)
    assert "reaching" in {relation.name for relation in result.relations}


async def test_a_file_named_like_a_database_that_is_not_one_says_so(root: Path) -> None:
    (root / "notes.duckdb").write_text("just text, long enough to have a head", encoding="utf-8")

    with pytest.raises(ValueError, match="not a DuckDB database"):
        await _read(root, "notes.duckdb")
