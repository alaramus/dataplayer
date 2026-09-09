"""Disposable mutation evidence for the unregistered interval strategy."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import psycopg
import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.postgres.actions import PostgresActions
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale import interval_execution
from app.adapters.postgres.timescale.interval_action import SetChunkInterval
from app.adapters.postgres.timescale.interval_plan import plan_chunk_interval
from app.adapters.postgres.timescale.plans import ChunkIntervalPlan, TimeDuration
from compatibility.timescale.source import TimescaleSource


@dataclass(frozen=True)
class IntervalTable:
    schema: str
    table: str = 'events"quoted'

    @property
    def identifier(self) -> sql.Identifier:
        return sql.Identifier(self.schema, self.table)


@pytest.fixture
async def interval_table(source: TimescaleSource) -> AsyncIterator[IntervalTable]:
    target = IntervalTable(f"interval_{uuid.uuid4().hex[:12]}")
    session = source.session()
    await session.schema_change(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(target.schema)).as_string())
    try:
        await session.schema_change(sql.SQL(
            "CREATE TABLE {} (observed_at timestamptz NOT NULL, value integer NOT NULL)"
        ).format(target.identifier).as_string())
        await session.query(
            "SELECT public.create_hypertable(%s::regclass, 'observed_at', "
            "chunk_time_interval => INTERVAL '7 days')", (target.identifier.as_string(),),
        )
        await session.schema_change(sql.SQL(
            "INSERT INTO {} VALUES ('2026-01-01 00:00:00+00', 1), ('2026-01-20 00:00:00+00', 2)"
        ).format(target.identifier).as_string())
        yield target
    finally:
        await session.schema_change(sql.SQL("DROP SCHEMA {} CASCADE").format(
            sql.Identifier(target.schema),
        ).as_string())


async def planned(source: TimescaleSource, target: IntervalTable) -> ChunkIntervalPlan:
    return await plan_chunk_interval(
        source.session(), target.schema, target.table, TimeDuration(amount=2, unit="day"),
    )


async def native_set(source: TimescaleSource, plan: ChunkIntervalPlan, duration: str) -> None:
    await source.session().query(sql.SQL(
        "SELECT {}(%s::regclass, %s::interval, %s::name)"
    ).format(sql.Identifier(plan.strategy.function_schema, "set_chunk_time_interval")).as_string(), (
        plan.target.relation_oid, duration, plan.target.column_name,
    ))


async def test_interval_change_preserves_existing_chunks_and_changes_future_chunks(
    source: TimescaleSource, interval_table: IntervalTable,
) -> None:
    session = source.session()
    target = interval_table
    chunks = """
        SELECT chunk_name, range_start, range_end
        FROM timescaledb_information.chunks
        WHERE hypertable_schema = %s AND hypertable_name = %s ORDER BY chunk_name
    """
    before = await session.query(chunks, (target.schema, target.table))
    assert len(before) == 2
    plan = await planned(source, target)
    registry = PostgresActions(session, PostgresCatalog(session))
    node_id = f"{target.schema}.{target.table}"
    assert SetChunkInterval.name in {item.name for item in await registry.all_actions()}
    assert SetChunkInterval.name in {item.name for item in await registry.available(node_id)}
    action = registry.action(SetChunkInterval.name)
    assert isinstance(action, SetChunkInterval)
    preview = await action.preview(node_id, plan.interval.model_dump())
    assert preview.fingerprint == plan.fingerprint()
    await action.perform_reviewed(
        node_id, plan.interval.model_dump(), plan.fingerprint(),
    )
    assert await session.query(chunks, (target.schema, target.table)) == before
    assert (await planned(source, target)).target.current_interval == "2 days"
    await session.schema_change(sql.SQL(
        "INSERT INTO {} VALUES ('2026-03-01 00:00:00+00', 3)"
    ).format(target.identifier).as_string())
    after = await session.query(chunks, (target.schema, target.table))
    created = [row for row in after if row["chunk_name"] not in {old["chunk_name"] for old in before}]
    assert len(created) == 1
    assert (created[0]["range_end"] - created[0]["range_start"]).total_seconds() == 2 * 86400


async def test_metadata_view_lock_alone_blocks_external_native_setter(
    source: TimescaleSource, interval_table: IntervalTable,
) -> None:
    plan = await planned(source, interval_table)
    async with source.session().acquire() as owner:
        async with owner.transaction():
            await owner.execute("SET LOCAL lock_timeout = '2s'")
            await owner.execute(interval_execution._METADATA_LOCK)
            async with source.session().acquire() as writer:
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    async with writer.transaction():
                        await writer.execute("SET LOCAL lock_timeout = '200ms'")
                        await writer.execute(sql.SQL(
                            "SELECT {}(%s::regclass, %s::interval, %s::name)"
                        ).format(sql.Identifier(plan.strategy.function_schema, "set_chunk_time_interval")), (
                            plan.target.relation_oid, "3 days", plan.target.column_name,
                        ))
    assert (await planned(source, interval_table)).fingerprint() == plan.fingerprint()


async def test_external_change_before_lock_acquisition_requires_new_review(
    source: TimescaleSource, interval_table: IntervalTable, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = interval_table
    reviewed = await planned(source, target)
    calls = 0

    async def change_after_read(
        reader: PostgresReader, schema: str, table: str, duration: TimeDuration,
    ) -> ChunkIntervalPlan:
        nonlocal calls
        result = await plan_chunk_interval(reader, schema, table, duration)
        calls += 1
        if calls == 1:
            await native_set(source, result, "3 days")
        return result

    monkeypatch.setattr(interval_execution, "plan_chunk_interval", change_after_read)
    with pytest.raises(ActionRefused, match="review it again"):
        await interval_execution.execute_chunk_interval(
            source.session(), target.schema, target.table, reviewed.interval, reviewed.fingerprint(),
        )
    assert calls == 2
    assert (await planned(source, target)).target.current_interval == "3 days"


async def test_native_refusal_leaves_interval_unchanged(
    source: TimescaleSource, interval_table: IntervalTable,
) -> None:
    target = interval_table
    duration = TimeDuration(amount=2_147_483_647, unit="week")
    plan = await plan_chunk_interval(source.session(), target.schema, target.table, duration)
    with pytest.raises(ActionRefused):
        await interval_execution.execute_chunk_interval(
            source.session(), target.schema, target.table, duration, plan.fingerprint(),
        )
    assert (await planned(source, target)).target.current_interval == plan.target.current_interval


async def test_cancellation_releases_metadata_locks_without_changing_interval(
    source: TimescaleSource, interval_table: IntervalTable, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = interval_table
    reviewed = await planned(source, target)
    locked = asyncio.Event()
    resume = asyncio.Event()
    calls = 0

    async def pause_after_locked_read(
        reader: PostgresReader, schema: str, table: str, duration: TimeDuration,
    ) -> ChunkIntervalPlan:
        nonlocal calls
        result = await plan_chunk_interval(reader, schema, table, duration)
        calls += 1
        if calls == 2:
            locked.set()
            await resume.wait()
        return result

    monkeypatch.setattr(interval_execution, "plan_chunk_interval", pause_after_locked_read)
    task = asyncio.create_task(interval_execution.execute_chunk_interval(
        source.session(), target.schema, target.table, reviewed.interval, reviewed.fingerprint(),
    ))
    try:
        await asyncio.wait_for(locked.wait(), timeout=4)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert (await planned(source, target)).fingerprint() == reviewed.fingerprint()
    async with asyncio.timeout(5):
        await native_set(source, reviewed, "3 days")
    assert (await planned(source, target)).target.current_interval == "3 days"


async def test_hypertable_owner_without_metadata_lock_permission_cannot_plan(
    source: TimescaleSource, interval_table: IntervalTable,
) -> None:
    session = source.session()
    target = interval_table
    await session.schema_change(sql.SQL("GRANT USAGE ON SCHEMA {} TO fixture_no_stats").format(
        sql.Identifier(target.schema),
    ).as_string())
    await session.schema_change(sql.SQL("ALTER TABLE {} OWNER TO fixture_no_stats").format(
        target.identifier,
    ).as_string())
    restricted = PostgresSession(source.options(user="fixture_no_stats"))
    with pytest.raises(ActionRefused, match="metadata lock permission"):
        await plan_chunk_interval(restricted, target.schema, target.table, TimeDuration(amount=2, unit="day"))


async def test_concrete_overload_refuses_polymorphic_api_planning(
    source: TimescaleSource, interval_table: IntervalTable,
) -> None:
    session = source.session()
    await session.schema_change(
        "CREATE FUNCTION public.set_chunk_time_interval(regclass, interval, name) "
        "RETURNS void LANGUAGE plpgsql AS 'BEGIN RAISE EXCEPTION ''must not run''; END;'"
    )
    try:
        with pytest.raises(ActionRefused):
            await planned(source, interval_table)
    finally:
        await session.schema_change("DROP FUNCTION public.set_chunk_time_interval(regclass, interval, name)")
