from unittest.mock import AsyncMock

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.catalog import ReportNode, SchemaNode, TableNode, ViewNode
from app.adapters.postgres.timescale import targets

ROW = {
    "database_oid": "42", "relation_oid": "123", "schema_name": "lab", "table_name": "events",
    "column_name": "time", "column_type": "timestamp with time zone",
}
AGGREGATE_ROW = {
    "database_oid": "42", "view_oid": "321", "view_schema": "lab", "view_name": "hourly",
    "materialization_oid": "654", "materialization_schema": "_timescaledb_internal",
    "materialization_name": "_materialized_hypertable_3", "source_schema": "lab",
    "source_name": "events", "column_type": "timestamp with time zone",
}
SCHEMA = SchemaNode(id="schema-id", name="lab", has_children=True, representations=[])


@pytest.fixture
def views(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    checked = AsyncMock()
    monkeypatch.setattr(targets, "require_public_view", checked)
    return checked


async def test_time_hypertable_binds_names_after_checking_public_views(views: AsyncMock) -> None:
    reader = AsyncMock()
    reader.query.return_value = [ROW]
    schema, table = 'odd"schema', "events'; DROP TABLE x; --"
    result = await targets.time_hypertable(reader, schema, table)
    assert result.relation_oid == "123"
    statement, params = reader.query.await_args.args
    assert params == (schema, table)
    assert schema not in statement and table not in statement
    assert reader.query.await_args.kwargs == {"inspection": True}
    assert {call.args[1] for call in views.await_args_list} == {
        "hypertables", "dimensions", "continuous_aggregates",
    }


@pytest.mark.parametrize("rows,message", [
    ([], "owned hypertable"), ([ROW, ROW], "owned hypertable"),
    ([{**ROW, "column_type": "bigint"}], "timestamp and date"),
])
@pytest.mark.usefixtures("views")
async def test_ineligible_hypertable_refuses(rows: list[dict[str, object]], message: str) -> None:
    reader = AsyncMock()
    reader.query.return_value = rows
    with pytest.raises(ActionRefused, match=message):
        await targets.time_hypertable(reader, "lab", "events")


def test_statements_exclude_foreign_owners_and_misread_identities() -> None:
    assert "continuous_aggregates" in targets._TIME_HYPERTABLE
    assert "pg_has_role(relation.relowner, 'USAGE')" in targets._TIME_HYPERTABLE
    assert "num_dimensions = 1" in targets._TIME_HYPERTABLE
    assert "pg_has_role(aggregate_view.relowner, 'USAGE')" in targets._CONTINUOUS_AGGREGATE
    assert "pg_has_role(materialization.relowner, 'USAGE')" in targets._CONTINUOUS_AGGREGATE
    assert "aggregate_view.relkind = 'v'" in targets._CONTINUOUS_AGGREGATE


async def test_continuous_aggregate_binds_names_after_checking_public_views(views: AsyncMock) -> None:
    reader = AsyncMock()
    reader.query.return_value = [AGGREGATE_ROW]
    schema, view = 'odd"schema', "hourly'; DROP VIEW x; --"
    result = await targets.continuous_aggregate(reader, schema, view)
    assert (result.view_oid, result.materialization_name) == ("321", "_materialized_hypertable_3")
    statement, params = reader.query.await_args.args
    assert params == (schema, view)
    assert schema not in statement and view not in statement
    assert {call.args[1] for call in views.await_args_list} == {"continuous_aggregates", "dimensions"}


@pytest.mark.parametrize("rows,message", [
    ([], "owned continuous aggregate"), ([AGGREGATE_ROW, AGGREGATE_ROW], "owned continuous aggregate"),
    ([{**AGGREGATE_ROW, "column_type": "integer"}], "timestamp and date"),
])
@pytest.mark.usefixtures("views")
async def test_ineligible_aggregate_refuses(rows: list[dict[str, object]], message: str) -> None:
    reader = AsyncMock()
    reader.query.return_value = rows
    with pytest.raises(ActionRefused, match=message):
        await targets.continuous_aggregate(reader, "lab", "hourly")


async def test_catalog_identities_are_the_sources_own() -> None:
    catalog = AsyncMock()
    table = TableNode(id="node-id", name="events", has_children=False, representations=[])
    view = ViewNode(id="view-id", name="hourly", has_children=False, representations=[])
    catalog.path_to.return_value = [SCHEMA, table]
    assert await targets.user_table(catalog, "opaque") == (SCHEMA, table)
    catalog.path_to.return_value = [SCHEMA, view]
    assert await targets.user_view(catalog, "opaque") == (SCHEMA, view)
    with pytest.raises(ActionRefused, match="user hypertable"):
        await targets.user_table(catalog, "opaque")
    catalog.path_to.return_value = [SCHEMA, table]
    with pytest.raises(ActionRefused, match="user continuous aggregate"):
        await targets.user_view(catalog, "opaque")


@pytest.mark.parametrize("node_id,path", [
    (None, []),
    ("schema-id", [SCHEMA]),
    ("report-id", [ReportNode(id="report-id", name="Chunks", has_children=False, representations=[])]),
    ("node-id", [
        SCHEMA,
        TableNode(id="node-id", name="internal", is_system=True, has_children=False, representations=[]),
    ]),
    ("node-id", [
        SchemaNode(id="schema-id", name="_timescaledb_internal", is_system=True, has_children=True,
                   representations=[]),
        TableNode(id="node-id", name="chunk", has_children=False, representations=[]),
    ]),
])
async def test_user_table_refuses_everything_else(node_id: str | None, path: list[object]) -> None:
    catalog = AsyncMock()
    catalog.path_to.return_value = path
    with pytest.raises(ActionRefused, match="user hypertable"):
        await targets.user_table(catalog, node_id)
