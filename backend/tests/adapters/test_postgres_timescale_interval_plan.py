from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.features import SourceFeature
from app.adapters.postgres.timescale import interval_plan
from app.adapters.postgres.timescale.api import ExtensionRoutine
from app.adapters.postgres.timescale.plans import TimeDuration
from app.adapters.postgres.timescale.profile import TimescaleProfile
from app.adapters.protocol import AdapterError

TARGET = {
    "database_oid": "42", "relation_oid": "123", "schema_name": "lab",
    "table_name": "events", "dimension_number": 1, "column_name": "time",
    "column_type": "timestamp with time zone", "current_interval": "7 days",
}
@dataclass
class Sources:
    discover: AsyncMock
    routine: AsyncMock
    view_lock: AsyncMock


@pytest.fixture
def discovery(monkeypatch: pytest.MonkeyPatch) -> Sources:
    mocks = Sources(
        discover=AsyncMock(return_value=TimescaleProfile(SourceFeature(
            code="timescaledb", title="TimescaleDB", state="available", installed_version="2.18.0",
        ))),
        routine=AsyncMock(return_value=ExtensionRoutine(oid="456", schema_name="public")),
        view_lock=AsyncMock(return_value="789"),
    )
    monkeypatch.setattr(interval_plan, "discover", mocks.discover)
    monkeypatch.setattr(interval_plan, "require_public_view", AsyncMock())
    monkeypatch.setattr(interval_plan, "extension_routine", mocks.routine)
    monkeypatch.setattr(interval_plan, "lockable_view", mocks.view_lock)
    return mocks


async def test_interval_plan_only_reads_and_binds_target_names(discovery: Sources) -> None:
    session = AsyncMock()
    session.query.return_value = [TARGET]
    schema, table = 'odd"schema', "events'; DROP TABLE x; --"
    result = await interval_plan.plan_chunk_interval(
        session, schema, table, TimeDuration(amount=2, unit="day"),
    )
    assert result.target.relation_oid == "123"
    assert result.interval.interval_value() == "2 day"
    assert (result.strategy.function_oid, result.strategy.dimensions_view_oid) == ("456", "789")
    target_read = session.query.await_args
    assert target_read.args[1] == (schema, table)
    assert schema not in target_read.args[0] and table not in target_read.args[0]
    assert all(call.kwargs == {"inspection": True} for call in session.query.await_args_list)
    discovery.routine.assert_awaited_once_with(session, "2.18.0", interval_plan.SET_INTERVAL)
    discovery.view_lock.assert_awaited_once_with(session, "2.18.0", "dimensions")
    session.schema_change.assert_not_called()
    session.transaction.assert_not_called()
    session.rehearse.assert_not_called()
    discovery.discover.assert_awaited_once_with(session)


@pytest.mark.parametrize("rows", [[], [TARGET, TARGET], [{**TARGET, "column_type": "bigint"}]])
@pytest.mark.usefixtures("discovery")
async def test_missing_ambiguous_or_integer_dimension_refuses_before_api_read(
    rows: list[dict[str, object]],
) -> None:
    session = AsyncMock()
    session.query.return_value = rows
    with pytest.raises(ActionRefused):
        await interval_plan.plan_chunk_interval(session, "lab", "events", TimeDuration(amount=1, unit="day"))
    assert session.query.await_count == 1


@pytest.mark.parametrize("failure", ["routine", "view_lock"])
async def test_missing_setter_or_lock_permission_refuses(discovery: Sources, failure: str) -> None:
    getattr(discovery, failure).side_effect = ActionRefused(
        "not_applicable", "The TimescaleDB API is not usable by this connection",
    )
    session = AsyncMock()
    session.query.return_value = [TARGET]
    with pytest.raises(ActionRefused, match="not usable by this connection"):
        await interval_plan.plan_chunk_interval(session, "lab", "events", TimeDuration(amount=1, unit="day"))


async def test_unavailable_extension_refuses_before_target_reads(discovery: Sources) -> None:
    discovery.discover.return_value = TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state="unsupported", installed_version="2.19.0",
        reason="The installed version lacks the supported inspection API",
    ))
    session = AsyncMock()
    with pytest.raises(ActionRefused, match="lacks the supported inspection API"):
        await interval_plan.plan_chunk_interval(session, "lab", "events", TimeDuration(amount=1, unit="day"))
    session.query.assert_not_called()


@pytest.mark.parametrize("error", [AdapterError("unknown", "secret password"), ValueError("secret password"), TimeoutError()])
@pytest.mark.usefixtures("discovery")
async def test_inspection_failure_is_safe(error: Exception) -> None:
    session = AsyncMock()
    session.query.side_effect = error
    with pytest.raises(ActionRefused) as caught:
        await interval_plan.plan_chunk_interval(session, "lab", "events", TimeDuration(amount=1, unit="day"))
    assert "secret" not in caught.value.message


async def test_calendar_duration_refuses_before_discovery(discovery: Sources) -> None:
    with pytest.raises(ActionRefused, match="Calendar"):
        await interval_plan.plan_chunk_interval(AsyncMock(), "lab", "events", TimeDuration(amount=1, unit="month"))
    discovery.discover.assert_not_called()


@pytest.mark.usefixtures("discovery")
async def test_date_dimension_refuses_subday_interval() -> None:
    session = AsyncMock()
    session.query.return_value = [{**TARGET, "column_type": "date"}]
    with pytest.raises(ActionRefused, match="whole days"):
        await interval_plan.plan_chunk_interval(session, "lab", "events", TimeDuration(amount=1, unit="hour"))
    assert session.query.await_count == 1
