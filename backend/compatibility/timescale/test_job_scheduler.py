"""A policy change never kills the database's job scheduler (D211).

Each scenario pauses DataPlayer's transaction just after its locks, makes the
policy's job due, waits until the scheduler has taken the job up — started it,
or stopped on a lock at its start — and then lets the change remove the job.
Up to 2.25 the scheduler holds the job's lock while it waits; a change that
then waits for that lock closes a cycle, PostgreSQL ends the scheduler, and on
most releases nothing starts it again.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest
from psycopg import sql

from app.adapters.hypertable_design import HypertableDesign
from app.adapters.postgres.timescale import age_policy_execution, design_execution
from app.adapters.postgres.timescale.age_policy_action import (
    RemoveRetentionPolicy,
    SetRetentionPolicy,
)
from app.adapters.postgres.timescale.age_policy_plan import RETENTION, plan_age_policy
from compatibility.timescale.policy_tables import (
    PolicyTable,
    disposable_hypertable,
    registry,
    reviewed,
)
from compatibility.timescale.source import TimescaleSource
from compatibility.timescale.test_hypertable_design import current, editor, params

_SCHEDULER = """
    SELECT pid FROM pg_catalog.pg_stat_activity
    WHERE datname = pg_catalog.current_database()
      AND backend_type = 'TimescaleDB Background Worker Scheduler'
"""

_WAITING = "SELECT 1 FROM pg_catalog.pg_locks WHERE pid = %s AND NOT granted"

_STARTED = """
    SELECT count(*) AS started FROM timescaledb_information.job_stats
    WHERE job_id = ANY(%s::integer[]) AND last_run_started_at >= %s
"""

# A first run far away, so the job stays quiet until the scenario makes it due.
_QUIET = "SELECT public.{}(%s::regclass, INTERVAL '10 years', initial_start => now() + INTERVAL '1 day')"


async def scheduler(source: TimescaleSource) -> int | None:
    rows = await source.session().query(_SCHEDULER)
    return int(rows[0]["pid"]) if rows else None


async def quiet_policy(source: TimescaleSource, target: PolicyTable, routine: str) -> int:
    rows = await source.session().query(
        sql.SQL(_QUIET).format(sql.Identifier(routine)).as_string(), (target.identifier.as_string(),),
    )
    return int(next(iter(rows[0].values())))


async def make_due(source: TimescaleSource, job_ids: list[int]) -> Any:
    rows = await source.session().query("SELECT now() + INTERVAL '1 second' AS due")
    due = rows[0]["due"]
    for job_id in job_ids:
        await source.session().query("SELECT public.alter_job(%s, next_start => %s)", (job_id, due))
    return due


async def taken_up(source: TimescaleSource, pid: int, job_ids: list[int], due: Any) -> None:
    """Until the scheduler waits on a lock or has recorded the start of every job."""
    async with asyncio.timeout(10):
        while True:
            if await source.session().query(_WAITING, (pid,)):
                return
            started = await source.session().query(_STARTED, (job_ids, due))
            if started[0]["started"] == len(job_ids):
                return
            await asyncio.sleep(0.02)


@asynccontextmanager
async def held_after_locks(
    monkeypatch: pytest.MonkeyPatch, module: object, name: str,
) -> AsyncIterator[tuple[asyncio.Event, asyncio.Event]]:
    """Pause the change's second planning, the one its locks protect, until released."""
    plan: Callable[..., Awaitable[Any]] = getattr(module, name)
    locked, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def pause_after_locked_read(*args: Any) -> Any:
        nonlocal calls
        result = await plan(*args)
        calls += 1
        if calls == 2:
            locked.set()
            await release.wait()
        return result

    monkeypatch.setattr(module, name, pause_after_locked_read)
    yield locked, release


