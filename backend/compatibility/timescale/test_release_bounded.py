"""Options a release has or lacks, each proven on both sides of where it begins (D207, H7)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused, JsonAction
from app.adapters.hypertable_design import (
    ChosenByTimescale,
    ColumnstoreDesign,
    DesignDuration,
    HypertableDesign,
    NoColumns,
    OlderThan,
    OrderColumns,
    OrderKey,
    SparseColumns,
    SparseIndex,
)
from app.adapters.postgres.timescale.chunk_maintenance_action import MaintainChunks
from app.adapters.postgres.timescale.chunk_skipping_action import ChunkSkipping
from app.adapters.postgres.timescale.design_action import DesignHypertable
from app.adapters.table_design import (
    DesignColumn,
    DesignColumnType,
    DesignPrimaryKey,
    TableDefinition,
    TableHypertable,
    TableOrderKey,
    TablePlanRequest,
    TableSparseIndex,
)
from compatibility.timescale.policy_tables import PolicyTable, jobs, registry
from compatibility.timescale.source import TimescaleSource

DAY = DesignDuration(amount=1, unit="day")
SPARSE = SparseColumns(indexes=[
    SparseIndex(column="device", kind="bloom"), SparseIndex(column="value", kind="minmax"),
])
# Timescale sets sparse indexes only beside a named order.
ORDER = OrderColumns(columns=[OrderKey(column="observed_at", descending=True, nulls_first=True)])


@pytest.fixture
async def schema(source: TimescaleSource) -> AsyncIterator[str]:
    name = f"bounded_{uuid.uuid4().hex[:12]}"
    session = source.session()
    await session.schema_change(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)).as_string())
    try:
        yield name
    finally:
        await session.schema_change(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)).as_string())


async def execute(source: TimescaleSource, statement: str, target: PolicyTable) -> None:
    await source.session().schema_change(sql.SQL(statement).format(
        target.identifier, literal=sql.Literal(target.identifier.as_string()),
    ).as_string())


async def hypertable(source: TimescaleSource, schema: str) -> PolicyTable:
    target = PolicyTable(schema, "readings")
    await execute(source, "CREATE TABLE {} (observed_at timestamptz NOT NULL, device integer, value integer, "
                  "note text)", target)
    await execute(source, "SELECT create_hypertable({literal}::regclass, by_range('observed_at', interval '1 day'))",
                  target)
    await execute(source, "INSERT INTO {} SELECT TIMESTAMPTZ '2020-01-01 00:00+00' + make_interval(hours => g), "
                  "g % 3, g, 'n' FROM generate_series(0, 71) AS g", target)
    return target


def editor(source: TimescaleSource) -> DesignHypertable:
    action = registry(source).action(DesignHypertable.name)
    assert isinstance(action, DesignHypertable)
    return action


def params(design: HypertableDesign) -> dict[str, Any]:
    return {"design": design.model_dump(mode="json")}


async def apply(source: TimescaleSource, target: PolicyTable, design: HypertableDesign) -> None:
    preview = await editor(source).preview(target.node_id, params(design))
    assert not preview.blocked and preview.fingerprint is not None, preview.summary
    await editor(source).perform_reviewed(target.node_id, params(design), preview.fingerprint)


async def summary(source: TimescaleSource, target: PolicyTable, design: HypertableDesign) -> str:
    preview = await editor(source).preview(target.node_id, params(design))
    assert preview.blocked
    return preview.summary


async def current(source: TimescaleSource, target: PolicyTable) -> HypertableDesign:
    state = await editor(source).state(target.node_id)
    assert state.design is not None, state.reason
    return state.design


async def test_sparse_indexes_have_three_states_from_2_22(source: TimescaleSource, schema: str) -> None:
    target = await hypertable(source, schema)
    state = await editor(source).state(target.node_id)
    assert state.sparse_indexes_supported is source.at_least("2.22.0")
    wanted = ColumnstoreDesign(enabled=True, order_by=ORDER, sparse_indexes=SPARSE)
    assert "need the order to be named" in await summary(source, target, (await current(source, target)).model_copy(
        update={"columnstore": ColumnstoreDesign(enabled=True, sparse_indexes=SPARSE)},
    )) or not source.at_least("2.22.0")
    if not source.at_least("2.22.0"):
        assert "has no sparse indexes" in await summary(source, target, HypertableDesign(
            chunk_interval=DAY, columnstore=wanted,
        ))
        return
    await apply(source, target, (await current(source, target)).model_copy(update={"columnstore": wanted}))
    read = await current(source, target)
    assert read.columnstore.sparse_indexes == SPARSE
    assert (await editor(source).preview(target.node_id, params(read))).summary.endswith("already matches these settings")

    for state_of_index in (NoColumns(), ChosenByTimescale()):
        changed = read.columnstore.model_copy(update={"sparse_indexes": state_of_index})
        await apply(source, target, read.model_copy(update={"columnstore": changed}))
        assert (await current(source, target)).columnstore.sparse_indexes == state_of_index


async def test_a_compaction_policy_where_the_release_has_one(source: TimescaleSource, schema: str) -> None:
    target = await hypertable(source, schema)
    on = (await current(source, target)).model_copy(update={
        "columnstore": ColumnstoreDesign(enabled=True), "compaction_policy": True,
    })
    supported = (await editor(source).state(target.node_id)).compaction_supported
    assert supported is source.at_least("2.29.0")
    if not supported:
        assert "has no compaction policy" in await summary(source, target, on)
        return
    await apply(source, target, on)
    assert len(await jobs(source, target, "policy_compaction")) == 1
    assert (await current(source, target)).compaction_policy is True
    await apply(source, target, (await current(source, target)).model_copy(update={"compaction_policy": False}))
    assert await jobs(source, target, "policy_compaction") == []


async def test_uuidv7_time_is_edited_from_2_25(source: TimescaleSource, schema: str) -> None:
    target = PolicyTable(schema, "events")
    await execute(source, "CREATE TABLE {} (id uuid NOT NULL, observed_at timestamptz, value integer)", target)
    state = await editor(source).state(target.node_id)
    names = [column.name for column in state.time_columns]
    assert ("id" in names) is source.at_least("2.25.0")
    if not source.at_least("2.25.0"):
        if source.at_least("2.22.0"):
            # A hypertable made by SQL on a release that has it partly is refused, saying so.
            await execute(source, "SELECT create_hypertable({literal}::regclass, by_range('id', interval '1 day'))",
                          target)
            refused = await editor(source).state(target.node_id)
            assert refused.reason is not None and "UUIDv7 only partly" in refused.reason
        return
    design = HypertableDesign(
        time_column="id", chunk_interval=DAY, retention=OlderThan(older_than=DesignDuration(amount=30, unit="year")),
    )
    await apply(source, target, design)
    read = await editor(source).state(target.node_id)
    assert read.time_column_type == "uuid" and read.design is not None
    assert read.design.chunk_interval == DAY
    assert len(await jobs(source, target, "policy_retention")) == 1


async def test_chunk_skipping_from_2_16(source: TimescaleSource, schema: str) -> None:
    target = await hypertable(source, schema)
    enable = registry(source).action("timescale_enable_chunk_skipping")
    disable = registry(source).action("timescale_disable_chunk_skipping")
    assert isinstance(enable, ChunkSkipping) and isinstance(disable, ChunkSkipping)
    preview = await enable.preview(target.node_id, {"column": "value"})
    if not source.at_least("2.16.0"):
        assert preview.blocked and "enable_chunk_skipping API is not usable" in preview.summary
        return
    assert not preview.blocked and preview.fingerprint is not None, preview.summary
    assert any("enable_chunk_skipping is off" in item for item in preview.items)
    await enable.perform_reviewed(target.node_id, {"column": "value"}, preview.fingerprint)
    # Read where Timescale keeps it, which the application itself never reads (D121).
    assert await recorded(source, target) > 0

    # Asking again for what already holds changes nothing and does not fail.
    again = await enable.preview(target.node_id, {"column": "value"})
    assert again.fingerprint is not None
    await enable.perform_reviewed(target.node_id, {"column": "value"}, again.fingerprint)
    off = await disable.preview(target.node_id, {"column": "value"})
    assert off.fingerprint is not None
    await disable.perform_reviewed(target.node_id, {"column": "value"}, off.fingerprint)
    assert await recorded(source, target) == 0

    text = await enable.preview(target.node_id, {"column": "note"})
    assert text.blocked and "integer, date and timestamp columns" in text.summary


async def recorded(source: TimescaleSource, target: PolicyTable) -> int:
    rows = await source.session().query(
        "SELECT count(*) AS n FROM _timescaledb_catalog.chunk_column_stats AS stats "
        "JOIN _timescaledb_catalog.hypertable AS hypertable ON hypertable.id = stats.hypertable_id "
        "WHERE hypertable.schema_name = %s AND hypertable.table_name = %s AND stats.column_name = 'value'",
        (target.schema, target.table),
    )
    return int(rows[0]["n"])


async def test_a_merge_that_lets_reads_go_on_from_2_29(source: TimescaleSource, schema: str) -> None:
    target = await hypertable(source, schema)
    action = registry(source).action("timescale_merge_chunks_concurrently")
    assert isinstance(action, MaintainChunks)
    window = {"starts_from": None, "ends_by": "2020-01-03T00:00:00Z"}
    preview = await action.preview(target.node_id, window)
    if not source.at_least("2.29.0"):
        assert preview.blocked and "merge_chunks_concurrently API is not usable" in preview.summary
        return
    assert preview.fingerprint is not None, preview.summary
    plan = await action.plan_job(target.node_id, window, preview.fingerprint)
    (unit,) = plan.targets
    assert await action.run_unit(target.node_id, window, plan.unit_fingerprint, unit) == "completed"
    assert await action.observe(target.node_id, window, plan.targets) == ["as_requested"]
    chunks = await source.session().query(
        "SELECT count(*) AS n FROM timescaledb_information.chunks WHERE hypertable_schema = %s",
        (target.schema,),
    )
    assert chunks == [{"n": 2}]


async def test_the_designer_creates_with_what_the_release_offers(source: TimescaleSource, schema: str) -> None:
    adapter = source.adapter()
    offer = (await adapter.table_design_options(schema)).hypertable
    assert (offer.sparse_indexes, offer.compaction, offer.uuid_time) == (
        source.at_least("2.22.0"), source.at_least("2.29.0"), source.at_least("2.25.0"),
    )
    definition = TableDefinition(
        name="made",
        columns=[
            DesignColumn(id="c1", name="id", type=DesignColumnType(code="uuid"), not_null=True),
            DesignColumn(id="c2", name="device", type=DesignColumnType(code="integer")),
        ],
        primary_key=DesignPrimaryKey(column_ids=["c1"]),
        hypertable=TableHypertable(
            time_column_id="c1", chunk_interval=DAY, columnstore=True,
            order_mode="columns", order_keys=[TableOrderKey(column_id="c1", descending=True, nulls_first=True)],
            sparse_mode="columns", sparse_indexes=[TableSparseIndex(column_id="c2", kind="bloom")],
            compaction_policy=True,
        ),
    )
    answer = await adapter.plan_table(TablePlanRequest(node_id=schema, definition=definition))
    if not offer.uuid_time:
        assert any("UUIDv7 only partly" in problem.message for problem in answer.problems)
        return
    assert answer.problems == [], answer.problems
    assert "Compaction policy" in [statement.title for statement in answer.statements]
    action = adapter.action("create_table")
    assert isinstance(action, JsonAction)
    await action.perform(schema, {"definition": definition.model_dump(mode="json"), "fingerprint": answer.fingerprint})
    made = PolicyTable(schema, "made")
    assert len(await jobs(source, made, "policy_compaction")) == 1
    state = await editor(source).state(made.node_id)
    assert state.design is not None
    assert state.design.columnstore.sparse_indexes == SparseColumns(indexes=[SparseIndex(column="device", kind="bloom")])


async def test_nothing_refuses_without_saying_why(source: TimescaleSource, schema: str) -> None:
    target = await hypertable(source, schema)
    with pytest.raises(ActionRefused):
        await registry(source).action("timescale_merge_chunks_concurrently").plan_job(
            target.node_id, {"starts_from": None, "ends_by": "2020-01-03T00:00:00Z"}, "0" * 64,
        )
