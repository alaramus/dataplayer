"""An ordinary table converted from the hypertable editor, at once or as a job (D207, H3)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.hypertable_design import (
    ColumnstoreDesign,
    DesignDuration,
    HypertableDesign,
    OlderThan,
    SegmentColumns,
)
from app.adapters.operations import OperationTarget
from app.adapters.postgres.timescale.design_action import DesignHypertable
from compatibility.timescale.policy_tables import PolicyTable, jobs, registry
from compatibility.timescale.source import TimescaleSource

_IS_HYPERTABLE = """
    SELECT count(*) AS hypertables FROM timescaledb_information.hypertables
    WHERE hypertable_schema = %s AND hypertable_name = %s
"""
_CHUNKS = """
    SELECT count(*) AS chunks FROM timescaledb_information.chunks
    WHERE hypertable_schema = %s AND hypertable_name = %s
"""


@pytest.fixture
async def plain(source: TimescaleSource) -> AsyncIterator[PolicyTable]:
    target = PolicyTable(f"convert_{uuid.uuid4().hex[:12]}", 'events"quoted')
    session = source.session()
    await session.schema_change(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(target.schema)).as_string())
    try:
        await session.schema_change(sql.SQL(
            "CREATE TABLE {} (observed_at timestamptz, device integer NOT NULL, value integer)"
        ).format(target.identifier).as_string())
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


async def rows(source: TimescaleSource, target: PolicyTable, count: int, *, missing_time: bool = False) -> None:
    await source.session().schema_change(sql.SQL(
        "INSERT INTO {} SELECT TIMESTAMPTZ '2000-01-01' + make_interval(days => g), g, g "
        "FROM generate_series(1, {}) AS g"
    ).format(target.identifier, sql.Literal(count)).as_string())
    if missing_time:
        await source.session().schema_change(sql.SQL(
            "INSERT INTO {} VALUES (NULL, 0, 0)"
        ).format(target.identifier).as_string())


async def hypertable(source: TimescaleSource, target: PolicyTable) -> bool:
    found = await source.session().query(_IS_HYPERTABLE, (target.schema, target.table))
    return bool(found[0]["hypertables"])


def converting(**changes: Any) -> HypertableDesign:
    return HypertableDesign(
        time_column="observed_at", chunk_interval=DesignDuration(amount=1, unit="week"),
    ).model_copy(update=changes)


async def test_an_ordinary_table_reads_as_a_conversion_to_make(source: TimescaleSource, plain: PolicyTable) -> None:
    state = await editor(source).state(plain.node_id)

    assert state.reason is None and state.hypertable is False
    # Integer columns are candidates too, but a time column is the one proposed.
    assert [column.name for column in state.time_columns] == ["observed_at", "device", "value"]
    assert state.design is not None and state.design.time_column == "observed_at"
    assert state.design.chunk_interval == DesignDuration(amount=1, unit="week")
    assert state.has_chunks is False


async def test_an_empty_table_is_converted_and_set_up_at_once(source: TimescaleSource, plain: PolicyTable) -> None:
    design = converting(
        columnstore=ColumnstoreDesign(enabled=True, segment_by=SegmentColumns(columns=["device"])),
        retention=OlderThan(older_than=DesignDuration(amount=30, unit="year")),
    )
    action = editor(source)
    preview = await action.preview(plain.node_id, params(design))
    assert not preview.blocked, preview.summary
    assert preview.runs_as_job is False and preview.fingerprint is not None
    assert any("becomes NOT NULL" in item for item in preview.items)

    await action.perform_reviewed(plain.node_id, params(design), preview.fingerprint)

    assert await hypertable(source, plain)
    after = (await action.state(plain.node_id)).design
    assert after is not None and after.columnstore.segment_by == SegmentColumns(columns=["device"])
    assert len(await jobs(source, plain, "policy_retention")) == 1


async def test_a_table_with_rows_moves_them_as_one_job(source: TimescaleSource, plain: PolicyTable) -> None:
    await rows(source, plain, 40)
    design = converting(retention=OlderThan(older_than=DesignDuration(amount=50, unit="year")))
    action = editor(source)
    preview = await action.preview(plain.node_id, params(design))
    assert not preview.blocked, preview.summary
    assert preview.runs_as_job is True and preview.fingerprint is not None
    with pytest.raises(ActionRefused, match="runs as a job"):
        await action.perform_reviewed(plain.node_id, params(design), preview.fingerprint)

    plan = await action.plan_job(plain.node_id, params(design), preview.fingerprint)
    assert plan.targets == (OperationTarget(schema_name=plain.schema, name=plain.table),)
    assert await action.observe(plain.node_id, params(design), plan.targets) == ["unchanged"]

    assert await action.run_unit(plain.node_id, params(design), plan.unit_fingerprint, plan.targets[0]) == "completed"

    assert await hypertable(source, plain)
    chunks = await source.session().query(_CHUNKS, (plain.schema, plain.table))
    assert chunks[0]["chunks"] > 1
    counted = await source.session().query(sql.SQL("SELECT count(*) AS n FROM {}").format(
        plain.identifier,
    ).as_string())
    assert counted == [{"n": 40}]
    assert len(await jobs(source, plain, "policy_retention")) == 1
    assert await action.observe(plain.node_id, params(design), plan.targets) == ["as_requested"]


async def test_a_row_without_a_time_rolls_the_whole_conversion_back(
    source: TimescaleSource, plain: PolicyTable,
) -> None:
    await rows(source, plain, 5, missing_time=True)
    design = converting(retention=OlderThan(older_than=DesignDuration(amount=50, unit="year")))
    action = editor(source)
    preview = await action.preview(plain.node_id, params(design))
    assert preview.fingerprint is not None
    plan = await action.plan_job(plain.node_id, params(design), preview.fingerprint)

    with pytest.raises(ActionRefused):
        await action.run_unit(plain.node_id, params(design), plan.unit_fingerprint, plan.targets[0])

    assert not await hypertable(source, plain)
    assert await jobs(source, plain, "policy_retention") == []
    assert await action.observe(plain.node_id, params(design), plan.targets) == ["unchanged"]


async def test_a_unique_index_without_the_time_column_refuses(source: TimescaleSource, plain: PolicyTable) -> None:
    await source.session().schema_change(sql.SQL("CREATE UNIQUE INDEX ON {} (device)").format(
        plain.identifier,
    ).as_string())

    preview = await editor(source).preview(plain.node_id, params(converting()))

    assert preview.blocked and 'must include "observed_at"' in preview.summary


async def test_a_job_refuses_a_plan_that_changed_since_review(source: TimescaleSource, plain: PolicyTable) -> None:
    await rows(source, plain, 5)
    design = converting()
    action = editor(source)
    preview = await action.preview(plain.node_id, params(design))
    assert preview.fingerprint is not None
    plan = await action.plan_job(plain.node_id, params(design), preview.fingerprint)
    await source.session().schema_change(sql.SQL("ALTER TABLE {} ADD COLUMN extra integer").format(
        plain.identifier,
    ).as_string())

    with pytest.raises(ActionRefused) as refused:
        await action.run_unit(plain.node_id, params(design), plan.unit_fingerprint, plan.targets[0])

    assert refused.value.reason == "conflict"
    assert not await hypertable(source, plain)


async def test_a_hypertable_keeps_its_time_column(source: TimescaleSource, plain: PolicyTable) -> None:
    action = editor(source)
    preview = await action.preview(plain.node_id, params(converting()))
    assert preview.fingerprint is not None
    await action.perform_reviewed(plain.node_id, params(converting()), preview.fingerprint)

    other = await action.preview(plain.node_id, params(converting(time_column="device")))

    assert other.blocked and "cannot change the time column" in other.summary
