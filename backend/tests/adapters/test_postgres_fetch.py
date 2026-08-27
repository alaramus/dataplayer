from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.adapters.fetch import FetchRequest, Filter, Sort
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.fetch import encode_cell
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.protocol import AdapterError
from app.adapters.relation import ColumnType
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run

CONNECTOR_TABLE = "public.connector"


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


@pytest.mark.parametrize(
    ("value", "column_type", "expected"),
    [
        (
            Decimal("9007199254740993.25"),
            ColumnType(sql="numeric", category="number"),
            "9007199254740993.25",
        ),
        (
            datetime(2026, 8, 27, 14, 30, tzinfo=UTC),
            ColumnType(sql="timestamp with time zone", category="datetime"),
            "2026-08-27T14:30:00+00:00",
        ),
        (True, ColumnType(sql="boolean", category="boolean"), "true"),
        (b"hello", ColumnType(sql="bytea", category="binary"), "0x68656C6C6F"),
        (None, ColumnType(sql="text", category="string"), None),
    ],
)
def test_cell_values_are_lossless_text(
    value: object, column_type: ColumnType, expected: str | None
) -> None:
    assert encode_cell(value, column_type) == expected


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


async def test_returns_columns_and_rows_as_arrays() -> None:
    result = await _adapter().fetch(FetchRequest(node_id=CONNECTOR_TABLE, limit=5))

    names = [column.name for column in result.columns]
    assert "adapter_type" in names
    assert all(isinstance(row, list) for row in result.rows)
    assert all(len(row) == len(result.columns) for row in result.rows)
    assert all(
        isinstance(cell, str)
        for row in result.rows
        for cell in row
        if cell is not None
    )


async def test_json_numeric_tokens_survive_a_database_fetch(schema: str) -> None:
    await run(f"CREATE TABLE {schema}.json_values (payload jsonb NOT NULL)")
    await run(
        f"INSERT INTO {schema}.json_values VALUES "  # noqa: S608 -- schema is fixture-owned.
        "('[9007199254740993.25,0.0000000000000000001]'::jsonb)"
    )

    result = await _adapter().fetch(
        FetchRequest(node_id=f"{schema}.json_values", limit=1)
    )

    assert result.rows == [["[9007199254740993.25,0.0000000000000000001]"]]


async def test_limit_bounds_the_page() -> None:
    result = await _adapter().fetch(FetchRequest(node_id=CONNECTOR_TABLE, limit=1))

    assert len(result.rows) <= 1


async def test_has_more_is_false_past_the_end() -> None:
    result = await _adapter().fetch(
        FetchRequest(node_id=CONNECTOR_TABLE, limit=100, offset=10_000)
    )

    assert result.rows == []
    assert result.has_more is False


async def test_offset_moves_the_window() -> None:
    adapter = _adapter()
    first = await adapter.fetch(
        FetchRequest(node_id=CONNECTOR_TABLE, limit=1, sort=[Sort(column="name")])
    )
    second = await adapter.fetch(
        FetchRequest(
            node_id=CONNECTOR_TABLE, limit=1, offset=1, sort=[Sort(column="name")]
        )
    )

    if first.rows and second.rows:
        assert first.rows[0] != second.rows[0]


async def test_sorting_descending_reverses_the_order() -> None:
    adapter = _adapter()
    ascending = await adapter.fetch(
        FetchRequest(node_id=CONNECTOR_TABLE, limit=50, sort=[Sort(column="name")])
    )
    descending = await adapter.fetch(
        FetchRequest(
            node_id=CONNECTOR_TABLE,
            limit=50,
            sort=[Sort(column="name", descending=True)],
        )
    )

    if len(ascending.rows) > 1:
        name_at = [c.name for c in ascending.columns].index("name")
        assert [row[name_at] for row in ascending.rows] == list(
            reversed([row[name_at] for row in descending.rows])
        )


async def test_equality_filter_narrows_the_result() -> None:
    result = await _adapter().fetch(
        FetchRequest(
            node_id=CONNECTOR_TABLE,
            filters=[Filter(column="adapter_type", op="eq", value="postgres")],
        )
    )

    type_at = [c.name for c in result.columns].index("adapter_type")
    assert all(row[type_at] == "postgres" for row in result.rows)


