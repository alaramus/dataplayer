from typing import Any
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
from app.adapters.catalog import ReportNode, SchemaNode, TableNode
from app.adapters.postgres.actions import PostgresActions
from app.adapters.postgres.timescale import age_policy_action
from app.adapters.postgres.timescale.age_policy_action import (
    RemoveAgePolicy,
    RemoveCompressionPolicy,
    RemoveRetentionPolicy,
    SetAgePolicy,
    SetCompressionPolicy,
    SetRetentionPolicy,
)
from app.adapters.postgres.timescale.age_policy_plan import (
    COMPRESSION,
    RETENTION,
    AgePolicySpec,
    AgePolicyState,
)
from app.adapters.postgres.timescale.plans import (
    AgePolicy,
    AgePolicyPlan,
    AgePolicyStrategy,
    TimeDuration,
    TimeHypertable,
)
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.protocol import AdapterError

TARGET = TimeHypertable(
    database_oid="42", relation_oid="123", schema_name='odd"schema', table_name="events",
    column_name="time", column_type="timestamp with time zone",
)
POLICY = AgePolicy(job_id="1000", scheduled=True, schedule_interval="1 day", older_than="10 years")
TEN_YEARS = TimeDuration(amount=10, unit="year")
SETTERS = [
    pytest.param(SetRetentionPolicy, RETENTION, id="retention"),
    pytest.param(SetCompressionPolicy, COMPRESSION, id="compression"),
]
REMOVERS = [
    pytest.param(RemoveRetentionPolicy, RETENTION, id="retention"),
    pytest.param(RemoveCompressionPolicy, COMPRESSION, id="compression"),
]


def catalog() -> AsyncMock:
    found = AsyncMock()
    found.path_to.return_value = [
        SchemaNode(id="schema-id", name='odd"schema', has_children=True, representations=[]),
        TableNode(id="node-id", name="events", has_children=False, representations=[]),
    ]
    return found


def strategy(spec: AgePolicySpec) -> AgePolicyStrategy:
    return AgePolicyStrategy.model_validate({
        "kind": spec.kind, "extension_version": "2.18.0", "function_schema": "public",
        "add_function_oid": "456", "remove_function_oid": "457", "jobs_view_oid": "789",
    })


def plan(
    spec: AgePolicySpec, *, existing: AgePolicy | None = POLICY, older_than: TimeDuration | None = TEN_YEARS,
) -> AgePolicyPlan:
    return AgePolicyPlan(
        operation="set_policy" if older_than is not None else "remove_policy", kind=spec.kind,
        target=TARGET, existing=existing, older_than=older_than, strategy=strategy(spec),
    )


@pytest.mark.parametrize("action_type,spec", SETTERS)
async def test_setting_uses_review_transport(
    monkeypatch: pytest.MonkeyPatch, action_type: type[SetAgePolicy[Any]], spec: AgePolicySpec,
) -> None:
    selected = action_type(AsyncMock(), catalog())
    assert isinstance(selected, TakesParams)
    assert isinstance(selected, Previews)
    assert isinstance(selected, RequiresReviewedPlan)
    assert selected.spec is spec
    assert selected.requires == "structure"
    assert selected.feature_requirements == ("timescaledb",)
    preview = AsyncMock(return_value=ActionPreview(summary="Review", fingerprint="a" * 64))
    execute = AsyncMock()
    monkeypatch.setattr(age_policy_action, "preview_age_policy", preview)
    monkeypatch.setattr(age_policy_action, "execute_age_policy", execute)
    params = {"amount": 10, "unit": "year"}
    assert (await selected.preview("opaque-client-id", params)).fingerprint == "a" * 64
    preview.assert_awaited_once_with(selected._session, spec, 'odd"schema', "events", TEN_YEARS)
    result = await selected.perform_reviewed("opaque-client-id", params, "a" * 64)
    execute.assert_awaited_once_with(selected._session, spec, 'odd"schema', "events", TEN_YEARS, "a" * 64)
    assert type(execute.await_args.args[4]) is TimeDuration
    assert "10 year" in result.message
    assert result.reload_node_ids == ["schema-id", "node-id", TIMESCALE_SECTION_ID]


def test_only_retention_asks_about_future_deletion() -> None:
    assert SetRetentionPolicy.destructive
    assert SetRetentionPolicy.question is not None
    assert "after this session ends" in SetRetentionPolicy.question
    assert not SetCompressionPolicy.destructive and SetCompressionPolicy.question is None
    assert not RemoveRetentionPolicy.destructive and not RemoveCompressionPolicy.destructive


