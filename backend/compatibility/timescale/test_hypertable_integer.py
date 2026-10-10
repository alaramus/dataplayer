"""Hypertables partitioned by an integer column, and their integer_now (D207, H5)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from psycopg import sql

from app.adapters.actions import JsonAction
from app.adapters.hypertable_design import (
    ColumnstoreDesign,
    ExistingNow,
    HypertableDesign,
    IntegerSpan,
    KeptNow,
    OlderThan,
    TemplateNow,
)
from app.adapters.postgres.timescale.design_action import DesignHypertable
from app.adapters.table_design import (
    DesignColumn,
    DesignColumnType,
    DesignPrimaryKey,
    TableDefinition,
    TableHypertable,
    TablePlanRequest,
)
from compatibility.timescale.policy_tables import PolicyTable, jobs, registry
from compatibility.timescale.source import TimescaleSource

_DIMENSION = """
    SELECT integer_interval, integer_now_func::text AS integer_now_func
    FROM timescaledb_information.dimensions
    WHERE hypertable_schema = %s AND hypertable_name = %s AND dimension_number = 1
"""
_POLICY = """
    SELECT config FROM timescaledb_information.jobs
    WHERE hypertable_schema = %s AND hypertable_name = %s AND proc_name = %s
"""


@pytest.fixture
async def schema(source: TimescaleSource) -> AsyncIterator[str]:
    name = f"integer_{uuid.uuid4().hex[:12]}"
    session = source.session()
    await session.schema_change(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)).as_string())
    try:
        yield name
    finally:
        await session.schema_change(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)).as_string())


async def execute(source: TimescaleSource, statement: sql.Composable) -> None:
    await source.session().schema_change(statement.as_string())


async def table(source: TimescaleSource, schema: str, column_type: str, *, hypertable: bool) -> PolicyTable:
    target = PolicyTable(schema, "ticks")
    await execute(source, sql.SQL("CREATE TABLE {} (tick {} NOT NULL, device integer, value integer)").format(
        target.identifier, sql.SQL(column_type),
    ))
    if hypertable:
        await execute(source, sql.SQL(
            "SELECT create_hypertable({}::regclass, by_range('tick', 1000::bigint), false, false, false)"
        ).format(sql.Literal(target.identifier.as_string())))
    return target


async def clock(source: TimescaleSource, schema: str, name: str, column_type: str) -> None:
    await execute(source, sql.SQL("CREATE FUNCTION {}() RETURNS {} LANGUAGE sql STABLE AS 'SELECT 1'").format(
        sql.Identifier(schema, name), sql.SQL(column_type),
    ))


def editor(source: TimescaleSource) -> DesignHypertable:
    action = registry(source).action(DesignHypertable.name)
    assert isinstance(action, DesignHypertable)
    return action


def params(design: HypertableDesign) -> dict[str, Any]:
    return {"design": design.model_dump(mode="json")}


async def apply(source: TimescaleSource, target: PolicyTable, design: HypertableDesign) -> None:
    action = editor(source)
    preview = await action.preview(target.node_id, params(design))
    assert not preview.blocked and preview.fingerprint is not None, preview.summary
    await action.perform_reviewed(target.node_id, params(design), preview.fingerprint)


async def summary(source: TimescaleSource, target: PolicyTable, design: HypertableDesign) -> str:
    preview = await editor(source).preview(target.node_id, params(design))
    assert preview.blocked
    return preview.summary


async def test_an_integer_table_converts_with_a_template_clock_and_a_counted_policy(
    source: TimescaleSource, schema: str,
) -> None:
    target = await table(source, schema, "bigint", hypertable=False)
    state = await editor(source).state(target.node_id)
    assert state.reason is None, state.reason
    # Every integer column is a candidate; the one that requires a value is proposed.
    assert [column.name for column in state.time_columns] == ["tick", "device", "value"]
    assert state.design is not None and state.design.time_column == "tick"
    tick = state.time_columns[0]
    assert tick.chunk_interval == IntegerSpan(amount="1000000")
    assert tick.now_templates == ["epoch_seconds", "epoch_milliseconds", "epoch_microseconds"]

    design = HypertableDesign(
        time_column="tick", chunk_interval=IntegerSpan(amount="5000"),
        integer_now=TemplateNow(template="epoch_seconds", name="unix_seconds"),
        # Far beyond any row, so the policy's first run drops nothing a test reads.
        retention=OlderThan(older_than=IntegerSpan(amount="9000000000")),
    )
    preview = await editor(source).preview(target.node_id, params(design))
    assert any("Create function" in item and "seconds since 1970" in item for item in preview.items)
    await apply(source, target, design)

    session = source.session()
    assert await session.query(_DIMENSION, (schema, target.table)) == [
        {"integer_interval": 5000, "integer_now_func": "unix_seconds"},
    ]
    (policy,) = await session.query(_POLICY, (schema, target.table, "policy_retention"))
    assert policy["config"]["drop_after"] == 9_000_000_000
    now = await session.query(sql.SQL("SELECT {}() AS now").format(
        sql.Identifier(schema, "unix_seconds"),
    ).as_string())
    assert now[0]["now"] > 1_700_000_000

    after = (await editor(source).state(target.node_id)).design
    assert after is not None
    assert after.chunk_interval == IntegerSpan(amount="5000")
    assert after.integer_now == ExistingNow(schema_name=schema, name="unix_seconds")
    assert after.retention == OlderThan(older_than=IntegerSpan(amount="9000000000"))
    assert (await editor(source).preview(target.node_id, params(after))).summary.endswith("already matches these settings")


async def test_an_integer_hypertable_takes_an_existing_clock_and_can_swap_it(
    source: TimescaleSource, schema: str,
) -> None:
    target = await table(source, schema, "integer", hypertable=True)
    await clock(source, schema, "first_clock", "integer")
    await clock(source, schema, "second_clock", "integer")
    await clock(source, schema, "wide_clock", "bigint")
    state = await editor(source).state(target.node_id)
    assert state.reason is None, state.reason
    assert state.interval_units == [] and state.design is not None
    assert state.design.chunk_interval == IntegerSpan(amount="1000")
    offered = {(item.schema_name, item.name) for item in state.now_functions}
    assert {(schema, "first_clock"), (schema, "second_clock")} <= offered
    assert (schema, "wide_clock") not in offered

    base = state.design
    columnstore = ColumnstoreDesign(enabled=True)
    policy = OlderThan(older_than=IntegerSpan(amount="2000000000"))
    assert "needs an integer_now" in await summary(source, target, base.model_copy(update={
        "columnstore": columnstore, "columnstore_policy": policy,
    }))
    assert "at most 2,147,483,647" in await summary(source, target, base.model_copy(update={
        "chunk_interval": IntegerSpan(amount="3000000000"),
    }))

    await apply(source, target, base.model_copy(update={
        "chunk_interval": IntegerSpan(amount="250"), "columnstore": columnstore, "columnstore_policy": policy,
        "integer_now": ExistingNow(schema_name=schema, name="first_clock"),
    }))
    assert len(await jobs(source, target, "policy_compression")) == 1

    current = (await editor(source).state(target.node_id)).design
    assert current is not None
    await apply(source, target, current.model_copy(update={
        "integer_now": ExistingNow(schema_name=schema, name="second_clock"),
    }))
    assert await source.session().query(_DIMENSION, (schema, target.table)) == [
        {"integer_interval": 250, "integer_now_func": "second_clock"},
    ]


async def test_a_clock_name_already_in_use_is_refused(source: TimescaleSource, schema: str) -> None:
    target = await table(source, schema, "bigint", hypertable=True)
    await clock(source, schema, "taken", "integer")
    design = HypertableDesign(
        chunk_interval=IntegerSpan(amount="1000"), integer_now=TemplateNow(template="epoch_milliseconds", name="taken"),
    )
    assert 'named "taken" already exists' in await summary(source, target, design)


async def test_a_dropped_clock_is_kept_as_it_is_by_its_name(source: TimescaleSource, schema: str) -> None:
    target = await table(source, schema, "bigint", hypertable=True)
    await clock(source, schema, "gone_clock", "bigint")
    await execute(source, sql.SQL("SELECT set_integer_now_func({}::regclass, {}::regproc)").format(
        sql.Literal(target.identifier.as_string()), sql.Literal(f'"{schema}"."gone_clock"'),
    ))
    # TimescaleDB lets the function go while the hypertable still names it.
    await execute(source, sql.SQL("DROP FUNCTION {}()").format(sql.Identifier(schema, "gone_clock")))

    state = await editor(source).state(target.node_id)
    assert state.design is not None and state.design.integer_now == KeptNow()
    assert state.integer_now_name == "gone_clock"
    assert "cannot take an integer_now function away" in await summary(
        source, target, state.design.model_copy(update={"integer_now": None}),
    )


async def test_a_merge_interval_on_integer_time_is_left_to_sql(source: TimescaleSource, schema: str) -> None:
    target = await table(source, schema, "bigint", hypertable=True)
    # Read as a time interval even on this column: the source stores seconds nobody chose.
    await execute(source, sql.SQL(
        "ALTER TABLE {} SET (timescaledb.compress, timescaledb.compress_chunk_time_interval = '2000')"
    ).format(target.identifier))

    state = await editor(source).state(target.node_id)
    assert state.reason is not None and "merges compressed chunks by a time interval" in state.reason


async def test_the_designer_creates_an_integer_hypertable_with_its_clock(
    source: TimescaleSource, schema: str,
) -> None:
    definition = TableDefinition(
        name="counted",
        columns=[
            DesignColumn(id="c1", name="tick", type=DesignColumnType(code="bigint"), not_null=True),
            DesignColumn(id="c2", name="value", type=DesignColumnType(code="integer")),
        ],
        primary_key=DesignPrimaryKey(column_ids=["c1"]),
        hypertable=TableHypertable(
            time_column_id="c1", chunk_interval=IntegerSpan(amount="86400000"),
            integer_now=TemplateNow(template="epoch_milliseconds", name="unix_ms"),
            retention=IntegerSpan(amount="9000000000000"),
        ),
    )
    adapter = source.adapter()
    options = await adapter.table_design_options(schema)
    bigint = next(item for item in options.hypertable.integer_types if item.type == "bigint")
    assert bigint.now_templates == ["epoch_seconds", "epoch_milliseconds", "epoch_microseconds"]

    answer = await adapter.plan_table(TablePlanRequest(node_id=schema, definition=definition))
    assert answer.problems == [], answer.problems
    titles = [statement.title for statement in answer.statements]
    assert titles.index("Function unix_ms") < titles.index("Hypertable") < titles.index("Integer now")

    action = adapter.action("create_table")
    assert isinstance(action, JsonAction)
    await action.perform(schema, {"definition": definition.model_dump(mode="json"), "fingerprint": answer.fingerprint})

    assert await source.session().query(_DIMENSION, (schema, "counted")) == [
        {"integer_interval": 86_400_000, "integer_now_func": "unix_ms"},
    ]
    assert len(await jobs(source, PolicyTable(schema, "counted"), "policy_retention")) == 1