async def test_filter_that_matches_nothing_returns_an_empty_page() -> None:
    result = await _adapter().fetch(
        FetchRequest(
            node_id=CONNECTOR_TABLE,
            filters=[Filter(column="adapter_type", op="eq", value="no such type")],
        )
    )

    assert result.rows == []
    assert result.has_more is False


async def test_is_null_filter_uses_no_value() -> None:
    result = await _adapter().fetch(
        FetchRequest(
            node_id=CONNECTOR_TABLE,
            filters=[Filter(column="updated_at", op="is_null")],
        )
    )

    updated_at = [c.name for c in result.columns].index("updated_at")
    assert all(row[updated_at] is None for row in result.rows)


async def test_contains_filter_matches_a_substring() -> None:
    result = await _adapter().fetch(
        FetchRequest(
            node_id=CONNECTOR_TABLE,
            filters=[Filter(column="adapter_type", op="contains", value="ostgr")],
        )
    )

    type_at = [c.name for c in result.columns].index("adapter_type")
    assert all("ostgr" in row[type_at] for row in result.rows)


async def test_unknown_filter_column_is_rejected() -> None:
    with pytest.raises(ValueError, match="no_such_column"):
        await _adapter().fetch(
            FetchRequest(
                node_id=CONNECTOR_TABLE,
                filters=[Filter(column="no_such_column", op="eq", value=1)],
            )
        )


async def test_unknown_sort_column_is_rejected() -> None:
    with pytest.raises(ValueError, match="no_such_column"):
        await _adapter().fetch(
            FetchRequest(
                node_id=CONNECTOR_TABLE, sort=[Sort(column="no_such_column")]
            )
        )


async def test_injection_through_a_column_name_never_reaches_sql() -> None:
    """The failure the old application invited: identifiers taken from input.

    The name is rejected because it is not a column of the relation, before any
    statement is built.
    """
    with pytest.raises(ValueError):
        await _adapter().fetch(
            FetchRequest(
                node_id=CONNECTOR_TABLE,
                sort=[Sort(column='name"; DROP TABLE connector; --')],
            )
        )


async def test_unknown_relation_raises_adapter_error() -> None:
    with pytest.raises(AdapterError):
        await _adapter().fetch(FetchRequest(node_id="public.no_such_table"))


async def test_a_node_that_is_not_a_relation_is_rejected() -> None:
    """A schema has no rows: fetching one must fail rather than guess."""
    with pytest.raises((AdapterError, ValueError)):
        await _adapter().fetch(FetchRequest(node_id="public"))


# pg_class always holds hundreds of rows, so paging tests here are not vacuous
# the way they would be against a nearly empty application table.
CATALOG_TABLE = "pg_catalog.pg_class"


async def test_has_more_is_true_before_the_last_page() -> None:
    result = await _adapter().fetch(FetchRequest(node_id=CATALOG_TABLE, limit=5))

    assert len(result.rows) == 5
    assert result.has_more is True


async def test_offset_returns_different_rows() -> None:
    adapter = _adapter()
    sort = [Sort(column="oid")]
    first = await adapter.fetch(
        FetchRequest(node_id=CATALOG_TABLE, limit=3, sort=sort)
    )
    second = await adapter.fetch(
        FetchRequest(node_id=CATALOG_TABLE, limit=3, offset=3, sort=sort)
    )

    assert len(first.rows) == 3
    assert len(second.rows) == 3
    assert first.rows != second.rows


async def test_descending_sort_reverses_a_populated_page() -> None:
    adapter = _adapter()
    ascending = await adapter.fetch(
        FetchRequest(node_id=CATALOG_TABLE, limit=10, sort=[Sort(column="relname")])
    )
    descending = await adapter.fetch(
        FetchRequest(
            node_id=CATALOG_TABLE,
            limit=10,
            sort=[Sort(column="relname", descending=True)],
        )
    )

    name_at = [c.name for c in ascending.columns].index("relname")
    first_ascending = [row[name_at] for row in ascending.rows]
    first_descending = [row[name_at] for row in descending.rows]

    assert len(first_ascending) == 10
    assert first_ascending == sorted(first_ascending)
    assert first_descending == sorted(first_descending, reverse=True)
    assert first_ascending != first_descending


async def test_page_size_never_exceeds_the_limit() -> None:
    result = await _adapter().fetch(FetchRequest(node_id=CATALOG_TABLE, limit=7))

    assert len(result.rows) == 7