@pytest.mark.parametrize("action_type,spec", REMOVERS)
async def test_removal_takes_no_parameters(
    monkeypatch: pytest.MonkeyPatch, action_type: type[RemoveAgePolicy], spec: AgePolicySpec,
) -> None:
    selected = action_type(AsyncMock(), catalog())
    assert isinstance(selected, RequiresReviewedPlan)
    assert selected.requires == "structure"
    preview = AsyncMock(return_value=ActionPreview(summary="Review", fingerprint="b" * 64))
    execute = AsyncMock()
    monkeypatch.setattr(age_policy_action, "preview_age_policy", preview)
    monkeypatch.setattr(age_policy_action, "execute_age_policy", execute)
    await selected.preview("node-id", {})
    preview.assert_awaited_once_with(selected._session, spec, 'odd"schema', "events", None)
    await selected.perform_reviewed("node-id", {}, "b" * 64)
    execute.assert_awaited_once_with(selected._session, spec, 'odd"schema', "events", None, "b" * 64)
    with pytest.raises(ValidationError):
        await selected.perform_reviewed("node-id", {"amount": 1}, "b" * 64)


@pytest.mark.parametrize("action_type,params", [
    (SetRetentionPolicy, {"amount": 10, "unit": "year"}), (RemoveRetentionPolicy, {}),
    (SetCompressionPolicy, {"amount": 10, "unit": "year"}), (RemoveCompressionPolicy, {}),
])
async def test_unreviewed_call_cannot_execute(
    monkeypatch: pytest.MonkeyPatch, action_type: type[SetAgePolicy[Any] | RemoveAgePolicy],
    params: dict[str, object],
) -> None:
    execute = AsyncMock()
    monkeypatch.setattr(age_policy_action, "execute_age_policy", execute)
    with pytest.raises(ActionRefused, match="Review"):
        await action_type(AsyncMock(), catalog()).perform("node-id", params)
    execute.assert_not_called()


@pytest.mark.parametrize("node_id,path", [
    (None, []),
    ("schema-id", [SchemaNode(id="schema-id", name="lab", has_children=True, representations=[])]),
    ("report-id", [ReportNode(id="report-id", name="Jobs", has_children=False, representations=[])]),
])
async def test_invalid_target_is_refused(node_id: str | None, path: list[object]) -> None:
    found = AsyncMock()
    found.path_to.return_value = path
    with pytest.raises(ActionRefused, match="user hypertable"):
        await SetCompressionPolicy(AsyncMock(), found).perform_reviewed(
            node_id, {"amount": 10, "unit": "year"}, "a" * 64,
        )


@pytest.mark.parametrize("action_type,_spec", SETTERS)
@pytest.mark.parametrize("params", [
    {"amount": 10, "unit": "year'; SELECT 1; --"}, {"amount": "10", "unit": "year"},
    {"amount": 0, "unit": "day"}, {"amount": 10, "unit": "second"},
    {"amount": 10, "unit": "year", "if_not_exists": True},
])
async def test_threshold_is_validated_before_target_read(
    action_type: type[SetAgePolicy[Any]], _spec: AgePolicySpec, params: dict[str, object],
) -> None:
    selected = action_type(AsyncMock(), catalog())
    with pytest.raises(ValidationError):
        await selected.perform_reviewed("node-id", params, "a" * 64)
    selected._catalog.path_to.assert_not_called()


@pytest.mark.parametrize("action_type,title", [
    (SetRetentionPolicy, "Drop chunks older than"), (SetCompressionPolicy, "Compress chunks older than"),
])
def test_form_offers_threshold_units_on_one_row(action_type: type[SetAgePolicy[Any]], title: str) -> None:
    properties = action_type.params_model.model_json_schema()["properties"]
    assert list(properties) == ["amount", "unit"]
    assert properties["amount"]["title"] == title
    assert properties["unit"]["enum"] == ["hour", "day", "week", "month", "year"]
    assert properties["amount"]["row"] == properties["unit"]["row"] == "threshold"
    assert RemoveRetentionPolicy.params_model.model_json_schema()["properties"] == {}


def test_policy_lookup_is_registered_and_unknown_names_stay_closed() -> None:
    registry = PostgresActions(AsyncMock(), AsyncMock())
    for action_type in (SetRetentionPolicy, RemoveRetentionPolicy, SetCompressionPolicy, RemoveCompressionPolicy):
        assert isinstance(registry.action(action_type.name), action_type)
    with pytest.raises(UnknownAction):
        registry.action("add_compression_policy")


