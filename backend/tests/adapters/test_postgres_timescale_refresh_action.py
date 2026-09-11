from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.adapters.actions import (
    ActionPreview,
    ActionRefused,
    Previews,
    RequiresReviewedPlan,
    TakesParams,
    UnknownAction,
)
from app.adapters.catalog import SchemaNode, TableNode, ViewNode
from app.adapters.postgres.actions import PostgresActions
from app.adapters.postgres.timescale import refresh_action
from app.adapters.postgres.timescale.plans import (
    AgePolicy,
    ContinuousAggregateTarget,
    RefreshPlan,
    RefreshPolicy,
    RefreshStrategy,
    RefreshWindow,
    TimeDuration,
)
from app.adapters.postgres.timescale.refresh_action import (
    RemoveRefreshPolicy,
    SetRefreshPolicy,
)
from app.adapters.postgres.timescale.refresh_plan import RefreshState
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.protocol import AdapterError

TARGET = ContinuousAggregateTarget(
    database_oid="42", view_oid="321", view_schema='odd"schema', view_name="hourly",
    materialization_oid="654", materialization_schema="_timescaledb_internal",
    materialization_name="_materialized_hypertable_3", source_schema="lab", source_name="metrics",
    column_type="timestamp with time zone",
)
STRATEGY = RefreshStrategy(
    extension_version="2.18.0", function_schema="public", add_function_oid="456",
    remove_function_oid="457", jobs_view_oid="789",
)
POLICY = RefreshPolicy(
    job_id="1000", scheduled=True, schedule_interval="01:00:00", start_offset="30 days", end_offset="01:00:00",
)
PARAMS: dict[str, object] = {
    "start_amount": 7, "start_unit": "day", "end_amount": 1, "end_unit": "hour",
    "schedule_amount": 30, "schedule_unit": "minute",
}
WINDOW = RefreshWindow(
    start_offset=TimeDuration(amount=7, unit="day"), end_offset=TimeDuration(amount=1, unit="hour"),
    schedule_interval=TimeDuration(amount=30, unit="minute"),
)
DROP_AFTER = AgePolicy(job_id="900", scheduled=True, schedule_interval="1 day", older_than="90 days")


def catalog(node: object | None = None) -> AsyncMock:
    found = AsyncMock()
    found.path_to.return_value = [
        SchemaNode(id="schema-id", name='odd"schema', has_children=True, representations=[]),
        node or ViewNode(id="view-id", name="hourly", has_children=False, representations=[]),
    ]
    return found


def plan(
    *, existing: RefreshPolicy | None = POLICY, window: RefreshWindow | None = WINDOW,
    retention: AgePolicy | None = None,
) -> RefreshPlan:
    return RefreshPlan(
        operation="set_policy" if window is not None else "remove_policy", target=TARGET,
        existing=existing, window=window, source_retention=retention, strategy=STRATEGY,
    )


async def test_setting_uses_review_transport_on_an_aggregate(monkeypatch: pytest.MonkeyPatch) -> None:
    selected = SetRefreshPolicy(AsyncMock(), catalog())
    assert isinstance(selected, TakesParams)
    assert isinstance(selected, Previews)
    assert isinstance(selected, RequiresReviewedPlan)
    assert (selected.requires, selected.destructive, selected.applies_to) == ("structure", False, {"view"})
    assert selected.feature_requirements == ("timescaledb",)
    preview = AsyncMock(return_value=ActionPreview(summary="Review", fingerprint="a" * 64))
    execute = AsyncMock()
    monkeypatch.setattr(refresh_action, "preview_refresh", preview)
    monkeypatch.setattr(refresh_action, "execute_refresh", execute)
    assert (await selected.preview("opaque", PARAMS)).fingerprint == "a" * 64
    preview.assert_awaited_once_with(selected._session, 'odd"schema', "hourly", WINDOW)
    result = await selected.perform_reviewed("opaque", PARAMS, "a" * 64)
    execute.assert_awaited_once_with(selected._session, 'odd"schema', "hourly", WINDOW, "a" * 64)
    assert result.reload_node_ids == ["schema-id", "view-id", TIMESCALE_SECTION_ID]


