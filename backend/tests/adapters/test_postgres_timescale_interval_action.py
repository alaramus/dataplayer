from unittest.mock import AsyncMock

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
from app.adapters.postgres.timescale import interval_action
from app.adapters.postgres.timescale.interval_action import (
    ChunkIntervalParams,
    SetChunkInterval,
)
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID


def action() -> SetChunkInterval:
    catalog = AsyncMock()
    catalog.path_to.return_value = [
        SchemaNode(id="schema-id", name='odd"schema', has_children=True, representations=[]),
        TableNode(id="node-id", name="events", has_children=False, representations=[]),
    ]
    return SetChunkInterval(AsyncMock(), catalog)


async def test_action_uses_review_transport_and_source_resolved_target(monkeypatch: pytest.MonkeyPatch) -> None:
    selected = action()
    assert isinstance(selected, TakesParams)
    assert isinstance(selected, Previews)
    assert isinstance(selected, RequiresReviewedPlan)
    assert selected.requires == "structure"
    assert selected.feature_requirements == ("timescaledb",)
    preview = AsyncMock(return_value=ActionPreview(summary="Review", fingerprint="a" * 64))
    execute = AsyncMock()
    monkeypatch.setattr(interval_action, "preview_chunk_interval", preview)
    monkeypatch.setattr(interval_action, "execute_chunk_interval", execute)
    assert (await selected.preview("opaque-client-id", {"amount": 2, "unit": "day"})).fingerprint == "a" * 64
    preview.assert_awaited_once_with(selected._session, 'odd"schema', "events", ChunkIntervalParams(amount=2, unit="day"))
    result = await selected.perform_reviewed("opaque-client-id", {"amount": 2, "unit": "day"}, "a" * 64)
    execute.assert_awaited_once_with(
        selected._session, 'odd"schema', "events", ChunkIntervalParams(amount=2, unit="day"), "a" * 64,
    )
    assert result.reload_node_ids == ["schema-id", "node-id", TIMESCALE_SECTION_ID]


async def test_unreviewed_call_cannot_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    execute = AsyncMock()
    monkeypatch.setattr(interval_action, "execute_chunk_interval", execute)
    with pytest.raises(ActionRefused, match="Review"):
        await action().perform("node-id", {"amount": 2, "unit": "day"})
    execute.assert_not_called()


@pytest.mark.parametrize("node_id,path", [
    (None, []), ("schema-id", [SchemaNode(id="schema-id", name="lab", has_children=True, representations=[])]),
    ("report-id", [ReportNode(id="report-id", name="Dimensions", has_children=False, representations=[])]),
    ("node-id", [
        SchemaNode(id="schema-id", name="lab", has_children=True, representations=[]),
        TableNode(id="node-id", name="internal", is_system=True, has_children=False, representations=[]),
    ]),
])
async def test_invalid_target_is_refused(node_id: str | None, path: list[object]) -> None:
    catalog = AsyncMock()
    catalog.path_to.return_value = path
    selected = SetChunkInterval(AsyncMock(), catalog)
    with pytest.raises(ActionRefused):
        await selected.perform_reviewed(node_id, {"amount": 2, "unit": "day"}, "a" * 64)


async def test_sql_in_duration_is_rejected_before_target_read() -> None:
    selected = action()
    with pytest.raises(ValidationError):
        await selected.perform_reviewed("node-id", {"amount": 2, "unit": "day'; SELECT 1; --"}, "a" * 64)
    selected._catalog.path_to.assert_not_called()


def test_action_form_does_not_offer_calendar_intervals() -> None:
    assert SetChunkInterval.params_model.model_json_schema()["properties"]["unit"]["enum"] == [
        "second", "minute", "hour", "day", "week",
    ]


def test_interval_lookup_is_registered_and_unknown_names_stay_closed() -> None:
    registry = PostgresActions(AsyncMock(), AsyncMock())
    assert isinstance(registry.action(SetChunkInterval.name), SetChunkInterval)
    with pytest.raises(UnknownAction):
        registry.action("set_chunk_time_interval")
