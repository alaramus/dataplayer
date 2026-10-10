from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.adapters.actions import ActionRefused
from app.adapters.features import SourceFeature
from app.adapters.postgres.timescale import refresh_plan
from app.adapters.postgres.timescale.age_policy_plan import RETENTION
from app.adapters.postgres.timescale.api import ExtensionRoutine, RoutineShape
from app.adapters.postgres.timescale.plans import (
    AgePolicy,
    ContinuousAggregateTarget,
    RefreshPlan,
    RefreshPolicy,
    RefreshStrategy,
    RefreshWindow,
    TimeDuration,
)
from app.adapters.postgres.timescale.profile import TimescaleProfile
from app.adapters.postgres.timescale.refresh_plan import RefreshState
from app.adapters.protocol import AdapterError

TARGET = ContinuousAggregateTarget(
    database_oid="42", view_oid="321", view_schema="lab", view_name="hourly",
    materialization_oid="654", materialization_schema="_timescaledb_internal",
    materialization_name="_materialized_hypertable_3", source_schema="lab", source_name="metrics",
    column_type="timestamp with time zone",
)
STRATEGY = RefreshStrategy(
    extension_version="2.18.0", function_schema="public", add_function_oid="456",
    remove_function_oid="457",
)
POLICY_ROW: dict[str, object] = {
    "job_id": "1000", "scheduled": True, "schedule_interval": "01:00:00",
    "start_offset": "30 days", "start_offset_type": "string",
    "end_offset": "01:00:00", "end_offset_type": "string",
}
POLICY = RefreshPolicy(
    job_id="1000", scheduled=True, schedule_interval="01:00:00", start_offset="30 days", end_offset="01:00:00",
)
WINDOW = RefreshWindow(
    start_offset=TimeDuration(amount=30, unit="day"), end_offset=TimeDuration(amount=1, unit="hour"),
    schedule_interval=TimeDuration(amount=1, unit="hour"),
)
DROP_AFTER = AgePolicy(job_id="900", scheduled=True, schedule_interval="1 day", older_than="90 days")


@dataclass
class Sources:
    discover: AsyncMock
    target: AsyncMock
    views: AsyncMock
    retention: AsyncMock
    routine: AsyncMock


def routine(_reader: object, _version: str, shape: RoutineShape) -> ExtensionRoutine:
    return ExtensionRoutine(oid="456" if shape.name.startswith("add_") else "457", schema_name="public")


@pytest.fixture
def sources(monkeypatch: pytest.MonkeyPatch) -> Sources:
    mocks = Sources(
        discover=AsyncMock(return_value=TimescaleProfile(SourceFeature(
            code="timescaledb", title="TimescaleDB", state="available", installed_version="2.18.0",
        ))),
        target=AsyncMock(return_value=TARGET), views=AsyncMock(),
        retention=AsyncMock(return_value=None), routine=AsyncMock(side_effect=routine),
    )
    monkeypatch.setattr(refresh_plan, "discover", mocks.discover)
    monkeypatch.setattr(refresh_plan, "continuous_aggregate", mocks.target)
    monkeypatch.setattr(refresh_plan, "require_public_view", mocks.views)
    monkeypatch.setattr(refresh_plan, "read_age_policy", mocks.retention)
    monkeypatch.setattr(refresh_plan, "extension_routine", mocks.routine)
    return mocks


def state(
    *, existing: RefreshPolicy | None = POLICY, retention: AgePolicy | None = None,
    column_type: str = "timestamp with time zone",
) -> RefreshState:
    return RefreshState(
        target=TARGET.model_copy(update={"column_type": column_type}), existing=existing,
        source_retention=retention, strategy=STRATEGY,
    )


def comparing(*answers: bool) -> AsyncMock:
    reader = AsyncMock()
    reader.query.side_effect = [[{"less": answer}] for answer in answers]
    return reader


