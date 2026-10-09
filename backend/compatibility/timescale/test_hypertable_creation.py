"""A table created as a hypertable from the table designer (D207, H4)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from psycopg import sql

from app.adapters.actions import JsonAction
from app.adapters.hypertable_design import DesignDuration
from app.adapters.table_design import (
    DesignColumn,
    DesignColumnType,
    DesignIndex,
    DesignPartition,
    DesignPrimaryKey,
    DesignUnique,
    IndexColumnKey,
    TableDefinition,
    TableHashDimension,
    TableHypertable,
    TablePlan,
    TablePlanRequest,
)
from compatibility.timescale.policy_tables import PolicyTable, jobs
from compatibility.timescale.source import TimescaleSource

_DIMENSIONS = """
    SELECT column_name, dimension_type, num_partitions FROM timescaledb_information.dimensions
    WHERE hypertable_schema = %s AND hypertable_name = %s ORDER BY dimension_number
"""
_INDEXES = """
    SELECT indexname FROM pg_catalog.pg_indexes WHERE schemaname = %s AND tablename = %s ORDER BY 1
"""


@pytest.fixture
async def schema(source: TimescaleSource) -> AsyncIterator[str]:
    name = f"create_{uuid.uuid4().hex[:12]}"
    session = source.session()
    await session.schema_change(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)).as_string())
    try:
        yield name
    finally:
        await session.schema_change(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)).as_string())


def column(draft_id: str, name: str, code: str, *, not_null: bool = True) -> DesignColumn:
    return DesignColumn(id=draft_id, name=name, type=DesignColumnType(code=code), not_null=not_null)


def definition(**changes: Any) -> TableDefinition:
    base = TableDefinition(
        name='readings"new',
        columns=[
            column("c1", "observed_at", "timestamp_tz"),
            column("c2", "device", "integer"),
            column("c3", "value", "double", not_null=False),
        ],
        primary_key=DesignPrimaryKey(column_ids=["c2", "c1"]),
        indexes=[DesignIndex(
            id="i1", method="btree",
            keys=[IndexColumnKey(column_id="c1", direction="desc")],
        )],
        hypertable=TableHypertable(
            time_column_id="c1", chunk_interval=DesignDuration(amount=1, unit="day"),
            hash_dimensions=[TableHashDimension(column_id="c2", partitions=4)],
            columnstore=True, segment_mode="columns", segment_column_ids=["c2"],
            retention=DesignDuration(amount=30, unit="year"),
            reorder_index_id="i1",
        ),
    )
    return base.model_copy(update=changes)


async def plan(source: TimescaleSource, schema: str, design: TableDefinition) -> TablePlan:
    return await source.adapter().plan_table(TablePlanRequest(node_id=schema, definition=design))


async def problems(source: TimescaleSource, schema: str, design: TableDefinition) -> list[str]:
    answer = await plan(source, schema, design)
    assert answer.fingerprint == ""
    return [problem.message for problem in answer.problems]


async def test_a_designed_table_is_created_as_a_set_up_hypertable(source: TimescaleSource, schema: str) -> None:
    design = definition()
    answer = await plan(source, schema, design)
    assert answer.problems == [], answer.problems
    titles = [statement.title for statement in answer.statements]
    assert titles[:2] == ['Table readings"new', titles[1]] and titles[1].startswith("Index ")
    assert {"Hypertable", "Hash dimension device", "Columnstore", "Retention policy", "Reorder policy"} <= set(titles)
    assert "false, false, false)" in answer.statements[titles.index("Hypertable")].sql

    action = source.adapter().action("create_table")
    assert isinstance(action, JsonAction)
    await action.perform(schema, {
        "definition": design.model_dump(mode="json"), "fingerprint": answer.fingerprint,
    })

    session = source.session()
    table = PolicyTable(schema, 'readings"new')
    assert await session.query(_DIMENSIONS, (schema, table.table)) == [
        {"column_name": "observed_at", "dimension_type": "Time", "num_partitions": None},
        {"column_name": "device", "dimension_type": "Space", "num_partitions": 4},
    ]
    # The designer's own index and the key's; create_hypertable added none of its own.
    indexes = [row["indexname"] for row in await session.query(_INDEXES, (schema, table.table))]
    assert len(indexes) == 2
    assert len(await jobs(source, table, "policy_retention")) == 1
    assert len(await jobs(source, table, "policy_reorder")) == 1


async def test_the_time_column_must_require_a_value(source: TimescaleSource, schema: str) -> None:
    design = definition(
        columns=[column("c1", "observed_at", "timestamp_tz", not_null=False), *definition().columns[1:]],
        primary_key=None,
        hypertable=TableHypertable(time_column_id="c1", chunk_interval=DesignDuration(amount=1, unit="day")),
    )

    assert '"observed_at" partitions the hypertable, so it must have a value' in await problems(source, schema, design)


async def test_keys_hold_the_time_and_hash_columns(source: TimescaleSource, schema: str) -> None:
    design = definition(
        primary_key=DesignPrimaryKey(column_ids=["c2"]),
        unique_constraints=[DesignUnique(id="u1", column_ids=["c1"])],
    )

    found = await problems(source, schema, design)

    assert "The primary key of a hypertable must hold its time column and every hash column" in found
    assert "A unique constraint on a hypertable must hold its time column and every hash column" in found


async def test_a_hypertable_is_neither_unlogged_nor_declaratively_partitioned(
    source: TimescaleSource, schema: str,
) -> None:
    assert "A hypertable cannot be unlogged" in await problems(source, schema, definition(persistence="unlogged"))
    partitioned = definition(partition=DesignPartition(strategy="range", column_ids=["c1"]))
    assert "A hypertable partitions itself; choose it or declarative partitioning, not both" in (
        await problems(source, schema, partitioned)
    )


async def test_a_date_column_counts_in_days(source: TimescaleSource, schema: str) -> None:
    design = definition(
        columns=[column("c1", "observed_on", "date"), *definition().columns[1:]],
        hypertable=TableHypertable(time_column_id="c1", chunk_interval=DesignDuration(amount=6, unit="hour")),
    )

    assert "A chunk interval of this column is counted in days or weeks" in await problems(source, schema, design)
