from collections.abc import AsyncGenerator

import psycopg
import pytest

from app.adapters.catalog import ColumnNode, SchemaNode, TableNode, ViewNode
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresOptions
from app.adapters.protocol import AdapterError
from tests.utils.database import working_postgres_options

VIEW_NAME = "catalog_test_view"


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresOptions(**working_postgres_options()))


@pytest.fixture
async def temporary_view() -> AsyncGenerator[str]:
    """A view in the public schema, so the view branch is covered for real."""
    options = working_postgres_options()
    conninfo = psycopg.conninfo.make_conninfo(
        host=options["host"],
        port=options["port"],
        dbname=options["database"],
        user=options["user"],
        password=options["password"],
    )
    async with await psycopg.AsyncConnection.connect(conninfo, autocommit=True) as conn:
        await conn.execute(f"CREATE OR REPLACE VIEW {VIEW_NAME} AS SELECT 1 AS one")
    try:
        yield VIEW_NAME
    finally:
        async with await psycopg.AsyncConnection.connect(
            conninfo, autocommit=True
        ) as conn:
            await conn.execute(f"DROP VIEW IF EXISTS {VIEW_NAME}")


async def test_root_lists_schemas_including_public() -> None:
    nodes = await _adapter().list_children(None)

    assert all(isinstance(node, SchemaNode) for node in nodes)
    names = [node.name for node in nodes]
    assert "public" in names


async def test_system_schemas_are_marked_but_not_hidden() -> None:
    nodes = await _adapter().list_children(None)

    by_name = {node.name: node for node in nodes}
    assert isinstance(by_name["information_schema"], SchemaNode)
    assert by_name["information_schema"].is_system is True
    assert by_name["public"].is_system is False


async def test_schema_lists_its_tables() -> None:
    nodes = await _adapter().list_children("public")

    tables = {node.name: node for node in nodes if isinstance(node, TableNode)}
    assert "connector" in tables
    assert tables["connector"].has_children is True
    assert tables["connector"].size_bytes is not None


async def test_schema_lists_views_separately_from_tables(temporary_view: str) -> None:
    nodes = await _adapter().list_children("public")

    views = {node.name: node for node in nodes if isinstance(node, ViewNode)}
    assert temporary_view in views
    assert views[temporary_view].is_materialized is False


async def test_table_lists_its_columns() -> None:
    nodes = await _adapter().list_children("public.connector")

    columns = {node.name: node for node in nodes if isinstance(node, ColumnNode)}
    assert "adapter_type" in columns
    assert columns["adapter_type"].data_type
    assert columns["adapter_type"].has_children is False
    assert columns["id"].primary_key is True


async def test_nullable_columns_are_reported() -> None:
    nodes = await _adapter().list_children("public.connector")

    columns = {node.name: node for node in nodes if isinstance(node, ColumnNode)}
    assert columns["adapter_type"].nullable is False
    assert columns["updated_at"].nullable is True


async def test_unknown_schema_raises_instead_of_returning_empty() -> None:
    with pytest.raises(AdapterError) as caught:
        await _adapter().list_children("no_such_schema")

    assert caught.value.error_kind == "config"


async def test_unknown_table_raises_instead_of_returning_empty() -> None:
    with pytest.raises(AdapterError) as caught:
        await _adapter().list_children("public.no_such_table")

    assert caught.value.error_kind == "config"


async def test_unreachable_server_raises_with_a_safe_message() -> None:
    options = PostgresOptions(**working_postgres_options()).model_copy(
        update={"host": "127.0.0.1", "port": 1}
    )

    with pytest.raises(AdapterError) as caught:
        await PostgresAdapter(options).list_children(None)

    assert caught.value.error_kind == "timeout"
    assert options.password.get_secret_value() not in caught.value.message
