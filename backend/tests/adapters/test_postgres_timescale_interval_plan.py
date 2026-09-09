from unittest.mock import AsyncMock

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.features import SourceFeature
from app.adapters.postgres.timescale import interval_plan
from app.adapters.postgres.timescale.plans import TimeDuration
from app.adapters.postgres.timescale.profile import TimescaleProfile
from app.adapters.protocol import AdapterError

TARGET = {
    "database_oid": "42", "relation_oid": "123", "schema_name": "lab",
    "table_name": "events", "dimension_number": 1, "column_name": "time",
    "column_type": "timestamp with time zone", "current_interval": "7 days",
}
API = {
    "extension_version": "2.18.0", "function_oid": "456", "function_schema": "public",
    "dimensions_view_oid": "789",
}


@pytest.fixture
def discovery(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    probe = AsyncMock(return_value=TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state="available", installed_version="2.18.0",
    )))
    monkeypatch.setattr(interval_plan, "discover", probe)
    monkeypatch.setattr(interval_plan, "require_public_view", AsyncMock())
    return probe


async def test_interval_plan_only_reads_and_binds_target_names(discovery: AsyncMock) -> None:
    session = AsyncMock()
    session.query.side_effect = [[TARGET], [API]]
    schema, table = 'odd"schema', "events'; DROP TABLE x; --"
    result = await interval_plan.plan_chunk_interval(
        session, schema, table, TimeDuration(amount=2, unit="day"),
    )
    assert result.target.relation_oid == "123"
    assert result.interval.interval_value() == "2 day"
    target_read, api_read = session.query.await_args_list
    assert target_read.args[1] == (schema, table)
    assert schema not in target_read.args[0] and table not in target_read.args[0]
    assert api_read.args[1] == ("2.18.0",)
    assert all(call.kwargs == {"inspection": True} for call in session.query.await_args_list)
    session.schema_change.assert_not_called()
    session.transaction.assert_not_called()
    session.rehearse.assert_not_called()
    discovery.assert_awaited_once_with(session)


@pytest.mark.parametrize("rows", [[], [TARGET, TARGET], [{**TARGET, "column_type": "bigint"}]])
async def test_missing_ambiguous_or_integer_dimension_refuses_before_api_read(
    discovery: AsyncMock, rows: list[dict[str, object]],
) -> None:
    session = AsyncMock()
    session.query.return_value = rows
    with pytest.raises(ActionRefused):
        await interval_plan.plan_chunk_interval(session, "lab", "events", TimeDuration(amount=1, unit="day"))
    assert session.query.await_count == 1


@pytest.mark.parametrize("functions", [
    [], [API, API], [{**API, "extension_version": "2.19.0"}],
    [{**API, "extension_version": "2.17.2"}],
])
async def test_missing_ambiguous_or_changed_api_refuses(
    discovery: AsyncMock, functions: list[dict[str, object]],
) -> None:
    session = AsyncMock()
    session.query.side_effect = [[TARGET], functions]
    with pytest.raises(ActionRefused):
        await interval_plan.plan_chunk_interval(session, "lab", "events", TimeDuration(amount=1, unit="day"))


async def test_unknown_version_refuses_before_target_reads(discovery: AsyncMock) -> None:
    discovery.return_value = TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state="available", installed_version="2.19.0",
    ))
    session = AsyncMock()
    with pytest.raises(ActionRefused, match="No supported"):
        await interval_plan.plan_chunk_interval(session, "lab", "events", TimeDuration(amount=1, unit="day"))
    session.query.assert_not_called()


@pytest.mark.parametrize("error", [AdapterError("unknown", "secret password"), ValueError("secret password"), TimeoutError()])
async def test_inspection_failure_is_safe(discovery: AsyncMock, error: Exception) -> None:
    session = AsyncMock()
    session.query.side_effect = error
    with pytest.raises(ActionRefused) as caught:
        await interval_plan.plan_chunk_interval(session, "lab", "events", TimeDuration(amount=1, unit="day"))
    assert "secret" not in caught.value.message


async def test_calendar_duration_refuses_before_discovery(discovery: AsyncMock) -> None:
    with pytest.raises(ActionRefused, match="Calendar"):
        await interval_plan.plan_chunk_interval(AsyncMock(), "lab", "events", TimeDuration(amount=1, unit="month"))
    discovery.assert_not_called()


async def test_date_dimension_refuses_subday_interval(discovery: AsyncMock) -> None:
    session = AsyncMock()
    session.query.return_value = [{**TARGET, "column_type": "date"}]
    with pytest.raises(ActionRefused, match="whole days"):
        await interval_plan.plan_chunk_interval(session, "lab", "events", TimeDuration(amount=1, unit="hour"))
    assert session.query.await_count == 1
