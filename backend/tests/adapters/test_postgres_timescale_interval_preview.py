from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.postgres.timescale import interval_preview
from app.adapters.postgres.timescale.plans import (
    ChunkIntervalPlan,
    IntervalStrategy,
    IntervalTarget,
    TimeDuration,
)
from app.adapters.protocol import AdapterError


@pytest.fixture
def plan() -> ChunkIntervalPlan:
    return ChunkIntervalPlan(
        target=IntervalTarget(
            database_oid="42", relation_oid="123", schema_name='odd"schema',
            table_name="events", dimension_number=1, column_name="time",
            column_type="timestamp with time zone", current_interval="7 days",
        ),
        interval=TimeDuration(amount=2, unit="day"),
        strategy=IntervalStrategy(
            extension_version="2.18.0", function_oid="456", function_schema="public",
        ),
    )


async def test_preview_uses_snapshot_and_returns_reviewed_impact(
    monkeypatch: pytest.MonkeyPatch, plan: ChunkIntervalPlan,
) -> None:
    planner = AsyncMock(return_value=plan)
    monkeypatch.setattr(interval_preview, "plan_chunk_interval", planner)
    session = MagicMock()
    reader = session.inspection.return_value.__aenter__.return_value
    result = await interval_preview.preview_chunk_interval(
        session, plan.target.schema_name, plan.target.table_name, plan.interval,
    )
    planner.assert_awaited_once_with(reader, 'odd"schema', "events", plan.interval)
    assert result.summary == 'Change the future chunk interval for "odd""schema"."events"'
    assert result.items == [
        'Time dimension: "time"', "Current interval: 7 days", "Requested interval: 2 day",
        "Only future chunks use the new interval; existing chunks are not repartitioned",
    ]
    assert result.fingerprint == plan.fingerprint()
    assert not result.blocked
    session.inspection.return_value.__aexit__.assert_awaited_once()
    session.rehearse.assert_not_called()
    session.change.assert_not_called()


@pytest.mark.parametrize("error", [
    ActionRefused("not_applicable", "Choose an owned hypertable"),
    AdapterError("unknown", "secret password"), ValueError("secret password"), TimeoutError(),
])
async def test_failed_plan_has_no_review_fingerprint(
    monkeypatch: pytest.MonkeyPatch, plan: ChunkIntervalPlan, error: Exception,
) -> None:
    monkeypatch.setattr(interval_preview, "plan_chunk_interval", AsyncMock(side_effect=error))
    result = await interval_preview.preview_chunk_interval(
        MagicMock(), "lab", "events", plan.interval,
    )
    assert result.blocked
    assert result.fingerprint is None
    assert result.items == []
    assert "secret" not in result.summary
    if isinstance(error, ActionRefused):
        assert result.summary == error.message


async def test_snapshot_acquisition_failure_is_a_blocked_preview(plan: ChunkIntervalPlan) -> None:
    session = MagicMock()
    session.inspection.return_value.__aenter__.side_effect = AdapterError("network", "secret")
    result = await interval_preview.preview_chunk_interval(session, "lab", "events", plan.interval)
    assert result.blocked
    assert result.fingerprint is None
    assert "secret" not in result.summary