async def test_inspection_reads_the_job_by_either_identity(sources: Sources) -> None:
    reader = AsyncMock()
    reader.query.return_value = [POLICY_ROW]
    sources.retention.return_value = DROP_AFTER
    inspected = await refresh_plan.inspect_refresh(reader, "lab", "hourly")
    assert inspected == RefreshState(
        target=TARGET, existing=POLICY, source_retention=DROP_AFTER, strategy=STRATEGY,
    )
    statement, params = reader.query.await_args.args
    assert statement == refresh_plan._EXISTING
    # Releases up to 2.19 name the materialization in the jobs view, later ones the view.
    assert params == ("_timescaledb_internal", "_materialized_hypertable_3", "lab", "hourly")
    sources.target.assert_awaited_once_with(reader, "lab", "hourly")
    sources.retention.assert_awaited_once_with(reader, RETENTION, "lab", "metrics")
    assert [call.args[2] for call in sources.routine.await_args_list] == [
        refresh_plan.ADD_REFRESH, refresh_plan.REMOVE_REFRESH,
    ]


def test_existing_statement_projects_validated_offsets_only() -> None:
    statement = refresh_plan._EXISTING
    assert "'policy_refresh_continuous_aggregate'" in statement
    assert statement.count("OPERATOR(pg_catalog.~)") == 2
    assert "deptype = 'e'" in statement
    assert "source.config AS" not in statement and "source.config," not in statement


@pytest.mark.parametrize("version", ["2.14.2", "2.18.0", "2.19.3", "2.30.0"])
async def test_every_version_asks_for_the_arguments_it_passes(sources: Sources, version: str) -> None:
    # This routine has had seven to eleven arguments; only the five execution
    # passes are asked for, so no release is refused for growing another.
    sources.discover.return_value = TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state="available", installed_version=version,
    ))
    reader = AsyncMock()
    reader.query.return_value = []
    await refresh_plan.inspect_refresh(reader, "lab", "hourly")
    added, removed = (call.args[2] for call in sources.routine.await_args_list)
    assert (added.name, added.argument_types) == (
        "add_continuous_aggregate_policy", "2205 2276 2276 1186 16",
    )
    assert removed.argument_types == "2205 16 16"


@pytest.mark.parametrize("start_type,expected", [(None, "from the earliest data"), ("null", "from the earliest data")])
@pytest.mark.usefixtures("sources")
async def test_unbounded_edges_are_readable(start_type: str | None, expected: str) -> None:
    reader = AsyncMock()
    reader.query.return_value = [{**POLICY_ROW, "start_offset": None, "start_offset_type": start_type}]
    existing = (await refresh_plan.inspect_refresh(reader, "lab", "hourly")).existing
    assert existing is not None and existing.start_offset is None
    assert existing.window() == f"{expected} to 01:00:00 ago"


@pytest.mark.parametrize("rows", [
    [{**POLICY_ROW, "start_offset": None, "start_offset_type": "number"}],
    [{**POLICY_ROW, "end_offset": None, "end_offset_type": "string"}],
    [{**POLICY_ROW, "scheduled": "yes"}],
    [{**POLICY_ROW, "config": {}}],
])
@pytest.mark.usefixtures("sources")
async def test_unreadable_policy_refuses(rows: list[dict[str, object]]) -> None:
    reader = AsyncMock()
    reader.query.return_value = rows
    with pytest.raises(ActionRefused, match="could not be read safely"):
        await refresh_plan.inspect_refresh(reader, "lab", "hourly")


@pytest.mark.usefixtures("sources")
async def test_several_policies_refuse() -> None:
    reader = AsyncMock()
    reader.query.return_value = [POLICY_ROW, {**POLICY_ROW, "job_id": "1001"}]
    with pytest.raises(ActionRefused, match="several refresh policy jobs"):
        await refresh_plan.inspect_refresh(reader, "lab", "hourly")


async def test_unavailable_extension_refuses_before_reads(sources: Sources) -> None:
    sources.discover.return_value = TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state="unsupported", installed_version="2.18.0",
        reason="The installed version lacks the supported inspection API",
    ))
    reader = AsyncMock()
    with pytest.raises(ActionRefused, match="lacks the supported inspection API"):
        await refresh_plan.inspect_refresh(reader, "lab", "hourly")
    reader.query.assert_not_called()
    sources.target.assert_not_awaited()