async def test_removal_takes_no_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    selected = RemoveRefreshPolicy(AsyncMock(), catalog())
    preview = AsyncMock(return_value=ActionPreview(summary="Review", fingerprint="b" * 64))
    execute = AsyncMock()
    monkeypatch.setattr(refresh_action, "preview_refresh", preview)
    monkeypatch.setattr(refresh_action, "execute_refresh", execute)
    await selected.preview("opaque", {})
    preview.assert_awaited_once_with(selected._session, 'odd"schema', "hourly", None)
    await selected.perform_reviewed("opaque", {}, "b" * 64)
    execute.assert_awaited_once_with(selected._session, 'odd"schema', "hourly", None, "b" * 64)
    with pytest.raises(ValidationError):
        await selected.perform_reviewed("opaque", {"start_amount": 1}, "b" * 64)


@pytest.mark.parametrize("action_type,params", [(SetRefreshPolicy, PARAMS), (RemoveRefreshPolicy, {})])
async def test_unreviewed_call_cannot_execute(
    monkeypatch: pytest.MonkeyPatch, action_type: type[SetRefreshPolicy | RemoveRefreshPolicy],
    params: dict[str, object],
) -> None:
    execute = AsyncMock()
    monkeypatch.setattr(refresh_action, "execute_refresh", execute)
    with pytest.raises(ActionRefused, match="Review"):
        await action_type(AsyncMock(), catalog()).perform("opaque", params)
    execute.assert_not_called()


async def test_table_is_not_an_aggregate_target() -> None:
    table = TableNode(id="node-id", name="metrics", has_children=False, representations=[])
    with pytest.raises(ActionRefused, match="user continuous aggregate"):
        await SetRefreshPolicy(AsyncMock(), catalog(table)).perform_reviewed("node-id", PARAMS, "a" * 64)


@pytest.mark.parametrize("change", [
    {"start_amount": 100_001}, {"start_amount": "7"}, {"end_amount": 0},
    {"schedule_unit": "month"}, {"start_unit": "day'; SELECT 1; --"}, {"if_not_exists": True},
])
async def test_window_is_validated_before_target_read(change: dict[str, object]) -> None:
    selected = SetRefreshPolicy(AsyncMock(), catalog())
    with pytest.raises(ValidationError):
        await selected.perform_reviewed("opaque", {**PARAMS, **change}, "a" * 64)
    selected._catalog.path_to.assert_not_called()


def test_form_lays_out_start_end_and_schedule_rows() -> None:
    properties = SetRefreshPolicy.params_model.model_json_schema()["properties"]
    assert list(properties) == [
        "start_amount", "start_unit", "end_amount", "end_unit", "schedule_amount", "schedule_unit",
    ]
    assert [properties[name]["row"] for name in properties] == [
        "start", "start", "end", "end", "schedule", "schedule",
    ]
    assert properties["schedule_unit"]["enum"] == ["minute", "hour", "day", "week"]
    assert properties["start_unit"]["enum"] == ["minute", "hour", "day", "week", "month", "year"]


def test_refresh_lookup_is_registered_and_unknown_names_stay_closed() -> None:
    registry = PostgresActions(AsyncMock(), AsyncMock())
    assert isinstance(registry.action(SetRefreshPolicy.name), SetRefreshPolicy)
    assert isinstance(registry.action(RemoveRefreshPolicy.name), RemoveRefreshPolicy)
    with pytest.raises(UnknownAction):
        registry.action("add_continuous_aggregate_policy")


