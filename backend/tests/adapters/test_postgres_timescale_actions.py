from unittest.mock import AsyncMock

import pytest

from app.adapters.actions import ActionPreview
from app.adapters.catalog import ReportNode, SchemaNode, TableNode, ViewNode
from app.adapters.features import SourceFeature
from app.adapters.postgres.actions import PostgresActions
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.timescale import actions
from app.adapters.postgres.timescale.interval_action import SetChunkInterval
from app.adapters.postgres.timescale.plans import TimeDuration
from app.adapters.postgres.timescale.profile import TimescaleProfile
from app.adapters.protocol import AdapterError
from app.adapters.specializations import (
    TimescaleContinuousAggregate,
    TimescaleHypertable,
)


async def test_vocabulary_tracks_live_installation(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = AsyncMock(side_effect=[
        TimescaleProfile(SourceFeature(code="timescaledb", title="TimescaleDB", state="absent")),
        TimescaleProfile(SourceFeature(
            code="timescaledb", title="TimescaleDB", state="available", installed_version="2.18.0",
        )),
        TimescaleProfile(SourceFeature(
            code="timescaledb", title="TimescaleDB", state="unsupported",
            reason="Public TimescaleDB views are incomplete",
        )),
        TimescaleProfile(SourceFeature(code="timescaledb", title="TimescaleDB", state="absent")),
    ])
    monkeypatch.setattr(actions, "discover", probe)
    registry = PostgresActions(AsyncMock(), AsyncMock())
    for expected in (False, True, True, False):
        vocabulary = await registry.all_actions()
        assert (SetChunkInterval.name in {item.name for item in vocabulary}) is expected
        assert "create_schema" in {item.name for item in vocabulary}
    assert probe.await_count == 4
    assert SetChunkInterval in PostgresAdapter.action_types()


async def test_unknown_discovery_is_not_an_absent_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions, "discover", AsyncMock(return_value=TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state="unavailable", reason="Inspection unavailable",
    ))))
    with pytest.raises(AdapterError, match="could not be inspected"):
        await PostgresActions(AsyncMock(), AsyncMock()).all_actions()


@pytest.mark.parametrize("blocked", [False, True])
async def test_interval_offer_uses_live_plan_and_preserves_ordinary_guards(
    monkeypatch: pytest.MonkeyPatch, blocked: bool,
) -> None:
    catalog = AsyncMock()
    catalog.path_to.return_value = [
        SchemaNode(id="lab", name="lab", has_children=True, representations=[]),
        TableNode(
            id="lab.events", name="events", has_children=False, representations=[],
            specialization=TimescaleHypertable(),
        ),
    ]
    catalog.relation_action_reason.return_value = "Structured Timescale writes are disabled"
    preview = AsyncMock(return_value=ActionPreview(
        summary="Metadata lock permission unavailable" if blocked else "Review interval",
        blocked=blocked, fingerprint=None if blocked else "a" * 64,
    ))
    monkeypatch.setattr(actions, "preview_chunk_interval", preview)
    session = AsyncMock()
    registry = PostgresActions(session, catalog)
    offers = await registry.action_offers("lab.events")
    assert {item.name for item in offers.actions} == (set() if blocked else {SetChunkInterval.name})
    assert offers.reason_for("drop_relation") == "Structured Timescale writes are disabled"
    assert offers.reason_for(SetChunkInterval.name) == (
        "Metadata lock permission unavailable" if blocked else None
    )
    preview.assert_awaited_once_with(session, "lab", "events", TimeDuration(amount=1, unit="day"))
    catalog.path_to.assert_awaited_once_with("lab.events")


@pytest.mark.parametrize("system,specialized", [(False, False), (True, True)])
async def test_ordinary_and_internal_tables_never_offer_interval(
    monkeypatch: pytest.MonkeyPatch, system: bool, specialized: bool,
) -> None:
    catalog = AsyncMock()
    catalog.path_to.return_value = [
        SchemaNode(id="lab", name="lab", has_children=True, representations=[]),
        TableNode(
            id="lab.events", name="events", has_children=False, representations=[], is_system=system,
            specialization=TimescaleHypertable() if specialized else None,
        ),
    ]
    catalog.relation_action_reason.return_value = None
    preview = AsyncMock()
    monkeypatch.setattr(actions, "preview_chunk_interval", preview)
    offers = await PostgresActions(AsyncMock(), catalog).action_offers("lab.events")
    assert SetChunkInterval.name not in {item.name for item in offers.actions}
    preview.assert_not_awaited()


@pytest.mark.parametrize("path", [
    [SchemaNode(id="lab", name="lab", has_children=True, representations=[])],
    [
        SchemaNode(id="lab", name="lab", has_children=True, representations=[]),
        ViewNode(
            id="lab.events_hourly", name="events_hourly", has_children=False,
            representations=[], specialization=TimescaleContinuousAggregate(),
        ),
    ],
    [ReportNode(id="timescale.v1.chunks", name="Chunks", has_children=False, representations=[])],
])
async def test_non_hypertables_never_probe_interval_admission(
    monkeypatch: pytest.MonkeyPatch, path: list[object],
) -> None:
    catalog = AsyncMock()
    catalog.path_to.return_value = path
    catalog.schema_action_reason.return_value = None
    catalog.cascade_reason.return_value = None
    catalog.relation_action_reason.return_value = None
    preview = AsyncMock()
    monkeypatch.setattr(actions, "preview_chunk_interval", preview)
    offers = await PostgresActions(AsyncMock(), catalog).action_offers(path[-1].id)
    assert SetChunkInterval.name not in {item.name for item in offers.actions}
    assert offers.reason_for(SetChunkInterval.name) is None
    preview.assert_not_awaited()
