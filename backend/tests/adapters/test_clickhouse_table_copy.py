"""ClickHouse tables copied with their structure, between connections (D182, D277).

The fixture's `items` holds a value of nearly every kind ClickHouse has, a
computed column, a check and a skipping index: what arrives must read back
exactly as the original does.
"""

from collections.abc import AsyncIterator

import pytest

from app.adapters.clickhouse.adapter import ClickhouseAdapter
from app.adapters.clickhouse.session import quoted_name
from app.adapters.database_ids import database_id, relation_id
from app.adapters.fetch import FetchRequest, Sort
from app.adapters.protocol import AdapterError, SupportsTableCopy
from app.adapters.table_copy import CopyLoad, TableCopyRequest, TableCopyTarget
from tests.adapters.clickhouse_fixture import DATABASE, adapter, build, run, tear_down
from tests.utils.services import CLICKHOUSE

COPIES = "dp_copies"
ITEMS = relation_id(DATABASE, "items")
DUPES = relation_id(DATABASE, "dupes")


@pytest.fixture
async def server() -> AsyncIterator[None]:
    CLICKHOUSE.require()
    await build()
    await run(f"DROP DATABASE IF EXISTS {COPIES}", f"CREATE DATABASE {COPIES}")
    yield
    await run(f"DROP DATABASE IF EXISTS {COPIES}")
    await tear_down()


async def _request(source: ClickhouseAdapter, place: str, names: dict[str, str]) -> TableCopyRequest:
    described = await source.describe_for_copy(list(names))
    return TableCopyRequest(
        dialect="clickhouse",
        place_node_id=database_id(place),
        same_database=False,
        tables=[TableCopyTarget(table=table, name=names[table.node_id]) for table in described],
    )


async def _carry(
    source: ClickhouseAdapter, destination: ClickhouseAdapter, request: TableCopyRequest
) -> dict[str, int]:
    counted: dict[str, int] = {}

    async def arrived(load: CopyLoad, rows: int, _size: int) -> None:
        counted[load.name] = rows

    async with source.reading_tables() as tables:
        await destination.carry_table_copy(
            request, lambda load: tables.rows(load.node_id, load.columns), arrived
        )
    return counted


async def _rows(source: ClickhouseAdapter, node_id: str) -> list[list[str | None]]:
    page = await source.fetch(FetchRequest(node_id=node_id, limit=50, sort=[Sort(column="id")]))
    return page.rows


@pytest.mark.usefixtures("server")
async def test_a_table_is_described_from_its_catalog() -> None:
    source = adapter()
    assert isinstance(source, SupportsTableCopy)

    [items] = await source.describe_for_copy([ITEMS])

    by_name = {column.name: column for column in items.columns}
    assert by_name["label"].definition == "LowCardinality(String) DEFAULT 'it\\'s'"
    assert by_name["doubled"].generated is not None
    assert by_name["doubled"].definition is not None
    assert by_name["doubled"].definition.startswith("Nullable(Int64) MATERIALIZED ")
    assert [constraint.definition for constraint in items.constraints] == ["CHECK amount >= 0"]
    assert [index.body for index in items.indexes] == [
        "INDEX `items_label` label TYPE bloom_filter GRANULARITY 4"
    ]
    assert items.options is not None and items.options.startswith("MergeTree PARTITION BY")
    # The materialized view reading it stays where it is, and is said to.
    assert items.left_behind == [f"materialized view {DATABASE}.item_ids"]


@pytest.mark.usefixtures("server")
async def test_what_is_not_a_table_of_its_own_is_refused_with_a_reason() -> None:
    source = adapter()

    view, system, items = await source.describe_for_copy(
        [relation_id(DATABASE, "item_labels"), relation_id("system", "one"), ITEMS]
    )

    assert view.refusal == "only tables are copied with their structure"
    assert system.refusal is not None
    assert items.refusal is None


@pytest.mark.usefixtures("server")
async def test_tables_arrive_in_another_database_exactly_as_they_were() -> None:
    source = adapter()
    request = await _request(source, COPIES, {ITEMS: "items", DUPES: "dupes"})

    plan = await source.plan_table_copy(request)
    counted = await _carry(source, source, request)

    assert plan.problems == []
    assert plan.statements[0].sql.startswith(f"CREATE TABLE {quoted_name(COPIES)}.`items` (")
    assert "ENGINE = MergeTree PARTITION BY toYYYYMM(day)" in plan.statements[0].sql
    assert counted == {"items": 3, "dupes": 4}
    assert await _rows(source, relation_id(COPIES, "items")) == await _rows(source, ITEMS)
    model = await source.relation_model(relation_id(COPIES, "items"))
    assert [constraint.name for constraint in model.constraints] == ["items_amount"]
    assert {index.name for index in model.indexes} == {"PRIMARY KEY", "items_label"}


@pytest.mark.usefixtures("server")
async def test_a_name_taken_is_numbered_and_a_failure_leaves_nothing() -> None:
    source = adapter()
    names = await source.free_table_names(database_id(DATABASE), ["items", "items"])
    assert names == ["items_copy", "items_copy_2"]

    request = await _request(source, COPIES, {ITEMS: "items"})

    async def broken(_load: CopyLoad) -> AsyncIterator[bytes]:
        yield b"not\tthe\trows\n"

    async def arrived(_load: CopyLoad, _rows: int, _size: int) -> None:
        return None

    with pytest.raises((ValueError, AdapterError)):
        await source.carry_table_copy(request, broken, arrived)

    assert "items" not in {node.name for node in await source.list_children(database_id(COPIES))}


@pytest.mark.usefixtures("server")
async def test_a_read_that_fails_halfway_hands_on_no_rows() -> None:
    """An exception in the middle of an answer is not taken for rows."""
    source = adapter()
    chunks: list[bytes] = []

    with pytest.raises(AdapterError):
        async for chunk in source._session.stream_bytes(
            "SELECT number, throwIf(number = 3, 'boom') FROM numbers(10) "
            "SETTINGS max_block_size = 1, max_threads = 1 FORMAT TabSeparated",
            {},
            {"http_response_buffer_size": "1"},
        ):
            chunks.append(chunk)

    assert b"__exception__" not in b"".join(chunks)


def test_a_fragment_is_read_with_clickhouse_s_quoting() -> None:
    from app.adapters.clickhouse.table_copy import stands_alone

    assert stands_alone("String DEFAULT 'it\\'s; not -- a comment'")
    assert stands_alone("`a``b` + `c\\`d`")
    assert not stands_alone("String DEFAULT 'x'; DROP TABLE t")
    assert not stands_alone("String DEFAULT 'open")
    assert not stands_alone("String -- trailing")
    assert not stands_alone("(1")
