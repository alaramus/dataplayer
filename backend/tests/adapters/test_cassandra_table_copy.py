"""Tables copied with their structure between Cassandra connections (D354)."""

from collections.abc import AsyncIterator

import pytest

from app.adapters.cassandra.adapter import CassandraAdapter
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import SupportsTableCopy
from app.adapters.table_copy import CopyLoad, TableCopyRequest, TableCopyTarget
from tests.adapters.cassandra_fixture import (
    KEYSPACE,
    TARGETS,
    Target,
    build,
    run,
    tear_down,
)

TARGET = "dp_test_cql_copy"


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    tablets = " AND tablets = {'enabled': false}" if chosen.scylla else ""
    await run(chosen, f"DROP KEYSPACE IF EXISTS {TARGET}")
    await run(
        chosen,
        f"CREATE KEYSPACE {TARGET} WITH replication = "
        "{'class': 'NetworkTopologyStrategy', 'datacenter1': 1}" + tablets,
    )
    await run(chosen, f"CREATE TABLE {KEYSPACE}.tally (k text PRIMARY KEY, n counter)")
    yield chosen
    await run(chosen, f"DROP KEYSPACE IF EXISTS {TARGET}")
    await tear_down(chosen)


async def _copy(
    adapter: CassandraAdapter, node_ids: list[str], names: list[str]
) -> TableCopyRequest:
    tables = await adapter.describe_for_copy(node_ids)
    return TableCopyRequest(
        dialect=adapter.table_copy_dialect,
        place_node_id=TARGET,
        same_database=True,
        tables=[
            TableCopyTarget(table=table, name=name)
            for table, name in zip(tables, names, strict=True)
        ],
    )


async def test_a_table_is_copied_with_its_types_key_index_and_rows(
    target: Target,
) -> None:
    adapter = target.adapter()
    assert isinstance(adapter, SupportsTableCopy)
    request = await _copy(adapter, [f"{KEYSPACE}.items"], ["items"])

    plan = await adapter.plan_table_copy(request)
    seen: list[tuple[str, int]] = []

    async def arrived(load: CopyLoad, rows: int, _size: int) -> None:
        seen.append((load.name, rows))

    async with adapter.reading_tables() as source:
        await adapter.carry_table_copy(
            request, lambda load: source.rows(load.node_id, load.columns), arrived
        )
    original = await adapter.fetch(FetchRequest(node_id=f"{KEYSPACE}.items", limit=100))
    copied = await adapter.fetch(FetchRequest(node_id=f"{TARGET}.items", limit=100))
    model = await adapter.relation_model(f"{TARGET}.items")

    assert plan.problems == []
    assert [statement.stage for statement in plan.statements] == [
        "before",
        "before",
        "after",
    ]
    assert plan.statements[0].sql.startswith('CREATE TYPE "dp_test_cql_copy"."address"')
    assert "CLUSTERING ORDER BY" in plan.statements[1].sql
    assert sorted(copied.rows) == sorted(original.rows)
    assert seen[-1] == ("items", 3)
    assert [column.name for column in model.columns[:3]] == ["shop", "id", "at"]
    assert len(model.indexes) == 1


async def test_a_name_that_is_taken_is_offered_free_and_refused_as_it_is(
    target: Target,
) -> None:
    adapter = target.adapter()
    await run(target, f"CREATE TABLE IF NOT EXISTS {TARGET}.many (p int PRIMARY KEY)")

    free = await adapter.free_table_names(TARGET, ["many", "fresh"])
    plan = await adapter.plan_table_copy(
        await _copy(adapter, [f"{KEYSPACE}.many"], ["many"])
    )

    assert free == ["many_copy", "fresh"]
    assert plan.problems[0].kind == "conflict"


async def test_a_view_and_a_counter_table_are_not_copied(target: Target) -> None:
    adapter = target.adapter()

    described = await adapter.describe_for_copy(
        [f"{KEYSPACE}.items_by_ok", f"{KEYSPACE}.tally", "system.local"]
    )

    assert all(table.refusal for table in described)


async def test_a_view_over_a_copied_table_is_named_as_left_behind(
    target: Target,
) -> None:
    [items] = await target.adapter().describe_for_copy([f"{KEYSPACE}.items"])

    assert any("items_by_ok" in line for line in items.left_behind)


async def test_another_dialect_is_refused(target: Target) -> None:
    adapter = target.adapter()
    request = await _copy(adapter, [f"{KEYSPACE}.many"], ["other"])

    plan = await adapter.plan_table_copy(
        request.model_copy(update={"dialect": "clickhouse"})
    )

    assert plan.problems
