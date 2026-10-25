"""Searching a ClickHouse catalog, and exporting every row (D202, D275)."""

import time
from collections.abc import AsyncIterator

import pytest

from app.adapters.clickhouse.reports import SECTION_ID
from app.adapters.clickhouse.session import quoted_name
from app.adapters.database_ids import database_id, relation_id
from app.adapters.export import ExportRequest
from app.adapters.fetch import ScalarFilter, Sort
from app.adapters.protocol import NodeNotFound
from app.adapters.search import NodeSearchRequest, SearchBounds
from tests.adapters.clickhouse_fixture import DATABASE, adapter, build, run, tear_down
from tests.utils.services import CLICKHOUSE

DB = quoted_name(DATABASE)


@pytest.fixture(scope="module")
async def server() -> AsyncIterator[None]:
    CLICKHOUSE.require()
    await build()
    await run(
        f"ALTER TABLE {DB}.journal MODIFY COMMENT 'the daily ledger'",
        f"ALTER TABLE {DB}.dupes COMMENT COLUMN b 'what 50% of people call it'",
    )
    yield
    await tear_down()


def _search(query: str, node_id: str | None = None) -> NodeSearchRequest:
    return NodeSearchRequest(query=query, node_id=node_id)


@pytest.mark.usefixtures("server")
async def test_names_are_found_best_first_with_wildcards_as_characters() -> None:
    source = adapter()

    found = await source.search_nodes(_search("item", database_id(DATABASE)))
    database = await source.search_nodes(_search("CLICKHOUSE"))
    literal = await source.search_nodes(_search("p0:String"))

    names = [match.node.name for match in found.matches]
    # Exact and prefix before a word inside the name (D202).
    assert names[:3] == ["item_ids", "item_labels", "items"] or names[0] == "items"
    assert all(match.parent_id == database_id(DATABASE) for match in found.matches)
    assert not any(name.startswith(".inner") for name in names)
    assert DATABASE in [match.node.name for match in database.matches]
    assert [match.node.name for match in literal.matches] == ["odd`{p0:String}\\name"]
    nothing = await source.search_nodes(_search("%", database_id(DATABASE)))
    assert nothing.matches == []


@pytest.mark.usefixtures("server")
async def test_relations_are_found_by_a_column_or_a_comment() -> None:
    source = adapter()

    by_column = await source.search_columns(_search("ratio", database_id(DATABASE)))
    by_column_comment = await source.search_columns(_search("50%", database_id(DATABASE)))
    by_comment = await source.search_columns(_search("ledger", database_id(DATABASE)))

    assert [(match.node.name, match.excerpt) for match in by_column.matches] == [("items", "ratio")]
    assert [match.node.name for match in by_column_comment.matches] == ["dupes"]
    assert by_column_comment.matches[0].excerpt == "b: what 50% of people call it"
    assert [(match.node.name, match.excerpt) for match in by_comment.matches] == [
        ("journal", "the daily ledger")
    ]


@pytest.mark.usefixtures("server")
async def test_reports_are_found_by_their_title_and_a_leaf_is_no_scope() -> None:
    source = adapter()

    found = await source.search_nodes(_search("merge", SECTION_ID))

    assert [match.node.name for match in found.matches] == ["Merges"]
    with pytest.raises(ValueError):
        await source.search_nodes(_search("x", relation_id(DATABASE, "items")))
    with pytest.raises(NodeNotFound):
        await source.search_nodes(_search("x", database_id("dp_no_such_database")))


@pytest.mark.usefixtures("server")
async def test_every_name_is_listed_for_a_kept_index() -> None:
    bounds = SearchBounds(deadline=time.monotonic() + 30)
    names = [
        kept.node.name
        async for batch in adapter().enumerate_names(10_000, bounds)
        for kept in batch.names
    ]

    assert DATABASE in names and "items" in names and "system" in names


@pytest.mark.usefixtures("server")
async def test_every_matching_row_is_exported_in_order() -> None:
    batches = [
        batch
        async for batch in adapter().export_rows(
            ExportRequest(
                node_id=relation_id(DATABASE, "items"),
                columns=["id", "amount", "tags"],
                filters=[ScalarFilter(column="id", op="gte", value="2")],
                sort=[Sort(column="id", descending=True)],
            )
        )
    ]

    rows = [row for batch in batches for row in batch.rows]
    assert rows == [["3", "1.0000000000", "[]"], ["2", "0.0000000000", "[]"]]