@asynccontextmanager
async def scheduler_kept(source: TimescaleSource) -> AsyncIterator[int]:
    """The scheduler's pid; afterwards it must be the same process, waited for past a deadlock check."""
    pid = await scheduler(source)
    assert pid is not None, "the source's job scheduler is not running"
    try:
        yield pid
        timeout = await source.session().query(
            "SELECT EXTRACT(epoch FROM pg_catalog.current_setting('deadlock_timeout')::interval) AS seconds",
        )
        await asyncio.sleep(float(timeout[0]["seconds"]) * 2 + 0.5)
        assert await scheduler(source) == pid
    finally:
        if await scheduler(source) is None:
            # Restore the source for the rest of the matrix; most releases never restart it.
            await source.session().query("SELECT _timescaledb_functions.start_background_workers()")


async def run_paused(
    change: Awaitable[Any], locked: asyncio.Event, release: asyncio.Event,
    source: TimescaleSource, pid: int, job_ids: list[int],
) -> None:
    # Due a second from now, before the change starts: changing a job waits for the
    # change's locks, and the change has five seconds in all.
    due = await make_due(source, job_ids)
    task = asyncio.ensure_future(change)
    try:
        await asyncio.wait_for(locked.wait(), timeout=1)
        await taken_up(source, pid, job_ids, due)
        release.set()
        await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.fixture
async def table(source: TimescaleSource) -> AsyncIterator[PolicyTable]:
    async with disposable_hypertable(source, "scheduler", compressed=True) as target:
        yield target


async def test_removing_a_policy_whose_job_is_starting_keeps_the_scheduler(
    source: TimescaleSource, table: PolicyTable, monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = await quiet_policy(source, table, "add_retention_policy")
    plan = await plan_age_policy(source.session(), RETENTION, table.schema, table.table, None)
    assert plan.existing is not None and plan.existing.job_id == str(job_id)
    async with scheduler_kept(source) as pid, held_after_locks(
        monkeypatch, age_policy_execution, "plan_age_policy",
    ) as (locked, release):
        await run_paused(age_policy_execution.execute_age_policy(
            source.session(), RETENTION, table.schema, table.table, None, plan.fingerprint(),
        ), locked, release, source, pid, [job_id])
    assert await source.session().query("SELECT 1 FROM timescaledb_information.jobs WHERE job_id = %s", (job_id,)) == []


async def test_a_design_removing_two_starting_jobs_keeps_the_scheduler(
    source: TimescaleSource, table: PolicyTable, monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_ids = [
        await quiet_policy(source, table, "add_retention_policy"),
        await quiet_policy(source, table, "add_compression_policy"),
    ]
    design: HypertableDesign = (await current(source, table)).model_copy(
        update={"retention": None, "columnstore_policy": None},
    )
    action = editor(source)
    fingerprint = await reviewed(action, table.node_id, params(design))
    async with scheduler_kept(source) as pid, held_after_locks(
        monkeypatch, design_execution, "plan_design",
    ) as (locked, release):
        await run_paused(
            action.perform_reviewed(table.node_id, params(design), fingerprint),
            locked, release, source, pid, job_ids,
        )
    assert await source.session().query(
        "SELECT 1 FROM timescaledb_information.jobs WHERE job_id = ANY(%s::integer[])", (job_ids,),
    ) == []


async def test_a_new_policy_starts_at_once_and_is_removed_beside_its_run(
    source: TimescaleSource, table: PolicyTable,
) -> None:
    """The ordinary path the race came from: set a policy, then remove it straight away."""
    remover = registry(source).action(RemoveRetentionPolicy.name)
    setter = registry(source).action(SetRetentionPolicy.name)
    ten_years = {"amount": 10, "unit": "year"}
    async with scheduler_kept(source):
        for _ in range(3):
            await setter.perform_reviewed(table.node_id, ten_years, await reviewed(setter, table.node_id, ten_years))
            await remover.perform_reviewed(table.node_id, {}, await reviewed(remover, table.node_id, {}))
