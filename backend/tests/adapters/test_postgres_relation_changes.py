from collections.abc import AsyncGenerator

import pytest

from app.adapters.fetch import FetchRequest
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.protocol import NodeNotFound
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)
from app.adapters.update import ValuesRejected
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema

DEFAULT_COLUMNS = [
    NewColumn(name="sku", type_code="text"),
    NewColumn(name="amount", type_code="integer"),
]


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


def _request(
    schema: str,
    *,
    parent_node_id: str | None = None,
    name: str = "prices",
    columns: list[NewColumn] | None = None,
    rows: list[list[str | None]] | None = None,
) -> CreateRelationRequest:
    return CreateRelationRequest(
        parent_node_id=schema if parent_node_id is None else parent_node_id,
        name=name,
        columns=DEFAULT_COLUMNS if columns is None else columns,
        rows=[["a-1", "10"], ["a-2", "20"]] if rows is None else rows,
    )


async def _exists(schema: str, name: str) -> bool:
    nodes = await _adapter().list_children(schema)
    return any(node.name == name for node in nodes)


async def test_creates_a_relation_with_its_rows_and_describes_it(schema: str) -> None:
    result = await _adapter().create_relation(_request(schema))

    assert isinstance(result, RelationCreated)
    assert result.inserted == 2
    # The catalog's own description of the new node, so nothing outside the
    # source composes an id or decides what kind of node this is.
    assert result.node.id == f"{schema}.prices"
    assert result.node.name == "prices"
    assert result.node.kind == "table"

    page = await _adapter().fetch(FetchRequest(node_id=f"{schema}.prices", limit=10))
    assert [column.name for column in page.columns] == ["sku", "amount"]
    assert sorted(str(row[0]) for row in page.rows) == ["a-1", "a-2"]


async def test_the_chosen_types_are_the_ones_the_relation_gets(schema: str) -> None:
    await _adapter().create_relation(_request(schema))

    model = await _adapter().relation_model(f"{schema}.prices")

    assert [(column.name, column.type.sql) for column in model.columns] == [
        ("sku", "text"),
        ("amount", "integer"),
    ]


async def test_a_value_the_chosen_type_cannot_read_leaves_no_relation(
    schema: str,
) -> None:
    result = await _adapter().create_relation(
        _request(schema, rows=[["a-1", "10"], ["a-2", "nope"]])
    )

    assert isinstance(result, ValuesRejected)
    assert [(cell.row, cell.column, cell.value) for cell in result.cells] == [
        (1, "amount", "nope")
    ]
    # Nothing at all, rather than a table left waiting to be filled: this is
    # the whole reason the DDL and the rows are one request.
    assert await _exists(schema, "prices") is False


async def test_a_relation_with_no_rows_is_a_request_worth_making(schema: str) -> None:
    result = await _adapter().create_relation(_request(schema, rows=[]))

    assert isinstance(result, RelationCreated)
    assert result.inserted == 0
    assert await _exists(schema, "prices") is True


async def test_a_taken_name_is_refused_without_the_driver_saying_so(
    schema: str,
) -> None:
    with pytest.raises(ValueError) as refusal:
        await _adapter().create_relation(_request(schema, name="customers"))

    assert "already there" in str(refusal.value)


async def test_an_unknown_type_code_is_refused_before_anything_is_built(
    schema: str,
) -> None:
    with pytest.raises(ValueError) as refusal:
        await _adapter().create_relation(
            _request(
                schema, columns=[NewColumn(name="sku", type_code="money")], rows=[]
            )
        )

    assert "money" in str(refusal.value)
    assert await _exists(schema, "prices") is False


async def test_an_identifier_longer_than_the_source_keeps_is_refused(
    schema: str,
) -> None:
    # 63 characters of two bytes each: inside the field's own length and over
    # what PostgreSQL stores, which it truncates with a notice rather than
    # refusing — so the column would end up under a name nobody chose.
    with pytest.raises(ValueError) as refusal:
        await _adapter().create_relation(
            _request(
                schema,
                columns=[NewColumn(name="я" * 63, type_code="text")],
                rows=[],
            )
        )

    assert "63 bytes" in str(refusal.value)


async def test_a_schema_offers_its_type_vocabulary(schema: str) -> None:
    options = await _adapter().new_relation_options(schema)

    assert options.supported is True
    assert {option.code for option in options.column_type_options} >= {
        "text",
        "integer",
        "numeric",
        "boolean",
        "date",
    }


async def test_a_system_schema_says_why_it_admits_nothing() -> None:
    options = await _adapter().new_relation_options("pg_catalog")

    assert options.supported is False
    assert options.reason is not None
    assert "pg_catalog" in options.reason


async def test_a_relation_is_not_a_container(schema: str) -> None:
    options = await _adapter().new_relation_options(f"{schema}.customers")

    assert options.supported is False
    assert options.reason == "A table is created in a schema"

    with pytest.raises(ValueError):
        await _adapter().create_relation(
            _request(schema, parent_node_id=f"{schema}.customers")
        )


async def test_a_schema_that_is_gone_is_not_found() -> None:
    with pytest.raises(NodeNotFound):
        await _adapter().new_relation_options("no_such_schema_here")


async def test_a_column_named_like_a_statement_is_quoted_not_composed(
    schema: str,
) -> None:
    result = await _adapter().create_relation(
        _request(
            schema,
            columns=[NewColumn(name='a"); drop table x; --', type_code="text")],
            rows=[["1"]],
        )
    )

    assert isinstance(result, RelationCreated)
    model = await _adapter().relation_model(f"{schema}.prices")
    assert [column.name for column in model.columns] == ['a"); drop table x; --']
