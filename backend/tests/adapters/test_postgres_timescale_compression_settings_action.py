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
from app.adapters.postgres.timescale import compression_settings_action
from app.adapters.postgres.timescale.compression_settings_action import (
    ConfigureCompression,
)
from app.adapters.postgres.timescale.plans import (
    CompressionSettingsPlan,
    CompressionSettingsStrategy,
    OrderColumn,
    TimeHypertable,
)
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
from app.adapters.protocol import AdapterError

TIME_DESC = OrderColumn(column="observed_at", descending=True, nulls_first=True)


def plan(**changes: object) -> CompressionSettingsPlan:
    base: dict[str, object] = {
        "target": TimeHypertable(
            database_oid="42", relation_oid="123", schema_name='odd"schema', table_name="events",
            column_name="observed_at", column_type="timestamp with time zone",
        ),
        "enabled": False, "current_segment_by": None, "current_order_by": None,
        "segment_by": ("device",), "order_by": (TIME_DESC,), "any_compressed": False,
        "unsegmented_unique": (), "strategy": CompressionSettingsStrategy(extension_version="2.18.0"),
    }
    return CompressionSettingsPlan.model_validate({**base, **changes})


def catalog() -> AsyncMock:
    found = AsyncMock()
    found.path_to.return_value = [
        SchemaNode(id="schema-id", name='odd"schema', has_children=True, representations=[]),
        TableNode(id="node-id", name="events", has_children=False, representations=[]),
    ]
    return found


@pytest.mark.parametrize("enabled,message", [
    (False, "Compression enabled; chunks are compressed by a compression policy or on request"),
    (True, "Compression settings changed; only chunks compressed from now on use them"),
])
async def test_settings_use_review_transport(
    monkeypatch: pytest.MonkeyPatch, enabled: bool, message: str,
) -> None:
    selected = ConfigureCompression(AsyncMock(), catalog())
    assert isinstance(selected, TakesParams)
    assert isinstance(selected, Previews)
    assert isinstance(selected, RequiresReviewedPlan)
    assert (selected.requires, selected.destructive) == ("structure", False)
    assert selected.feature_requirements == ("timescaledb",)
    preview = AsyncMock(return_value=ActionPreview(summary="Review", fingerprint="a" * 64))
    execute = AsyncMock(return_value=plan(enabled=enabled))
    monkeypatch.setattr(compression_settings_action, "preview_compression_settings", preview)
    monkeypatch.setattr(compression_settings_action, "execute_compression_settings", execute)
    params = {"segment_by": "device", "order_by": "value desc"}
    await selected.preview("opaque", params)
    preview.assert_awaited_once_with(selected._session, 'odd"schema', "events", "device", "value desc")
    result = await selected.perform_reviewed("opaque", params, "a" * 64)
    execute.assert_awaited_once_with(selected._session, 'odd"schema', "events", "device", "value desc", "a" * 64)
    assert result.message == message
    assert result.reload_node_ids == ["schema-id", "node-id", TIMESCALE_SECTION_ID]


async def test_unreviewed_call_cannot_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    execute = AsyncMock()
    monkeypatch.setattr(compression_settings_action, "execute_compression_settings", execute)
    with pytest.raises(ActionRefused, match="Review"):
        await ConfigureCompression(AsyncMock(), catalog()).perform("opaque", {})
    execute.assert_not_called()


@pytest.mark.parametrize("params", [
    {"segment_by": 1}, {"order_by": "x" * 4097}, {"segment_by": "", "compress_chunk_time_interval": "1 day"},
])
async def test_form_is_validated_before_target_read(params: dict[str, object]) -> None:
    selected = ConfigureCompression(AsyncMock(), catalog())
    with pytest.raises(ValidationError):
        await selected.perform_reviewed("opaque", params, "a" * 64)
    selected._catalog.path_to.assert_not_called()


def test_form_takes_one_column_per_line() -> None:
    properties = ConfigureCompression.params_model.model_json_schema()["properties"]
    assert list(properties) == ["segment_by", "order_by"]
    assert all(properties[name]["x-ui-multiline"] is True for name in properties)
    assert all(properties[name]["default"] == "" for name in properties)


def test_settings_lookup_is_registered_and_unknown_names_stay_closed() -> None:
    registry = PostgresActions(AsyncMock(), AsyncMock())
    assert isinstance(registry.action(ConfigureCompression.name), ConfigureCompression)
    with pytest.raises(UnknownAction):
        registry.action("compress_chunk")


@pytest.mark.parametrize("planned,summary,expected", [
    (plan(unsegmented_unique=("value",)), 'Enable compression on "odd""schema"."events"', [
        'Time dimension: "observed_at"', "Compression is not enabled yet",
        'New segment by: "device"', 'New order by: "observed_at" DESC NULLS FIRST',
        'TimescaleDB recommends segmenting or ordering by the unique column "value"',
    ]),
    (plan(enabled=True, current_segment_by="device", current_order_by="observed_at DESC",
          segment_by=(), any_compressed=True),
     'Change the compression settings of "odd""schema"."events"', [
        'Time dimension: "observed_at"', "Current segment by: device",
        "Current order by: observed_at DESC", "New segment by: none",
        'New order by: "observed_at" DESC NULLS FIRST',
        "Already compressed chunks keep the settings they were compressed with",
    ]),
])
async def test_preview_renders_the_snapshot_plan(
    monkeypatch: pytest.MonkeyPatch, planned: CompressionSettingsPlan, summary: str, expected: list[str],
) -> None:
    planner = AsyncMock(return_value=planned)
    monkeypatch.setattr(compression_settings_action, "plan_compression_settings", planner)
    session = MagicMock()
    reader = session.inspection.return_value.__aenter__.return_value
    result = await compression_settings_action.preview_compression_settings(session, "lab", "events", "device", "")
    planner.assert_awaited_once_with(reader, "lab", "events", "device", "")
    assert result.summary == summary
    assert result.items == [*expected, planned.impact, planned.coordination]
    assert result.fingerprint == planned.fingerprint()


@pytest.mark.parametrize("error", [
    ActionRefused("not_applicable", 'This hypertable has no column "missing"'),
    AdapterError("unknown", "secret password"), ValueError("secret password"), TimeoutError(),
])
async def test_failed_plan_has_no_review_fingerprint(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(compression_settings_action, "plan_compression_settings", AsyncMock(side_effect=error))
    result = await compression_settings_action.preview_compression_settings(MagicMock(), "lab", "events", "", "")
    assert result.blocked and result.fingerprint is None and result.items == []
    assert "secret" not in result.summary


@pytest.mark.parametrize("outcome,reason", [
    (plan(), None),
    (ActionRefused("not_applicable", "Choose an owned hypertable with one time dimension"),
     "Choose an owned hypertable with one time dimension"),
    (AdapterError("network", "secret password"), compression_settings_action._unreadable()),
])
async def test_admission_plans_the_default_settings(
    monkeypatch: pytest.MonkeyPatch, outcome: object, reason: str | None,
) -> None:
    planner = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
    monkeypatch.setattr(compression_settings_action, "plan_compression_settings", planner)
    session = MagicMock()
    assert await compression_settings_action.compression_settings_admission(session, "lab", "events") == reason
    planner.assert_awaited_once_with(session.inspection.return_value.__aenter__.return_value, "lab", "events", "", "")
