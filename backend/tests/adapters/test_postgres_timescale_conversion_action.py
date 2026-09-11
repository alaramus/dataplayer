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
from app.adapters.catalog import SchemaNode, TableNode
from app.adapters.postgres.actions import PostgresActions
from app.adapters.postgres.timescale import conversion_action
from app.adapters.postgres.timescale.conversion_action import ConvertToHypertable
from app.adapters.postgres.timescale.plans import (
    ConversionColumn,
    ConversionPlan,
    ConversionStrategy,
    ConversionTarget,
    TimeDuration,
)
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.protocol import AdapterError

PARAMS: dict[str, object] = {"time_column": "observed_at", "amount": 7, "unit": "day"}
WEEK = TimeDuration(amount=7, unit="day")


def plan(*, not_null: bool = False, time_index_exists: bool = False) -> ConversionPlan:
    return ConversionPlan(
        target=ConversionTarget(database_oid="42", relation_oid="123", schema_name='odd"schema', table_name="events"),
        column=ConversionColumn(name="observed_at", type="timestamp with time zone", not_null=not_null),
        interval=WEEK, time_index_exists=time_index_exists,
        strategy=ConversionStrategy(
            extension_version="2.18.0", function_schema="public", create_function_oid="456",
            by_range_function_oid="457", dimension_info_oid="99999",
        ),
    )


def catalog(guard: str | None = None) -> AsyncMock:
    found = AsyncMock()
    found.path_to.return_value = [
        SchemaNode(id="schema-id", name='odd"schema', has_children=True, representations=[]),
        TableNode(id="node-id", name="events", has_children=False, representations=[]),
    ]
    found.relation_action_reason.return_value = guard
    return found


async def test_conversion_uses_review_transport_and_asks_before_an_irreversible_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = ConvertToHypertable(AsyncMock(), catalog())
    assert isinstance(selected, TakesParams)
    assert isinstance(selected, Previews)
    assert isinstance(selected, RequiresReviewedPlan)
    assert (selected.requires, selected.destructive) == ("structure", True)
    assert selected.question is not None and "cannot turn back" in selected.question
    preview = AsyncMock(return_value=ActionPreview(summary="Review", fingerprint="a" * 64))
    execute = AsyncMock(return_value=plan())
    monkeypatch.setattr(conversion_action, "preview_conversion", preview)
    monkeypatch.setattr(conversion_action, "execute_conversion", execute)
    await selected.preview("opaque", PARAMS)
    preview.assert_awaited_once_with(selected._session, 'odd"schema', "events", "observed_at", WEEK)
    result = await selected.perform_reviewed("opaque", PARAMS, "a" * 64)
    execute.assert_awaited_once_with(selected._session, 'odd"schema', "events", "observed_at", WEEK, "a" * 64)
    assert result.reload_node_ids == ["schema-id", "node-id", TIMESCALE_SECTION_ID]
    assert result.replacement is None


async def test_ordinary_protection_refuses_before_any_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    preview = AsyncMock()
    execute = AsyncMock()
    monkeypatch.setattr(conversion_action, "preview_conversion", preview)
    monkeypatch.setattr(conversion_action, "execute_conversion", execute)
    selected = ConvertToHypertable(AsyncMock(), catalog("Something else is built on this relation"))
    for call in (selected.preview("opaque", PARAMS), selected.perform_reviewed("opaque", PARAMS, "a" * 64)):
        with pytest.raises(ActionRefused, match="Something else is built"):
            await call
    preview.assert_not_called()
    execute.assert_not_called()


async def test_unreviewed_call_cannot_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    execute = AsyncMock()
    monkeypatch.setattr(conversion_action, "execute_conversion", execute)
    with pytest.raises(ActionRefused, match="Review"):
        await ConvertToHypertable(AsyncMock(), catalog()).perform("opaque", PARAMS)
    execute.assert_not_called()


@pytest.mark.parametrize("change", [
    {"time_column": ""}, {"time_column": "x" * 64}, {"unit": "month"}, {"amount": "7"},
    {"migrate_data": True},
])
async def test_form_is_validated_before_target_read(change: dict[str, object]) -> None:
    selected = ConvertToHypertable(AsyncMock(), catalog())
    with pytest.raises(ValidationError):
        await selected.perform_reviewed("opaque", {**PARAMS, **change}, "a" * 64)
    selected._catalog.path_to.assert_not_called()


def test_conversion_lookup_is_registered_and_unknown_names_stay_closed() -> None:
    registry = PostgresActions(AsyncMock(), AsyncMock())
    assert isinstance(registry.action(ConvertToHypertable.name), ConvertToHypertable)
    with pytest.raises(UnknownAction):
        registry.action("create_hypertable")


@pytest.mark.parametrize("planned,expected", [
    (plan(), [
        'Time column: "observed_at" (timestamp with time zone)', "Chunk interval: 7 day",
        "The table is empty, and the conversion refuses if a row arrives before it runs",
        '"observed_at" becomes NOT NULL', 'TimescaleDB adds an index on "observed_at", newest first',
    ]),
    (plan(not_null=True, time_index_exists=True), [
        'Time column: "observed_at" (timestamp with time zone)', "Chunk interval: 7 day",
        "The table is empty, and the conversion refuses if a row arrives before it runs",
        'An index on "observed_at" alone already exists, so TimescaleDB adds none',
    ]),
])
async def test_preview_renders_the_snapshot_plan(
    monkeypatch: pytest.MonkeyPatch, planned: ConversionPlan, expected: list[str],
) -> None:
    planner = AsyncMock(return_value=planned)
    monkeypatch.setattr(conversion_action, "plan_conversion", planner)
    session = MagicMock()
    reader = session.inspection.return_value.__aenter__.return_value
    result = await conversion_action.preview_conversion(session, "lab", "events", "observed_at", WEEK)
    planner.assert_awaited_once_with(reader, "lab", "events", "observed_at", WEEK)
    assert result.summary == 'Convert "odd""schema"."events" into a hypertable'
    assert result.items == [*expected, planned.impact, planned.coordination]
    assert result.fingerprint == planned.fingerprint()


@pytest.mark.parametrize("error", [
    ActionRefused("not_applicable", "This table is not empty; only empty tables are converted here"),
    AdapterError("unknown", "secret password"), TimeoutError(),
])
async def test_failed_plan_has_no_review_fingerprint(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(conversion_action, "plan_conversion", AsyncMock(side_effect=error))
    result = await conversion_action.preview_conversion(MagicMock(), "lab", "events", "observed_at", WEEK)
    assert result.blocked and result.fingerprint is None and result.items == []
    assert "secret" not in result.summary


@pytest.mark.parametrize("outcome,reason", [
    (None, None),
    (ActionRefused("not_applicable", "Only logged tables can become hypertables"),
     "Only logged tables can become hypertables"),
    (AdapterError("network", "secret password"), conversion_action._UNREADABLE),
])
async def test_admission_asks_only_column_independent_questions(
    monkeypatch: pytest.MonkeyPatch, outcome: Exception | None, reason: str | None,
) -> None:
    inspect = AsyncMock(side_effect=outcome) if outcome is not None else AsyncMock()
    monkeypatch.setattr(conversion_action, "inspect_conversion", inspect)
    session = MagicMock()
    assert await conversion_action.conversion_admission(session, "lab", "events") == reason
    inspect.assert_awaited_once_with(session.inspection.return_value.__aenter__.return_value, "lab", "events")
