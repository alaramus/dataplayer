from unittest.mock import AsyncMock

import pytest

from app.adapters.actions import ActionPreview
from app.adapters.catalog import ReportNode, SchemaNode, TableNode, ViewNode
from app.adapters.features import SourceFeature
from app.adapters.postgres.actions import PostgresActions
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.timescale import actions
from app.adapters.postgres.timescale.age_policy_action import (
    RemoveCompressionPolicy,
    RemoveRetentionPolicy,
    SetCompressionPolicy,
    SetRetentionPolicy,
)
from app.adapters.postgres.timescale.age_policy_plan import (
    COMPRESSION,
    RETENTION,
    AgePolicySpec,
)
from app.adapters.postgres.timescale.chunk_storage_action import (
    CompressChunks,
    DecompressChunks,
)
from app.adapters.postgres.timescale.compression_settings_action import (
    ConfigureCompression,
)
from app.adapters.postgres.timescale.conversion_action import ConvertToHypertable
from app.adapters.postgres.timescale.interval_action import SetChunkInterval
from app.adapters.postgres.timescale.plans import TimeDuration
from app.adapters.postgres.timescale.profile import TimescaleProfile
from app.adapters.postgres.timescale.refresh_action import (
    RemoveRefreshPolicy,
    SetRefreshPolicy,
)
from app.adapters.protocol import AdapterError
from app.adapters.specializations import (
    TimescaleContinuousAggregate,
    TimescaleHypertable,
)

POLICY_ACTIONS = {
    SetRetentionPolicy.name, RemoveRetentionPolicy.name,
    SetCompressionPolicy.name, RemoveCompressionPolicy.name,
}
REFRESH_ACTIONS = {SetRefreshPolicy.name, RemoveRefreshPolicy.name}
STORAGE_ACTIONS = {CompressChunks.name, DecompressChunks.name}
MANAGEMENT = {
    SetChunkInterval.name, ConfigureCompression.name, ConvertToHypertable.name,
    *POLICY_ACTIONS, *REFRESH_ACTIONS, *STORAGE_ACTIONS,
}
NO_RETENTION = "This hypertable has no retention policy"
NOT_COMPRESSED = "Enable compression on this hypertable first"
NO_REFRESH = "This continuous aggregate has no refresh policy"

Answer = tuple[str | None, str | None]


def profile(state: str) -> TimescaleProfile:
    return TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state=state,  # type: ignore[arg-type]  # parametrized states
        installed_version=None if state == "absent" else "2.18.0",
        reason="Inspection unavailable" if state in {"unavailable", "unsupported"} else None,
    ))


def admission(by_kind: dict[str, Answer]) -> AsyncMock:
    async def admit(_session: object, spec: AgePolicySpec, _schema: str, _table: str) -> Answer:
        return by_kind[spec.kind]

    return AsyncMock(side_effect=admit)


