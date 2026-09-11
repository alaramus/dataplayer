import asyncio
from unittest.mock import AsyncMock, MagicMock

import psycopg
import pytest

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale import compression_settings_execution
from app.adapters.postgres.timescale.plans import (
    CompressionSettingsPlan,
    CompressionSettingsStrategy,
    OrderColumn,
    TimeHypertable,
)
from app.adapters.protocol import AdapterError

PLAN = CompressionSettingsPlan(
    target=TimeHypertable(
        database_oid="42", relation_oid="123", schema_name='odd"schema', table_name="events",
        column_name="observed_at", column_type="timestamp with time zone",
    ),
    enabled=True, current_segment_by="device", current_order_by="observed_at DESC",
    segment_by=('de"vice',),
    order_by=(OrderColumn(column="observed_at", descending=True, nulls_first=True),),
    any_compressed=False, unsegmented_unique=(),
    strategy=CompressionSettingsStrategy(extension_version="2.18.0"),
)
LOCK = 'LOCK TABLE ONLY "odd""schema"."events" IN ACCESS EXCLUSIVE MODE'
ALTER = (
    'ALTER TABLE "odd""schema"."events" SET (timescaledb.compress, '
    "timescaledb.compress_segmentby = '\"de\"\"vice\"', "
    "timescaledb.compress_orderby = '\"observed_at\" DESC NULLS FIRST')"
)


def source_session() -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    connection = MagicMock()
    connection.execute = AsyncMock()
    session.acquire.return_value.__aenter__.return_value = connection
    return session, connection


async def run(session: MagicMock, fingerprint: str | None = None) -> CompressionSettingsPlan:
    return await compression_settings_execution.execute_compression_settings(
        session, "odd\"schema", "events", "de\"vice", "", PLAN.fingerprint() if fingerprint is None else fingerprint,
    )


async def test_the_sources_lock_is_taken_first_then_one_explicit_alter(monkeypatch: pytest.MonkeyPatch) -> None:
    session, connection = source_session()
    phases: list[int] = []

    async def replan(*args: object) -> CompressionSettingsPlan:
        assert args[1:] == ('odd"schema', "events", 'de"vice', "")
        phases.append(connection.execute.await_count)
        return PLAN

    monkeypatch.setattr(compression_settings_execution, "plan_compression_settings", replan)
    assert await run(session) == PLAN
    assert phases == [3, 4]
    calls = connection.execute.await_args_list
    assert calls[3].args[0].as_string() == LOCK
    assert calls[4].args[0].as_string() == ALTER
    assert len(calls[4].args) == 1
    assert len(calls) == 5
    connection.transaction.return_value.__aexit__.assert_awaited_once_with(None, None, None)


async def test_change_while_waiting_for_the_lock_refuses_before_alter(monkeypatch: pytest.MonkeyPatch) -> None:
    session, connection = source_session()
    changed = CompressionSettingsPlan.model_validate({**PLAN.model_dump(), "current_segment_by": "value"})
    monkeypatch.setattr(compression_settings_execution, "plan_compression_settings", AsyncMock(side_effect=[
        PLAN, changed,
    ]))
    with pytest.raises(ActionRefused, match="review it again"):
        await run(session)
    assert connection.execute.await_count == 4


async def test_busy_table_refuses_without_altering(monkeypatch: pytest.MonkeyPatch) -> None:
    session, connection = source_session()
    monkeypatch.setattr(compression_settings_execution, "plan_compression_settings", AsyncMock(return_value=PLAN))
    connection.execute.side_effect = [None, None, None, psycopg.errors.LockNotAvailable("secret")]
    with pytest.raises(ActionRefused, match="busy"):
        await run(session)
    assert connection.execute.await_count == 4


@pytest.mark.parametrize("error,expected", [
    (psycopg.errors.UndefinedFunction("secret"), ActionRefused),
    (psycopg.errors.UndefinedColumn("secret"), ActionRefused),
    (psycopg.errors.InsufficientPrivilege("secret"), ActionRefused),
    (psycopg.OperationalError("secret"), AdapterError),
    (TimeoutError("secret"), AdapterError),
    (asyncio.CancelledError(), asyncio.CancelledError),
])
async def test_failed_alter_rolls_back_without_retry(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, expected: type[BaseException],
) -> None:
    session, connection = source_session()
    monkeypatch.setattr(compression_settings_execution, "plan_compression_settings", AsyncMock(return_value=PLAN))
    connection.execute.side_effect = [None] * 4 + [error]
    with pytest.raises(expected) as caught:
        await run(session)
    assert "secret" not in str(caught.value)
    assert connection.execute.await_count == 5
    assert connection.transaction.return_value.__aexit__.await_args.args[0] is not None