@pytest.mark.parametrize("spec,planned,summary,expected", [
    (RETENTION, plan(RETENTION, existing=None), 'Set the retention policy for "odd""schema"."events"', [
        'Time dimension: "time"', "No retention policy exists yet",
        "New policy: drop chunks older than 10 year",
    ]),
    (COMPRESSION, plan(COMPRESSION, older_than=TimeDuration(amount=20, unit="year")),
     'Set the compression policy for "odd""schema"."events"', [
        'Time dimension: "time"', "Replaces job 1000, which compresses chunks older than 10 years",
        "The current policy runs every 1 day; its replacement uses TimescaleDB's default schedule",
        "New policy: compress chunks older than 20 year",
    ]),
    (RETENTION, plan(RETENTION, older_than=None), 'Remove the retention policy from "odd""schema"."events"', [
        'Time dimension: "time"', "Removes job 1000, which drops chunks older than 10 years",
    ]),
    (COMPRESSION, plan(COMPRESSION, existing=POLICY.model_copy(update={
        "older_than": None, "created_before": "30 days",
    }), older_than=None), 'Remove the compression policy from "odd""schema"."events"', [
        'Time dimension: "time"', "Removes job 1000, which compresses chunks created more than 30 days ago",
    ]),
])
async def test_preview_renders_the_snapshot_plan(
    monkeypatch: pytest.MonkeyPatch, spec: AgePolicySpec, planned: AgePolicyPlan,
    summary: str, expected: list[str],
) -> None:
    planner = AsyncMock(return_value=planned)
    monkeypatch.setattr(age_policy_action, "plan_age_policy", planner)
    session = MagicMock()
    reader = session.inspection.return_value.__aenter__.return_value
    result = await age_policy_action.preview_age_policy(session, spec, "lab", "events", planned.older_than)
    planner.assert_awaited_once_with(reader, spec, "lab", "events", planned.older_than)
    assert result.summary == summary
    assert result.items == [*expected, planned.impact, planned.coordination]
    assert result.fingerprint == planned.fingerprint()
    assert not result.blocked
    session.rehearse.assert_not_called()


@pytest.mark.parametrize("error", [
    ActionRefused("not_applicable", "Enable compression on this hypertable first"),
    AdapterError("unknown", "secret password"), ValueError("secret password"), TimeoutError(),
])
async def test_failed_plan_has_no_review_fingerprint(
    monkeypatch: pytest.MonkeyPatch, error: Exception,
) -> None:
    monkeypatch.setattr(age_policy_action, "plan_age_policy", AsyncMock(side_effect=error))
    result = await age_policy_action.preview_age_policy(MagicMock(), COMPRESSION, "lab", "events", None)
    assert result.blocked and result.fingerprint is None and result.items == []
    assert "secret" not in result.summary
    if isinstance(error, ActionRefused):
        assert result.summary == error.message


@pytest.mark.parametrize("spec", [pytest.param(RETENTION, id="retention"), pytest.param(COMPRESSION, id="compression")])
@pytest.mark.parametrize("existing,paused_refusal,no_policy_refusal", [
    (None, False, True), (POLICY, False, False), (POLICY.model_copy(update={"scheduled": False}), True, False),
])
async def test_admission_answers_both_actions_from_one_snapshot(
    monkeypatch: pytest.MonkeyPatch, spec: AgePolicySpec, existing: AgePolicy | None,
    paused_refusal: bool, no_policy_refusal: bool,
) -> None:
    inspect = AsyncMock(return_value=AgePolicyState(target=TARGET, existing=existing, strategy=strategy(spec)))
    monkeypatch.setattr(age_policy_action, "inspect_age_policy", inspect)
    session = MagicMock()
    setting, removing = await age_policy_action.age_policy_admission(session, spec, "lab", "events")
    assert setting == (
        f"The existing {spec.noun} is paused; remove it before setting a new one" if paused_refusal else None
    )
    assert removing == (f"This hypertable has no {spec.noun}" if no_policy_refusal else None)
    inspect.assert_awaited_once_with(
        session.inspection.return_value.__aenter__.return_value, spec, "lab", "events",
    )


@pytest.mark.parametrize("error,reason", [
    (ActionRefused("not_applicable", "Enable compression on this hypertable first"),
     "Enable compression on this hypertable first"),
    (AdapterError("network", "secret password"), "TimescaleDB compression policy metadata could not be inspected safely"),
    (TimeoutError(), "TimescaleDB compression policy metadata could not be inspected safely"),
])
async def test_refused_admission_explains_both_actions(
    monkeypatch: pytest.MonkeyPatch, error: Exception, reason: str,
) -> None:
    monkeypatch.setattr(age_policy_action, "inspect_age_policy", AsyncMock(side_effect=error))
    assert await age_policy_action.age_policy_admission(MagicMock(), COMPRESSION, "lab", "events") == (reason, reason)