@pytest.fixture
def policies(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    admit = admission({"retention": (None, NO_RETENTION), "compression": (NOT_COMPRESSED, NOT_COMPRESSED)})
    monkeypatch.setattr(actions, "age_policy_admission", admit)
    return admit


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    admit = AsyncMock(return_value=None)
    monkeypatch.setattr(actions, "compression_settings_admission", admit)
    return admit


@pytest.fixture
def refresh(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    admit = AsyncMock(return_value=(None, NO_REFRESH))
    monkeypatch.setattr(actions, "refresh_admission", admit)
    return admit


@pytest.fixture
def conversion(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    admit = AsyncMock(return_value=None)
    monkeypatch.setattr(actions, "conversion_admission", admit)
    return admit


@pytest.fixture(autouse=True)
def storage(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    admit = AsyncMock(return_value={"columnstore": None, "rowstore": None})
    monkeypatch.setattr(actions, "chunk_storage_admission", admit)
    return admit


SCHEMA = SchemaNode(id="lab", name="lab", has_children=True, representations=[])


def hypertable_path(*, system: bool = False, specialized: bool = True) -> list[object]:
    return [SCHEMA, TableNode(
        id="lab.events", name="events", has_children=False, representations=[], is_system=system,
        specialization=TimescaleHypertable() if specialized else None,
    )]


def aggregate_path(*, specialized: bool = True) -> list[object]:
    return [SCHEMA, ViewNode(
        id="lab.events_hourly", name="events_hourly", has_children=False, representations=[],
        specialization=TimescaleContinuousAggregate() if specialized else None,
    )]


async def test_vocabulary_tracks_live_installation(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = AsyncMock(side_effect=[profile("absent"), profile("available"), profile("unsupported"), profile("absent")])
    monkeypatch.setattr(actions, "discover", probe)
    registry = PostgresActions(AsyncMock(), AsyncMock())
    for expected in (False, True, True, False):
        names = {item.name for item in await registry.all_actions()}
        assert names & MANAGEMENT == (MANAGEMENT if expected else set())
        assert "create_schema" in names
    assert probe.await_count == 4
    assert {
        SetChunkInterval, ConfigureCompression, SetRetentionPolicy, RemoveRetentionPolicy,
        SetCompressionPolicy, RemoveCompressionPolicy, SetRefreshPolicy, RemoveRefreshPolicy,
        ConvertToHypertable, CompressChunks, DecompressChunks,
    } <= set(PostgresAdapter.action_types())


async def test_unknown_discovery_is_not_an_absent_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions, "discover", AsyncMock(return_value=profile("unavailable")))
    with pytest.raises(AdapterError, match="could not be inspected"):
        await PostgresActions(AsyncMock(), AsyncMock()).all_actions()


@pytest.mark.parametrize("blocked", [False, True])
@pytest.mark.usefixtures("conversion")
async def test_interval_offer_uses_live_plan_and_preserves_ordinary_guards(
    monkeypatch: pytest.MonkeyPatch, policies: AsyncMock, settings: AsyncMock, refresh: AsyncMock,
    storage: AsyncMock, blocked: bool,
) -> None:
    catalog = AsyncMock()
    catalog.path_to.return_value = hypertable_path()
    catalog.relation_action_reason.return_value = "Structured Timescale writes are disabled"
    preview = AsyncMock(return_value=ActionPreview(
        summary="Metadata lock permission unavailable" if blocked else "Review interval",
        blocked=blocked, fingerprint=None if blocked else "a" * 64,
    ))
    monkeypatch.setattr(actions, "preview_chunk_interval", preview)
    session = AsyncMock()
    registry = PostgresActions(session, catalog)
    offers = await registry.action_offers("lab.events")
    expected = {ConfigureCompression.name, SetRetentionPolicy.name, *STORAGE_ACTIONS}
    assert {item.name for item in offers.actions} == (expected if blocked else {SetChunkInterval.name, *expected})
    storage.assert_awaited_once_with(session, "lab", "events")
    assert offers.reason_for("drop_relation") == "Structured Timescale writes are disabled"
    assert offers.reason_for(SetChunkInterval.name) == (
        "Metadata lock permission unavailable" if blocked else None
    )
    assert offers.reason_for(RemoveRetentionPolicy.name) == NO_RETENTION
    assert offers.reason_for(SetCompressionPolicy.name) == NOT_COMPRESSED
    assert offers.reason_for(RemoveCompressionPolicy.name) == NOT_COMPRESSED
    assert all(offers.reason_for(name) is None for name in {*REFRESH_ACTIONS, ConvertToHypertable.name})
    preview.assert_awaited_once_with(session, "lab", "events", TimeDuration(amount=1, unit="day"))
    settings.assert_awaited_once_with(session, "lab", "events")
    assert [call.args for call in policies.await_args_list] == [
        (session, RETENTION, "lab", "events"), (session, COMPRESSION, "lab", "events"),
    ]
    refresh.assert_not_awaited()
    catalog.path_to.assert_awaited_once_with("lab.events")


@pytest.mark.usefixtures("policies", "refresh")
async def test_compression_settings_refusal_keeps_its_reason(
    monkeypatch: pytest.MonkeyPatch, settings: AsyncMock,
) -> None:
    catalog = AsyncMock()
    catalog.path_to.return_value = hypertable_path()
    catalog.relation_action_reason.return_value = None
    monkeypatch.setattr(actions, "preview_chunk_interval", AsyncMock(return_value=ActionPreview(
        summary="Review interval", fingerprint="a" * 64,
    )))
    settings.return_value = "This connection may not change compression settings"
    offers = await PostgresActions(AsyncMock(), catalog).action_offers("lab.events")
    assert ConfigureCompression.name not in {item.name for item in offers.actions}
    assert offers.reason_for(ConfigureCompression.name) == "This connection may not change compression settings"


@pytest.mark.parametrize("retention,offered", [
    ((None, None), {SetRetentionPolicy.name, RemoveRetentionPolicy.name}),
    (("The existing retention policy is paused; remove it before setting a new one", None),
     {RemoveRetentionPolicy.name}),
    (("This connection may not lock TimescaleDB public metadata",) * 2, set()),
])
@pytest.mark.usefixtures("settings")
async def test_policy_offers_carry_source_reasons_per_kind(
    monkeypatch: pytest.MonkeyPatch, retention: Answer, offered: set[str],
) -> None:
    catalog = AsyncMock()
    catalog.path_to.return_value = hypertable_path()
    catalog.relation_action_reason.return_value = None
    monkeypatch.setattr(actions, "preview_chunk_interval", AsyncMock(return_value=ActionPreview(
        summary="Review interval", fingerprint="a" * 64,
    )))
    monkeypatch.setattr(actions, "age_policy_admission", admission({
        "retention": retention, "compression": (None, None),
    }))
    offers = await PostgresActions(AsyncMock(), catalog).action_offers("lab.events")
    names = {item.name for item in offers.actions}
    assert names & {SetRetentionPolicy.name, RemoveRetentionPolicy.name} == offered
    assert {SetCompressionPolicy.name, RemoveCompressionPolicy.name} <= names
    assert offers.reason_for(SetRetentionPolicy.name) == retention[0]
    assert offers.reason_for(RemoveRetentionPolicy.name) == retention[1]


@pytest.mark.parametrize("answer,offered", [
    ((None, NO_REFRESH), {SetRefreshPolicy.name}),
    ((None, None), REFRESH_ACTIONS),
    (("The existing refresh policy is paused; remove it before setting a new one", None),
     {RemoveRefreshPolicy.name}),
])
@pytest.mark.usefixtures("conversion")
async def test_continuous_aggregate_offers_only_refresh_policy_commands(
    monkeypatch: pytest.MonkeyPatch, policies: AsyncMock, settings: AsyncMock,
    answer: Answer, offered: set[str],
) -> None:
    catalog = AsyncMock()
    catalog.path_to.return_value = aggregate_path()
    catalog.relation_action_reason.return_value = "Structured Timescale writes are disabled"
    preview = AsyncMock()
    monkeypatch.setattr(actions, "preview_chunk_interval", preview)
    admit = AsyncMock(return_value=answer)
    monkeypatch.setattr(actions, "refresh_admission", admit)
    session = AsyncMock()
    offers = await PostgresActions(session, catalog).action_offers("lab.events_hourly")
    assert {item.name for item in offers.actions} & MANAGEMENT == offered
    assert offers.reason_for(SetRefreshPolicy.name) == answer[0]
    assert offers.reason_for(RemoveRefreshPolicy.name) == answer[1]
    assert offers.reason_for("drop_relation") == "Structured Timescale writes are disabled"
    admit.assert_awaited_once_with(session, "lab", "events_hourly")
    preview.assert_not_awaited()
    policies.assert_not_awaited()
    settings.assert_not_awaited()


@pytest.mark.parametrize("state", ["absent", "unavailable"])
async def test_ordinary_table_without_timescale_costs_one_discovery(
    monkeypatch: pytest.MonkeyPatch, conversion: AsyncMock, state: str,
) -> None:
    catalog = AsyncMock()
    catalog.path_to.return_value = hypertable_path(specialized=False)
    catalog.relation_action_reason.return_value = None
    probe = AsyncMock(return_value=profile(state))
    monkeypatch.setattr(actions, "discover", probe)
    offers = await PostgresActions(AsyncMock(), catalog).action_offers("lab.events")
    assert ConvertToHypertable.name not in {item.name for item in offers.actions}
    assert offers.reason_for(ConvertToHypertable.name) is None
    probe.assert_awaited_once()
    conversion.assert_not_awaited()


@pytest.mark.parametrize("guard,admitted,reason", [
    (None, None, None),
    (None, "This table is not empty; only empty tables are converted here",
     "This table is not empty; only empty tables are converted here"),
    ("Something else is built on this relation", None, "Something else is built on this relation"),
])
async def test_ordinary_table_offers_conversion_behind_its_ordinary_guard(
    monkeypatch: pytest.MonkeyPatch, conversion: AsyncMock,
    guard: str | None, admitted: str | None, reason: str | None,
) -> None:
    catalog = AsyncMock()
    catalog.path_to.return_value = hypertable_path(specialized=False)
    catalog.relation_action_reason.return_value = guard
    monkeypatch.setattr(actions, "discover", AsyncMock(return_value=profile("available")))
    conversion.return_value = admitted
    session = AsyncMock()
    offers = await PostgresActions(session, catalog).action_offers("lab.events")
    assert (ConvertToHypertable.name in {item.name for item in offers.actions}) is (reason is None)
    assert offers.reason_for(ConvertToHypertable.name) == reason
    if guard is None:
        conversion.assert_awaited_once_with(session, "lab", "events")
    else:
        conversion.assert_not_awaited()


@pytest.mark.parametrize("path", [
    hypertable_path(system=True), aggregate_path(specialized=False), [SCHEMA],
    [ReportNode(id="timescale.v1.chunks", name="Chunks", has_children=False, representations=[])],
])
async def test_other_nodes_never_probe_management_admission(
    monkeypatch: pytest.MonkeyPatch, policies: AsyncMock, settings: AsyncMock, refresh: AsyncMock,
    conversion: AsyncMock, storage: AsyncMock, path: list[object],
) -> None:
    catalog = AsyncMock()
    catalog.path_to.return_value = path
    catalog.schema_action_reason.return_value = None
    catalog.cascade_reason.return_value = None
    catalog.relation_action_reason.return_value = None
    preview = AsyncMock()
    probe = AsyncMock(return_value=profile("available"))
    monkeypatch.setattr(actions, "preview_chunk_interval", preview)
    monkeypatch.setattr(actions, "discover", probe)
    offers = await PostgresActions(AsyncMock(), catalog).action_offers(path[-1].id)
    assert not MANAGEMENT & {item.name for item in offers.actions}
    assert all(offers.reason_for(name) is None for name in MANAGEMENT)
    for admission_mock in (preview, policies, settings, refresh, conversion, storage, probe):
        admission_mock.assert_not_awaited()
