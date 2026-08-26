from collections.abc import AsyncGenerator

import psycopg
import pytest

from app.adapters.catalog import SchemaNode, TableNode, ViewNode
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.protocol import AdapterError, NodeNotFound
from tests.utils.database import working_postgres_options
from tests.utils.network import silent_endpoint

VIEW_NAME = "catalog_test_view"


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


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
    assert tables["connector"].has_children is False
    assert tables["connector"].size_bytes is not None


async def test_schema_lists_views_separately_from_tables(temporary_view: str) -> None:
    nodes = await _adapter().list_children("public")

    views = {node.name: node for node in nodes if isinstance(node, ViewNode)}
    assert temporary_view in views
    assert views[temporary_view].is_materialized is False


async def test_a_table_is_a_leaf_now_that_its_columns_come_from_the_model() -> None:
    nodes = await _adapter().list_children("public")

    table = next(node for node in nodes if isinstance(node, TableNode))
    assert table.has_children is False


async def test_unknown_schema_raises_instead_of_returning_empty() -> None:
    with pytest.raises(AdapterError) as caught:
        await _adapter().list_children("no_such_schema")

    assert caught.value.error_kind == "config"


async def test_unknown_table_raises_instead_of_returning_empty() -> None:
    with pytest.raises(AdapterError) as caught:
        await _adapter().list_children("public.no_such_table")

    assert caught.value.error_kind == "config"


async def test_unreachable_server_raises_with_a_safe_message() -> None:
    with silent_endpoint() as port:
        options = PostgresUserPassword(**working_postgres_options()).model_copy(
            update={"host": "127.0.0.1", "port": port}
        )

        with pytest.raises(AdapterError) as caught:
            await PostgresAdapter(options).list_children(None)

    assert caught.value.error_kind == "timeout"
    assert options.password.get_secret_value() not in caught.value.message


async def test_path_to_a_table_names_its_schema_and_then_the_table() -> None:
    path = await _adapter().path_to("public.connector")

    assert [node.name for node in path] == ["public", "connector"]
    assert isinstance(path[0], SchemaNode)
    assert isinstance(path[1], TableNode)
    assert path[0].id == "public"
    assert path[1].id == "public.connector"


async def test_path_to_a_table_carries_what_the_listing_would_carry() -> None:
    """The last node answers "what is this", so it must not be a stub."""
    path = await _adapter().path_to("public.connector")

    table = path[-1]
    assert isinstance(table, TableNode)
    assert table.has_children is False
    assert table.size_bytes is not None


async def test_path_to_a_view_ends_with_a_view(temporary_view: str) -> None:
    path = await _adapter().path_to(f"public.{temporary_view}")

    assert isinstance(path[-1], ViewNode)
    assert path[-1].name == temporary_view


async def test_path_to_a_schema_is_the_schema_alone() -> None:
    path = await _adapter().path_to("public")

    assert [node.name for node in path] == ["public"]
    assert isinstance(path[0], SchemaNode)


async def test_path_to_an_unknown_schema_is_not_found() -> None:
    with pytest.raises(NodeNotFound):
        await _adapter().path_to("no_such_schema")


async def test_path_to_an_unknown_table_is_not_found() -> None:
    with pytest.raises(NodeNotFound):
        await _adapter().path_to("public.no_such_table")
