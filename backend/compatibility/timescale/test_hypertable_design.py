"""Hypertable settings read into one design and applied as one reviewed change (D207)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.hypertable_design import (
    ChosenByTimescale,
    ColumnstoreDesign,
    DesignDuration,
    HashDimensionDesign,
    HypertableDesign,
    KeptAsItIs,
    NoColumns,
    OlderThan,
    OrderColumns,
    OrderKey,
    SegmentColumns,
)
from app.adapters.postgres.timescale.design_action import DesignHypertable
from compatibility.timescale.policy_tables import (
    PolicyTable,
    disposable_hypertable,
    jobs,
    registry,
    reviewed,
    rows,
)
from compatibility.timescale.source import TimescaleSource

_DIMENSIONS = """
    SELECT column_name, num_partitions FROM timescaledb_information.dimensions
    WHERE hypertable_schema = %s AND hypertable_name = %s AND dimension_number > 1
"""


@pytest.fixture
async def table(source: TimescaleSource) -> AsyncIterator[PolicyTable]:
    async with disposable_hypertable(source, "design") as target:
        await source.session().schema_change(sql.SQL(
            'ALTER TABLE {} ADD COLUMN "x,y" integer, ADD COLUMN device text'
        ).format(target.identifier).as_string())
        await source.session().schema_change(sql.SQL(
            "CREATE INDEX design_order ON {} (value, observed_at DESC)"
        ).format(target.identifier).as_string())
        yield target


@pytest.fixture
async def empty(source: TimescaleSource) -> AsyncIterator[PolicyTable]:
    target = PolicyTable(f"design_empty_{uuid.uuid4().hex[:12]}", "readings")
    session = source.session()
    await session.schema_change(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(target.schema)).as_string())
    try:
        await session.schema_change(sql.SQL(
            "CREATE TABLE {} (observed_at timestamptz NOT NULL, device integer NOT NULL, value integer)"
        ).format(target.identifier).as_string())
        await session.query(
            "SELECT public.create_hypertable(%s::regclass, 'observed_at', chunk_time_interval => INTERVAL '1 day')",
            (target.identifier.as_string(),),
        )
        yield target
    finally:
        await session.schema_change(sql.SQL("DROP SCHEMA {} CASCADE").format(
            sql.Identifier(target.schema),
        ).as_string())


def editor(source: TimescaleSource) -> DesignHypertable:
    action = registry(source).action(DesignHypertable.name)
    assert isinstance(action, DesignHypertable)
    return action


def params(design: HypertableDesign) -> dict[str, Any]:
    return {"design": design.model_dump(mode="json")}


async def current(source: TimescaleSource, target: PolicyTable) -> HypertableDesign:
    state = await editor(source).state(target.node_id)
    assert state.design is not None, state.reason
    return state.design


async def apply(source: TimescaleSource, target: PolicyTable, design: HypertableDesign) -> None:
    action = editor(source)
    await action.perform_reviewed(target.node_id, params(design), await reviewed(action, target.node_id, params(design)))


async def refusal(source: TimescaleSource, target: PolicyTable, design: HypertableDesign) -> str:
    preview = await editor(source).preview(target.node_id, params(design))
    assert preview.blocked
    assert preview.fingerprint is None
    return preview.summary


def full() -> HypertableDesign:
    return HypertableDesign(
        chunk_interval=DesignDuration(amount=2, unit="day"),
        columnstore=ColumnstoreDesign(
            enabled=True,
            segment_by=SegmentColumns(columns=["x,y", "device"]),
            order_by=OrderColumns(columns=[OrderKey(column="value", descending=False, nulls_first=False)]),
            merge_interval=DesignDuration(amount=4, unit="day"),
        ),
        # Far beyond the fixture's rows: Timescale runs a new policy at once, and a job
        # dropping or compressing chunks mid-scenario would change what is being read.
        retention=OlderThan(older_than=DesignDuration(amount=30, unit="year")),
        columnstore_policy=OlderThan(older_than=DesignDuration(amount=20, unit="year")),
        reorder_index="design_order",
        tablespaces=["pg_default"],
    )


async def test_a_new_hypertable_reads_as_its_design(source: TimescaleSource, table: PolicyTable) -> None:
    state = await editor(source).state(table.node_id)

    assert state.reason is None
    assert state.design == HypertableDesign(
        time_column="observed_at",
        chunk_interval=DesignDuration(amount=1, unit="week"),
        columnstore=ColumnstoreDesign(
            enabled=False,
            segment_by=ChosenByTimescale() if state.per_chunk_defaults else NoColumns(),
            order_by=ChosenByTimescale(),
        ),
    )
    assert state.time_column == "observed_at"
    assert state.has_chunks and not state.compressed_chunks
    assert "design_order" in state.indexes
    assert "pg_default" in state.tablespaces
    assert state.per_chunk_defaults == source.at_least("2.22.1")


async def test_one_plan_sets_everything_and_reads_back(source: TimescaleSource, table: PolicyTable) -> None:
    before = await rows(source, table)
    design = full()
    preview = await editor(source).preview(table.node_id, params(design))
    assert not preview.blocked, preview.summary
    assert any("retention" in item for item in preview.items)

    await apply(source, table, design)

    after = await current(source, table)
    # Timescale appends the time column to an order that does not name it, and the plan says so first.
    order = OrderColumns(columns=[
        OrderKey(column="value", descending=False, nulls_first=False),
        OrderKey(column="observed_at", descending=True, nulls_first=True),
    ])
    assert after == design.model_copy(update={
        "time_column": "observed_at",
        "columnstore": design.columnstore.model_copy(update={"order_by": order}),
    })
    assert len(await jobs(source, table, "policy_retention")) == 1
    assert len(await jobs(source, table, "policy_compression")) == 1
    assert len(await jobs(source, table, "policy_reorder")) == 1
    assert await rows(source, table) == before

    # What was applied is now the state, so the same design has nothing to change.
    assert "already matches" in await refusal(source, table, after)


async def test_emptied_fields_remove_what_they_held(source: TimescaleSource, table: PolicyTable) -> None:
    await apply(source, table, full())
    applied = await current(source, table)

    await apply(source, table, applied.model_copy(update={
        "retention": None, "columnstore_policy": None, "reorder_index": None, "tablespaces": [],
        "columnstore": applied.columnstore.model_copy(update={"merge_interval": None}),
    }))

    after = await current(source, table)
    assert after.retention is None and after.columnstore_policy is None and after.reorder_index is None
    assert after.tablespaces == [] and after.columnstore.merge_interval is None
    assert await jobs(source, table, "policy_retention") == []
    assert await jobs(source, table, "policy_reorder") == []


async def test_a_changed_age_replaces_the_job(source: TimescaleSource, table: PolicyTable) -> None:
    await apply(source, table, full())
    first = await jobs(source, table, "policy_retention")
    applied = await current(source, table)

    await apply(source, table, applied.model_copy(update={
        "retention": OlderThan(older_than=DesignDuration(amount=40, unit="year")),
    }))

    second = await jobs(source, table, "policy_retention")
    assert len(second) == 1 and second[0]["job_id"] != first[0]["job_id"]
    assert (await current(source, table)).retention == OlderThan(older_than=DesignDuration(amount=40, unit="year"))


async def test_a_policy_the_editor_cannot_say_is_kept(source: TimescaleSource, table: PolicyTable) -> None:
    await source.session().query(
        "SELECT public.add_retention_policy(%s::regclass, INTERVAL '10000 days 02:00:00')",
        (table.identifier.as_string(),),
    )
    state = await editor(source).state(table.node_id)
    assert state.design is not None and state.design.retention == KeptAsItIs()
    assert state.retention is not None and "10000 days 02:00:00" in state.retention.description
    job = await jobs(source, table, "policy_retention")

    await apply(source, table, state.design.model_copy(update={"chunk_interval": DesignDuration(amount=3, unit="day")}))

    assert await jobs(source, table, "policy_retention") == job


async def test_the_columnstore_turns_off_only_without_its_policy(source: TimescaleSource, table: PolicyTable) -> None:
    await apply(source, table, full())
    applied = await current(source, table)
    off = applied.model_copy(update={"columnstore": ColumnstoreDesign(enabled=False)})

    assert "Remove the columnstore policy" in await refusal(source, table, off)

    await apply(source, table, off.model_copy(update={"columnstore_policy": None}))
    assert (await current(source, table)).columnstore.enabled is False


async def test_compressed_chunks_keep_the_columnstore_on(source: TimescaleSource, table: PolicyTable) -> None:
    await apply(source, table, full().model_copy(update={"columnstore_policy": None}))
    await source.session().query(
        "SELECT public.compress_chunk(chunk) FROM public.show_chunks(%s::regclass) AS chunk LIMIT 1",
        (table.identifier.as_string(),),
    )
    applied = await current(source, table)

    summary = await refusal(source, table, applied.model_copy(update={"columnstore": ColumnstoreDesign(enabled=False)}))
    assert "decompress them first" in summary


async def test_returning_to_timescale_choice_needs_a_release_that_has_it(
    source: TimescaleSource, table: PolicyTable,
) -> None:
    await apply(source, table, full().model_copy(update={"columnstore_policy": None}))
    applied = await current(source, table)
    chosen = applied.model_copy(update={"columnstore": applied.columnstore.model_copy(update={
        "segment_by": ChosenByTimescale(),
    })})

    if not source.at_least("2.22.1"):
        assert "cannot return a setting to its own choice" in await refusal(source, table, chosen)
        return
    await apply(source, table, chosen)
    assert (await current(source, table)).columnstore.segment_by == ChosenByTimescale()


async def test_segmenting_by_nothing_is_kept_apart_from_unset(source: TimescaleSource, table: PolicyTable) -> None:
    design = full().model_copy(update={"columnstore_policy": None})
    await apply(source, table, design.model_copy(update={
        "columnstore": design.columnstore.model_copy(update={"segment_by": NoColumns()}),
    }))

    assert (await current(source, table)).columnstore.segment_by == NoColumns()


async def test_a_hash_dimension_is_added_only_while_empty(
    source: TimescaleSource, table: PolicyTable, empty: PolicyTable,
) -> None:
    hashed = [HashDimensionDesign(column="device", partitions=4)]
    with_rows = (await current(source, table)).model_copy(update={"hash_dimensions": hashed})
    assert "holds no chunks" in await refusal(source, table, with_rows)

    await apply(source, empty, (await current(source, empty)).model_copy(update={"hash_dimensions": hashed}))
    assert await source.session().query(_DIMENSIONS, (empty.schema, empty.table)) == [
        {"column_name": "device", "num_partitions": 4},
    ]

    resized = (await current(source, empty)).model_copy(update={
        "hash_dimensions": [HashDimensionDesign(column="device", partitions=6)],
    })
    await apply(source, empty, resized)
    assert (await current(source, empty)).hash_dimensions == resized.hash_dimensions
    assert "cannot remove the hash dimension" in await refusal(
        source, empty, resized.model_copy(update={"hash_dimensions": []}),
    )


async def test_a_plan_reviewed_before_the_source_changed_is_refused(
    source: TimescaleSource, table: PolicyTable,
) -> None:
    design = full()
    action = editor(source)
    fingerprint = await reviewed(action, table.node_id, params(design))
    await source.session().query(
        "SELECT public.add_retention_policy(%s::regclass, INTERVAL '50 years')", (table.identifier.as_string(),),
    )

    with pytest.raises(ActionRefused) as refused:
        await action.perform_reviewed(table.node_id, params(design), fingerprint)

    assert refused.value.reason == "conflict"
    assert len(await jobs(source, table, "policy_reorder")) == 0
