import asyncio
from unittest.mock import AsyncMock, MagicMock

import psycopg
import pytest

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale import refresh_execution
from app.adapters.postgres.timescale.plans import (
    ContinuousAggregateTarget,
    RefreshPlan,
    RefreshPolicy,
    RefreshStrategy,
    RefreshWindow,
    TimeDuration,
)
from app.adapters.protocol import AdapterError

EXISTING = RefreshPolicy(
    job_id="1000", scheduled=True, schedule_interval="01:00:00", start_offset="30 days", end_offset="01:00:00",
)
WINDOW = RefreshWindow(
    start_offset=TimeDuration(amount=7, unit="day"), end_offset=TimeDuration(amount=1, unit="hour"),
    schedule_interval=TimeDuration(amount=30, unit="minute"),
)
REMOVE = (
    'SELECT "ext""schema"."remove_continuous_aggregate_policy"'
    "(%s::pg_catalog.regclass, false, false)"
)
ADD = (
    'SELECT "ext""schema"."add_continuous_aggregate_policy"(%s::pg_catalog.regclass, '
    "%s::pg_catalog.interval, %s::pg_catalog.interval, %s::pg_catalog.interval, false)"
)


def make_plan(*, existing: RefreshPolicy | None = EXISTING, window: RefreshWindow | None = WINDOW) -> RefreshPlan:
    return RefreshPlan(
        operation="set_policy" if window is not None else "remove_policy",
        target=ContinuousAggregateTarget(
            database_oid="42", view_oid="321", view_schema='odd"schema', view_name="hourly",
            materialization_oid="654", materialization_schema="_timescaledb_internal",
            materialization_name="_materialized_hypertable_3", source_schema="lab", source_name="metrics",
            column_type="timestamp with time zone",
        ),
        existing=existing, window=window, source_retention=None,
        strategy=RefreshStrategy(
            extension_version="2.18.0", function_schema='ext"schema', add_function_oid="456",
            remove_function_oid="457", jobs_view_oid="789",
        ),
    )


def source_session() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    connection = MagicMock()
    connection.execute = AsyncMock()
    session.acquire.return_value.__aenter__.return_value = connection
    return session, connection


async def run(session: MagicMock, plan: RefreshPlan, fingerprint: str | None = None) -> RefreshPlan:
    return await refresh_execution.execute_refresh(
        session, plan.target.view_schema, plan.target.view_name, plan.window,
        plan.fingerprint() if fingerprint is None else fingerprint,
    )


async def test_replacement_locks_the_materialization_and_replaces_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = make_plan()
    session, connection = source_session()
    phases: list[int] = []

    async def replan(*_args: object) -> RefreshPlan:
        phases.append(connection.execute.await_count)
        return plan

    monkeypatch.setattr(refresh_execution, "plan_refresh", replan)
    assert await run(session, plan) == plan
    assert phases == [3, 5]
    calls = connection.execute.await_args_list
    assert calls[3].args[0].as_string() == (
        'LOCK TABLE ONLY "timescaledb_information"."jobs" IN SHARE ROW EXCLUSIVE MODE'
    )
    assert calls[4].args[0].as_string() == (
        'LOCK TABLE ONLY "_timescaledb_internal"."_materialized_hypertable_3" IN SHARE UPDATE EXCLUSIVE MODE'
    )
    assert (calls[5].args[0].as_string(), calls[5].args[1]) == (REMOVE, ("321",))
    assert (calls[6].args[0].as_string(), calls[6].args[1]) == (ADD, ("321", "7 day", "1 hour", "30 minute"))
    assert len(calls) == 7
    connection.transaction.return_value.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.parametrize("first", [True, False])
async def test_first_policy_only_adds_and_removal_only_removes(
    monkeypatch: pytest.MonkeyPatch, first: bool,
) -> None:
    plan = make_plan(existing=None) if first else make_plan(window=None)
    session, connection = source_session()
    monkeypatch.setattr(refresh_execution, "plan_refresh", AsyncMock(return_value=plan))
    await run(session, plan)
    calls = connection.execute.await_args_list
    assert len(calls) == 6
    assert calls[5].args[0].as_string() == (ADD if first else REMOVE)


@pytest.mark.parametrize("section,field,value", [
    ("target", "view_oid", "322"), ("existing", "job_id", "1001"),
    ("strategy", "jobs_view_oid", "790"),
])
async def test_change_while_acquiring_locks_refuses_before_mutation(
    monkeypatch: pytest.MonkeyPatch, section: str, field: str, value: str,
) -> None:
    plan = make_plan()
    session, connection = source_session()
    changed = plan.model_dump()
    changed[section][field] = value
    monkeypatch.setattr(refresh_execution, "plan_refresh", AsyncMock(side_effect=[
        plan, RefreshPlan.model_validate(changed),
    ]))
    with pytest.raises(ActionRefused, match="review it again"):
        await run(session, plan)
    assert connection.execute.await_count == 5


@pytest.mark.parametrize("error,expected", [
    (psycopg.errors.InvalidParameterValue("secret"), ActionRefused),
    (psycopg.errors.LockNotAvailable("secret"), ActionRefused),
    (psycopg.OperationalError("secret"), AdapterError),
    (asyncio.CancelledError(), asyncio.CancelledError),
])
async def test_refused_addition_rolls_the_removal_back(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, expected: type[BaseException],
) -> None:
    plan = make_plan()
    session, connection = source_session()
    monkeypatch.setattr(refresh_execution, "plan_refresh", AsyncMock(return_value=plan))
    connection.execute.side_effect = [None] * 6 + [error]
    with pytest.raises(expected) as caught:
        await run(session, plan)
    assert "secret" not in str(caught.value)
    assert connection.execute.await_count == 7
    assert connection.transaction.return_value.__aexit__.await_args.args[0] is not None
