import asyncio
from unittest.mock import AsyncMock, MagicMock

import psycopg
import pytest

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale import conversion_execution
from app.adapters.postgres.timescale.plans import (
    ConversionColumn,
    ConversionPlan,
    ConversionStrategy,
    ConversionTarget,
    TimeDuration,
)
from app.adapters.protocol import AdapterError

PLAN = ConversionPlan(
    target=ConversionTarget(database_oid="42", relation_oid="123", schema_name='odd"schema', table_name="events"),
    column=ConversionColumn(name="observed_at", type="timestamp with time zone", not_null=False),
    interval=TimeDuration(amount=7, unit="day"), time_index_exists=False,
    strategy=ConversionStrategy(
        extension_version="2.18.0", function_schema='ext"schema', create_function_oid="456",
        by_range_function_oid="457", dimension_info_oid="99999",
    ),
)
LOCK = 'LOCK TABLE ONLY "odd""schema"."events" IN ACCESS EXCLUSIVE MODE'
CREATE = (
    'SELECT hypertable_id FROM "ext""schema"."create_hypertable"(%s::pg_catalog.regclass, '
    '"ext""schema"."by_range"(%s::pg_catalog.name, %s::pg_catalog.interval), true, false, false)'
)


def source_session() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    connection = MagicMock()
    connection.execute = AsyncMock()
    session.acquire.return_value.__aenter__.return_value = connection
    return session, connection


async def run(session: MagicMock, fingerprint: str | None = None) -> ConversionPlan:
    return await conversion_execution.execute_conversion(
        session, 'odd"schema', "events", "observed_at", PLAN.interval,
        PLAN.fingerprint() if fingerprint is None else fingerprint,
    )


async def test_the_table_is_locked_before_emptiness_is_replanned_and_converted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, connection = source_session()
    phases: list[int] = []

    async def replan(*args: object) -> ConversionPlan:
        assert args[1:] == ('odd"schema', "events", "observed_at", PLAN.interval)
        phases.append(connection.execute.await_count)
        return PLAN

    monkeypatch.setattr(conversion_execution, "plan_conversion", replan)
    assert await run(session) == PLAN
    assert phases == [3, 4]
    calls = connection.execute.await_args_list
    assert calls[3].args[0].as_string() == LOCK
    assert (calls[4].args[0].as_string(), calls[4].args[1]) == (CREATE, ("123", "observed_at", "7 day"))
    assert len(calls) == 5
    connection.transaction.return_value.__aexit__.assert_awaited_once_with(None, None, None)


async def test_rows_arriving_after_review_refuse_under_the_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    session, connection = source_session()
    monkeypatch.setattr(conversion_execution, "plan_conversion", AsyncMock(side_effect=[
        PLAN, ActionRefused("not_applicable", "This table is not empty; only empty tables are converted here"),
    ]))
    with pytest.raises(ActionRefused, match="not empty"):
        await run(session)
    assert connection.execute.await_count == 4


async def test_change_while_waiting_for_the_lock_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    session, connection = source_session()
    changed = ConversionPlan.model_validate({**PLAN.model_dump(), "time_index_exists": True})
    monkeypatch.setattr(conversion_execution, "plan_conversion", AsyncMock(side_effect=[PLAN, changed]))
    with pytest.raises(ActionRefused, match="review it again"):
        await run(session)
    assert connection.execute.await_count == 4


@pytest.mark.parametrize("error,expected", [
    (psycopg.errors.FeatureNotSupported("secret"), ActionRefused),
    (psycopg.errors.InsufficientPrivilege("secret"), ActionRefused),
    (psycopg.errors.LockNotAvailable("secret"), ActionRefused),
    (psycopg.OperationalError("secret"), AdapterError),
    (asyncio.CancelledError(), asyncio.CancelledError),
])
async def test_refused_conversion_rolls_back_without_retry(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, expected: type[BaseException],
) -> None:
    session, connection = source_session()
    monkeypatch.setattr(conversion_execution, "plan_conversion", AsyncMock(return_value=PLAN))
    connection.execute.side_effect = [None] * 4 + [error]
    with pytest.raises(expected) as caught:
        await run(session)
    assert "secret" not in str(caught.value)
    assert connection.execute.await_count == 5
    assert connection.transaction.return_value.__aexit__.await_args.args[0] is not None
