import uuid
from collections.abc import AsyncGenerator

import psycopg
import pytest
from psycopg import sql

from app.adapters.catalog import SchemaNode
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from tests.utils.database import working_postgres_options


@pytest.fixture
async def framework_schemas() -> AsyncGenerator[tuple[str, str]]:
    """Real tables in one schema and identically named views in another."""
    options = working_postgres_options()
    conninfo = psycopg.conninfo.make_conninfo(
        host=options["host"],
        port=options["port"],
        dbname=options["database"],
        user=options["user"],
        password=options["password"],
    )
    tables = f"framework_tables_{uuid.uuid4().hex}"
    views = f"framework_views_{uuid.uuid4().hex}"
    async with await psycopg.AsyncConnection.connect(conninfo, autocommit=True) as conn:
        try:
            for schema in (tables, views):
                await conn.execute(
                    sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
                )
            # A partitioned table is a table too, even before it holds any rows.
            await conn.execute(
                sql.SQL("CREATE TABLE {} (id integer) PARTITION BY RANGE (id)").format(
                    sql.Identifier(tables, "django_content_type")
                )
            )
            for marker in ("alembic_version", "DATABASECHANGELOG", "wp_options"):
                await conn.execute(
                    sql.SQL("CREATE TABLE {} (id integer)").format(
                        sql.Identifier(tables, marker)
                    )
                )
            for marker in (
                "django_content_type", "alembic_version", "databasechangelog", "wp_options"
            ):
                await conn.execute(
                    sql.SQL("CREATE VIEW {} AS SELECT 1 AS id").format(
                        sql.Identifier(views, marker)
                    )
                )
            yield tables, views
        finally:
            for schema in (tables, views):
                await conn.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema)
                    )
                )


async def test_framework_metadata_is_scoped_to_tables_in_each_schema(
    framework_schemas: tuple[str, str],
) -> None:
    tables, views = framework_schemas
    adapter = PostgresAdapter(PostgresUserPassword(**working_postgres_options()))
    schemas = {
        node.id: node
        for node in await adapter.list_children(None)
        if isinstance(node, SchemaNode)
    }
    assert [item.id for item in schemas[tables].frameworks] == [
        "django", "alembic", "liquibase", "wordpress"
    ]
    assert schemas[views].frameworks == []
    assert schemas["pg_catalog"].frameworks == []
    assert schemas["information_schema"].frameworks == []
    assert "pg_toast" not in schemas

    # Not listed at the root does not mean an explicit reference is missing.
    system_path = await adapter.path_to("pg_toast")
    assert isinstance(system_path[0], SchemaNode)
    assert system_path[0].frameworks == []

    # Following a relation back to its schema must carry the same hints.
    path = await adapter.path_to(f"{tables}.django_content_type")
    assert path[0] == schemas[tables]
    view_path = await adapter.path_to(f"{views}.django_content_type")
    assert view_path[0] == schemas[views]
