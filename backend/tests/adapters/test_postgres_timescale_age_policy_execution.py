import asyncio
from unittest.mock import AsyncMock, MagicMock

import psycopg
import pytest

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale import age_policy_execution
from app.adapters.postgres.timescale.age_policy_plan import (
    COMPRESSION,
    RETENTION,
    AgePolicySpec,
)
from app.adapters.postgres.timescale.plans import (
    AgePolicy,
    AgePolicyPlan,
    AgePolicyStrategy,
    TimeDuration,
    TimeHypertable,
)
from app.adapters.protocol import AdapterError

EXISTING = AgePolicy(job_id="1000", scheduled=True, schedule_interval="1 day", older_than="10 years")
TWENTY_YEARS = TimeDuration(amount=20, unit="year")
SPECS = [pytest.param(RETENTION, id="retention"), pytest.param(COMPRESSION, id="compression")]


def make_plan(
    spec: AgePolicySpec = RETENTION, *, existing: AgePolicy | None = EXISTING,
    older_than: TimeDuration | None = TWENTY_YEARS,
) -> AgePolicyPlan:
    return AgePolicyPlan(
        operation="set_policy" if older_than is not None else "remove_policy", kind=spec.kind,
        target=TimeHypertable(
            database_oid="42", relation_oid="123", schema_name='odd"schema', table_name="events",
            column_name="time", column_type="timestamp with time zone",
        ),
        existing=existing, older_than=older_than,
        strategy=AgePolicyStrategy.model_validate({
            "kind": spec.kind, "extension_version": "2.18.0", "function_schema": 'ext"schema',
            "add_function_oid": "456", "remove_function_oid": "457", "jobs_view_oid": "789",
        }),
    )


def removal(spec: AgePolicySpec) -> str:
    return f'SELECT "ext""schema"."{spec.remove.name}"(%s::pg_catalog.regclass, false)'


def addition(spec: AgePolicySpec) -> str:
    routine = spec.add.name
    return f'SELECT "ext""schema"."{routine}"(%s::pg_catalog.regclass, %s::pg_catalog.interval, false)'


def source_session() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    connection = MagicMock()
    connection.execute = AsyncMock()
    session.acquire.return_value.__aenter__.return_value = connection
    return session, connection


async def run(
    session: MagicMock, spec: AgePolicySpec, plan: AgePolicyPlan, fingerprint: str | None = None,
) -> AgePolicyPlan:
    return await age_policy_execution.execute_age_policy(
        session, spec, plan.target.schema_name, plan.target.table_name, plan.older_than,
        plan.fingerprint() if fingerprint is None else fingerprint,
    )


@pytest.mark.parametrize("spec", SPECS)
async def test_replacement_replans_under_locks_then_removes_and_adds_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch, spec: AgePolicySpec,
) -> None:
    plan = make_plan(spec)
    session, connection = source_session()
    phases: list[int] = []

    async def replan(*args: object) -> AgePolicyPlan:
        assert args[1] is spec
        phases.append(connection.execute.await_count)
        return plan

    monkeypatch.setattr(age_policy_execution, "plan_age_policy", replan)
    assert await run(session, spec, plan) == plan
    assert phases == [3, 5]
    calls = connection.execute.await_args_list
    assert calls[0].args[0] == "SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE"
    assert calls[1].args[0] == "SET LOCAL lock_timeout = '2s'"
    assert calls[3].args[0].as_string() == (
        'LOCK TABLE ONLY "timescaledb_information"."jobs" IN SHARE ROW EXCLUSIVE MODE'
    )
    assert calls[4].args[0].as_string() == (
        'LOCK TABLE ONLY "odd""schema"."events" IN SHARE UPDATE EXCLUSIVE MODE'
    )
    assert (calls[5].args[0].as_string(), calls[5].args[1]) == (removal(spec), ("123",))
    assert (calls[6].args[0].as_string(), calls[6].args[1]) == (addition(spec), ("123", "20 year"))
    assert len(calls) == 7
    connection.transaction.return_value.__aexit__.assert_awaited_once_with(None, None, None)


