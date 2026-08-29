from collections.abc import AsyncGenerator

import pytest

from app.adapters.actions import ActionRefused, TakesParams
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


async def test_rename_is_offered_only_for_non_system_relations(schema: str) -> None:
    source = adapter()

    table = await source.available(f"{schema}.customers")
    view = await source.available(f"{schema}.rich_customers")
    system = await source.available("pg_catalog.pg_class")

    assert [action.name for action in table] == ["rename_relation"]
    assert [action.name for action in view] == ["rename_relation"]
    assert system == []


async def test_renames_a_view_with_a_source_issued_replacement(schema: str) -> None:
    source = adapter()
    action = source.action("rename_relation")
    assert isinstance(action, TakesParams)

    result = await action.perform(
        f"{schema}.rich_customers", {"new_name": "valuable_customers"}
    )

    assert result.reload_node_id == schema
    assert result.replacement is not None
    assert result.replacement.old_node_id == f"{schema}.rich_customers"
    assert result.replacement.new_node_id == f"{schema}.valuable_customers"
    path = await source.path_to(result.replacement.new_node_id)
    assert path[-1].name == "valuable_customers"


async def test_renames_a_materialized_view(schema: str) -> None:
    await run(
        f"CREATE MATERIALIZED VIEW {schema}.customer_snapshot "  # noqa: S608 -- fixture-owned schema.
        f"AS SELECT id, name FROM {schema}.customers"  # noqa: S608 -- fixture-owned schema.
    )
    source = adapter()
    action = source.action("rename_relation")
    assert isinstance(action, TakesParams)

    result = await action.perform(
        f"{schema}.customer_snapshot", {"new_name": "renamed_snapshot"}
    )

    assert result.replacement is not None
    path = await source.path_to(result.replacement.new_node_id)
    assert path[-1].name == "renamed_snapshot"


async def test_refuses_a_relation_name_that_is_already_taken(schema: str) -> None:
    source = adapter()
    action = source.action("rename_relation")
    assert isinstance(action, TakesParams)

    with pytest.raises(ActionRefused, match="already has"):
        await action.perform(f"{schema}.customers", {"new_name": "regions"})


async def test_rejects_a_name_postgres_would_truncate(schema: str) -> None:
    source = adapter()
    action = source.action("rename_relation")
    assert isinstance(action, TakesParams)

    with pytest.raises(ValueError, match="63 bytes"):
        await action.perform(f"{schema}.customers", {"new_name": "x" * 64})