@pytest.mark.parametrize("error", [
    AdapterError("unknown", "secret password"), ValueError("secret password"), TimeoutError(),
])
@pytest.mark.usefixtures("sources")
async def test_inspection_failure_is_safe(error: Exception) -> None:
    reader = AsyncMock()
    reader.query.side_effect = error
    with pytest.raises(ActionRefused) as caught:
        await refresh_plan.plan_refresh(reader, "lab", "hourly", WINDOW)
    assert "secret" not in caught.value.message


async def test_window_is_compared_by_the_source_with_bound_values() -> None:
    reader = comparing(True, True)
    plan = await refresh_plan._build(reader, state(retention=DROP_AFTER), WINDOW)
    assert (plan.operation, plan.window, plan.source_retention) == ("set_policy", WINDOW, DROP_AFTER)
    first, second = reader.query.await_args_list
    assert first.args == (refresh_plan._LESS, ("1 hour", "30 day"))
    assert second.args == (refresh_plan._LESS, ("30 day", "90 days"))


async def test_window_must_start_further_back_than_it_ends() -> None:
    with pytest.raises(ActionRefused, match="start further back"):
        await refresh_plan._build(comparing(False), state(), WINDOW)


async def test_window_reaching_dropped_raw_data_is_refused() -> None:
    with pytest.raises(ActionRefused, match="retention policy drops"):
        await refresh_plan._build(comparing(True, False), state(retention=DROP_AFTER), WINDOW)


async def test_creation_time_retention_is_not_compared() -> None:
    created = DROP_AFTER.model_copy(update={"older_than": None, "created_before": "90 days"})
    reader = comparing(True)
    plan = await refresh_plan._build(reader, state(retention=created), WINDOW)
    assert plan.source_retention == created
    assert reader.query.await_count == 1


async def test_paused_policy_is_not_replaced_and_removal_needs_a_policy() -> None:
    paused = state(existing=POLICY.model_copy(update={"scheduled": False}))
    assert refresh_plan.setting_refusal(paused) is not None
    with pytest.raises(ActionRefused, match="paused"):
        await refresh_plan._build(comparing(True), paused, WINDOW)
    assert (await refresh_plan._build(AsyncMock(), paused, None)).operation == "remove_policy"
    with pytest.raises(ActionRefused, match="no refresh policy"):
        await refresh_plan._build(AsyncMock(), state(existing=None), None)


@pytest.mark.parametrize("unit,allowed", [("hour", False), ("day", True)])
async def test_date_aggregates_take_whole_day_offsets(unit: str, allowed: bool) -> None:
    window = WINDOW.model_copy(update={"end_offset": TimeDuration.model_validate({"amount": 1, "unit": unit})})
    current = state(column_type="date")
    if allowed:
        assert (await refresh_plan._build(comparing(True), current, window)).window == window
    else:
        with pytest.raises(ActionRefused, match="whole days"):
            await refresh_plan._build(comparing(True), current, window)


@pytest.mark.parametrize("section,field,value", [
    ("target", "materialization_oid", "655"), ("existing", "job_id", "1001"),
    ("existing", "start_offset", "7 days"), ("source_retention", "older_than", "30 days"),
    ("strategy", "add_function_oid", "458"),
])
async def test_every_planned_fact_is_fingerprinted(section: str, field: str, value: str) -> None:
    plan = await refresh_plan._build(comparing(True, True), state(retention=DROP_AFTER), WINDOW)
    changed = plan.model_dump()
    changed[section][field] = value
    with pytest.raises(ActionRefused, match="review it again"):
        RefreshPlan.model_validate(changed).require_unchanged(plan.fingerprint())


@pytest.mark.parametrize("operation,existing,window", [
    ("remove_policy", None, None), ("remove_policy", POLICY, WINDOW), ("set_policy", POLICY, None),
])
def test_inconsistent_plan_is_not_a_plan(
    operation: str, existing: RefreshPolicy | None, window: RefreshWindow | None,
) -> None:
    with pytest.raises(ValidationError):
        RefreshPlan.model_validate({
            "operation": operation, "target": TARGET, "existing": existing, "window": window,
            "source_retention": None, "strategy": STRATEGY,
        })