@pytest.mark.parametrize("spec", SPECS)
@pytest.mark.parametrize("first", [True, False])
async def test_first_policy_only_adds_and_removal_only_removes(
    monkeypatch: pytest.MonkeyPatch, spec: AgePolicySpec, first: bool,
) -> None:
    plan = make_plan(spec, existing=None) if first else make_plan(spec, older_than=None)
    session, connection = source_session()
    monkeypatch.setattr(age_policy_execution, "plan_age_policy", AsyncMock(return_value=plan))
    await run(session, spec, plan)
    calls = connection.execute.await_args_list
    assert len(calls) == 6
    assert calls[5].args[0].as_string() == (addition(spec) if first else removal(spec))


@pytest.mark.parametrize("section,field,value", [
    ("target", "relation_oid", "124"), ("existing", "job_id", "1001"),
    ("existing", "schedule_interval", "2 days"), ("strategy", "remove_function_oid", "458"),
    ("strategy", "jobs_view_oid", "790"),
])
async def test_change_while_acquiring_locks_refuses_before_mutation(
    monkeypatch: pytest.MonkeyPatch, section: str, field: str, value: str,
) -> None:
    plan = make_plan()
    session, connection = source_session()
    changed = plan.model_dump()
    changed[section][field] = value
    monkeypatch.setattr(age_policy_execution, "plan_age_policy", AsyncMock(side_effect=[
        plan, AgePolicyPlan.model_validate(changed),
    ]))
    with pytest.raises(ActionRefused, match="review it again"):
        await run(session, RETENTION, plan)
    assert connection.execute.await_count == 5
    assert connection.transaction.return_value.__aexit__.await_args.args[0] is ActionRefused


async def test_bad_review_refuses_before_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = make_plan()
    session, connection = source_session()
    monkeypatch.setattr(age_policy_execution, "plan_age_policy", AsyncMock(return_value=plan))
    with pytest.raises(ActionRefused):
        await run(session, RETENTION, plan, "bad")
    assert connection.execute.await_count == 3


async def test_lock_timeout_before_mutation_asks_for_new_review(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = make_plan()
    session, connection = source_session()
    monkeypatch.setattr(age_policy_execution, "plan_age_policy", AsyncMock(return_value=plan))
    connection.execute.side_effect = [None, None, None, TimeoutError()]
    with pytest.raises(ActionRefused, match="timed out"):
        await run(session, RETENTION, plan)


@pytest.mark.parametrize("failing_call", [6, 7])
@pytest.mark.parametrize("error,expected", [
    (psycopg.errors.InsufficientPrivilege("secret"), ActionRefused),
    (psycopg.errors.LockNotAvailable("secret"), ActionRefused),
    (psycopg.errors.UndefinedObject("secret"), ActionRefused),
    (psycopg.errors.FeatureNotSupported("secret"), ActionRefused),
    (psycopg.errors.DatetimeFieldOverflow("secret"), ActionRefused),
    (psycopg.OperationalError("secret"), AdapterError),
    (TimeoutError("secret"), AdapterError),
    (asyncio.CancelledError(), asyncio.CancelledError),
])
async def test_failure_after_dispatch_rolls_back_without_retry(
    monkeypatch: pytest.MonkeyPatch, failing_call: int,
    error: BaseException, expected: type[BaseException],
) -> None:
    plan = make_plan()
    session, connection = source_session()
    monkeypatch.setattr(age_policy_execution, "plan_age_policy", AsyncMock(return_value=plan))
    connection.execute.side_effect = [None] * (failing_call - 1) + [error]
    with pytest.raises(expected) as caught:
        await run(session, RETENTION, plan)
    assert "secret" not in str(caught.value)
    assert connection.execute.await_count == failing_call
    # A refused addition leaves the transaction that removed the old policy.
    assert connection.transaction.return_value.__aexit__.await_args.args[0] is not None
    session.acquire.return_value.__aexit__.assert_awaited_once()