@pytest.mark.parametrize("planned,summary,expected", [
    (plan(existing=None), 'Set the refresh policy for "odd""schema"."hourly"', [
        'Source hypertable: "lab"."metrics"', "No refresh policy exists yet",
        "New policy: refresh from 7 day ago to 1 hour ago, every 30 minute",
        "The source hypertable has no retention policy",
    ]),
    (plan(retention=DROP_AFTER), 'Set the refresh policy for "odd""schema"."hourly"', [
        'Source hypertable: "lab"."metrics"',
        "Replaces job 1000, which refreshes from 30 days ago to 01:00:00 ago every 01:00:00",
        "New policy: refresh from 7 day ago to 1 hour ago, every 30 minute",
        "The source drops chunks older than 90 days; the window starts after that",
    ]),
    (plan(retention=DROP_AFTER.model_copy(update={"older_than": None, "created_before": "90 days"})),
     'Set the refresh policy for "odd""schema"."hourly"', [
        'Source hypertable: "lab"."metrics"',
        "Replaces job 1000, which refreshes from 30 days ago to 01:00:00 ago every 01:00:00",
        "New policy: refresh from 7 day ago to 1 hour ago, every 30 minute",
        "The source drops chunks created more than 90 days ago; "
        "check that it keeps the raw data this window refreshes",
    ]),
    (plan(window=None), 'Remove the refresh policy from "odd""schema"."hourly"', [
        'Source hypertable: "lab"."metrics"',
        "Removes job 1000, which refreshes from 30 days ago to 01:00:00 ago every 01:00:00",
    ]),
])
async def test_preview_renders_the_snapshot_plan(
    monkeypatch: pytest.MonkeyPatch, planned: RefreshPlan, summary: str, expected: list[str],
) -> None:
    planner = AsyncMock(return_value=planned)
    monkeypatch.setattr(refresh_action, "plan_refresh", planner)
    session = MagicMock()
    reader = session.inspection.return_value.__aenter__.return_value
    result = await refresh_action.preview_refresh(session, "lab", "hourly", planned.window)
    planner.assert_awaited_once_with(reader, "lab", "hourly", planned.window)
    assert result.summary == summary
    assert result.items == [*expected, planned.impact, planned.coordination]
    assert result.fingerprint == planned.fingerprint()


@pytest.mark.parametrize("error", [
    ActionRefused("not_applicable", "The window must start further back than it ends"),
    AdapterError("unknown", "secret password"), TimeoutError(),
])
async def test_failed_plan_has_no_review_fingerprint(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(refresh_action, "plan_refresh", AsyncMock(side_effect=error))
    result = await refresh_action.preview_refresh(MagicMock(), "lab", "hourly", WINDOW)
    assert result.blocked and result.fingerprint is None and result.items == []
    assert "secret" not in result.summary


@pytest.mark.parametrize("existing,expected", [
    (None, (None, "This continuous aggregate has no refresh policy")),
    (POLICY, (None, None)),
    (POLICY.model_copy(update={"scheduled": False}),
     ("The existing refresh policy is paused; remove it before setting a new one", None)),
])
async def test_admission_answers_both_actions_from_one_snapshot(
    monkeypatch: pytest.MonkeyPatch, existing: RefreshPolicy | None, expected: tuple[str | None, str | None],
) -> None:
    inspect = AsyncMock(return_value=RefreshState(
        target=TARGET, existing=existing, source_retention=None, strategy=STRATEGY,
    ))
    monkeypatch.setattr(refresh_action, "inspect_refresh", inspect)
    session = MagicMock()
    assert await refresh_action.refresh_admission(session, "lab", "hourly") == expected
    inspect.assert_awaited_once_with(session.inspection.return_value.__aenter__.return_value, "lab", "hourly")


@pytest.mark.parametrize("error,reason", [
    (ActionRefused("not_applicable", "Choose an owned continuous aggregate"), "Choose an owned continuous aggregate"),
    (AdapterError("network", "secret password"), "TimescaleDB refresh policy metadata could not be inspected safely"),
])
async def test_refused_admission_explains_both_actions(
    monkeypatch: pytest.MonkeyPatch, error: Exception, reason: str,
) -> None:
    monkeypatch.setattr(refresh_action, "inspect_refresh", AsyncMock(side_effect=error))
    assert await refresh_action.refresh_admission(MagicMock(), "lab", "hourly") == (reason, reason)
