import asyncio
from unittest.mock import AsyncMock, MagicMock

import psycopg
import pytest

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale import interval_execution
from app.adapters.postgres.timescale.plans import ChunkIntervalPlan, IntervalStrategy, IntervalTarget, TimeDuration
from app.adapters.protocol import AdapterError


@pytest.fixture
def plan() -> ChunkIntervalPlan:
    return ChunkIntervalPlan(
        target=IntervalTarget(
            database_oid="42", relation_oid="123", schema_name='odd"schema', table_name="events",
            dimension_number=1, column_name="time", column_type="timestamp with time zone",
            current_interval="7 days",
        ),
        interval=TimeDuration(amount=2, unit="day"),
        strategy=IntervalStrategy(
            extension_version="2.18.0", function_oid="456", function_schema='ext"schema',
            dimensions_view_oid="789",
        ),
    )


def source_session() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    connection = MagicMock()
    connection.execute = AsyncMock()
    session.acquire.return_value.__aenter__.return_value = connection
    return session, connection


async def test_execution_replans_after_locks_and_binds_native_call(
    monkeypatch: pytest.MonkeyPatch, plan: ChunkIntervalPlan,
) -> None:
    session, connection = source_session()
    phases: list[int] = []

    async def replan(*_args: object) -> ChunkIntervalPlan:
        phases.append(connection.execute.await_count)
        return plan

    monkeypatch.setattr(interval_execution, "plan_chunk_interval", replan)
    result = await interval_execution.execute_chunk_interval(
        session, plan.target.schema_name, plan.target.table_name, plan.interval, plan.fingerprint(),
    )
    assert result == plan
    assert phases == [3, 5]
    calls = connection.execute.await_args_list
    assert calls[0].args[0] == "SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE"
    assert calls[1].args[0] == "SET LOCAL lock_timeout = '2s'"
    assert calls[3].args[0] == interval_execution._METADATA_LOCK
    assert calls[4].args[0].as_string() == (
        'LOCK TABLE ONLY "odd""schema"."events" IN SHARE UPDATE EXCLUSIVE MODE'
    )
    assert calls[5].args[0].as_string() == (
        'SELECT "ext""schema"."set_chunk_time_interval"'
        '(%s::pg_catalog.regclass, %s::pg_catalog.interval, %s::pg_catalog.name)'
    )
    assert calls[5].args[1] == ("123", "2 day", "time")
    connection.transaction.return_value.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.parametrize("section,field,value", [
    ("target", "relation_oid", "124"), ("target", "current_interval", "3 days"),
    ("strategy", "function_oid", "457"), ("strategy", "dimensions_view_oid", "790"),
])
async def test_change_while_acquiring_locks_refuses_before_mutation(
    monkeypatch: pytest.MonkeyPatch, plan: ChunkIntervalPlan,
    section: str, field: str, value: str,
) -> None:
    session, connection = source_session()
    changed = plan.model_dump()
    changed[section][field] = value
    monkeypatch.setattr(interval_execution, "plan_chunk_interval", AsyncMock(side_effect=[
        plan, ChunkIntervalPlan.model_validate(changed),
    ]))
    with pytest.raises(ActionRefused, match="review it again"):
        await interval_execution.execute_chunk_interval(
            session, "lab", "events", plan.interval, plan.fingerprint(),
        )
    assert connection.execute.await_count == 5
    assert connection.transaction.return_value.__aexit__.await_args.args[0] is ActionRefused


async def test_bad_review_refuses_before_locks(monkeypatch: pytest.MonkeyPatch, plan: ChunkIntervalPlan) -> None:
    session, connection = source_session()
    monkeypatch.setattr(interval_execution, "plan_chunk_interval", AsyncMock(return_value=plan))
    with pytest.raises(ActionRefused):
        await interval_execution.execute_chunk_interval(session, "lab", "events", plan.interval, "bad")
    assert connection.execute.await_count == 3


@pytest.mark.parametrize("error,expected", [
    (psycopg.errors.InsufficientPrivilege("secret"), ActionRefused),
    (psycopg.errors.LockNotAvailable("secret"), ActionRefused),
    (psycopg.errors.InvalidParameterValue("secret"), ActionRefused),
    (psycopg.OperationalError("secret"), AdapterError),
    (TimeoutError("secret"), AdapterError),
    (asyncio.CancelledError(), asyncio.CancelledError),
])
async def test_failure_exits_transaction_without_retry(
    monkeypatch: pytest.MonkeyPatch, plan: ChunkIntervalPlan,
    error: BaseException, expected: type[BaseException],
) -> None:
    session, connection = source_session()
    monkeypatch.setattr(interval_execution, "plan_chunk_interval", AsyncMock(return_value=plan))
    connection.execute.side_effect = [None, None, None, None, None, error]
    with pytest.raises(expected) as caught:
        await interval_execution.execute_chunk_interval(
            session, "lab", "events", plan.interval, plan.fingerprint(),
        )
    assert "secret" not in str(caught.value)
    assert connection.execute.await_count == 6
    connection.transaction.return_value.__aexit__.assert_awaited_once()
    session.acquire.return_value.__aexit__.assert_awaited_once()
