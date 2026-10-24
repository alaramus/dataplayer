import asyncio
from unittest.mock import AsyncMock

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.features import SourceFeature
from app.adapters.postgres.features import PostgresFeatures
from app.adapters.postgres.timescale.profile import (
    TimescaleProfile,
    discover,
    require_available,
)
from app.adapters.protocol import AdapterError

BASELINE_COLUMNS = [
    {"view_name": "hypertables", "column_name": "hypertable_schema"},
    {"view_name": "hypertables", "column_name": "hypertable_name"},
    {"view_name": "continuous_aggregates", "column_name": "view_schema"},
    {"view_name": "continuous_aggregates", "column_name": "view_name"},
    {
        "view_name": "continuous_aggregates",
        "column_name": "materialization_hypertable_schema",
    },
    {
        "view_name": "continuous_aggregates",
        "column_name": "materialization_hypertable_name",
    },
    {"view_name": "chunks", "column_name": "chunk_schema"},
    {"view_name": "chunks", "column_name": "chunk_name"},
]


async def test_absent_extension_is_distinct_from_failed_discovery() -> None:
    session = AsyncMock()
    session.query.return_value = []

    profile = await discover(session)

    assert profile.feature.state == "absent"
    assert profile.feature.installed_version is None


async def test_supported_extension_requires_the_baseline_public_views() -> None:
    session = AsyncMock()
    session.query.side_effect = [
        [{"oid": 42, "version": "2.18.0"}],
        BASELINE_COLUMNS,
        [],
    ]

    profile = await discover(session)

    assert profile.available is True
    assert profile.feature.installed_version == "2.18.0"


async def test_missing_baseline_column_makes_the_version_unsupported() -> None:
    session = AsyncMock()
    session.query.side_effect = [
        [{"oid": 42, "version": "2.18.0"}],
        BASELINE_COLUMNS[:-1],
    ]

    profile = await discover(session)

    assert profile.feature.state == "unsupported"
    assert profile.feature.reason is not None


async def test_inaccessible_public_views_make_metadata_unavailable() -> None:
    session = AsyncMock()
    session.query.side_effect = [
        [{"oid": 42, "version": "2.18.0"}],
        BASELINE_COLUMNS,
        ValueError("driver detail must not escape"),
    ]

    profile = await discover(session)

    assert profile.feature.state == "unavailable"
    assert profile.feature.installed_version == "2.18.0"
    assert profile.feature.reason == (
        "This connection may not inspect TimescaleDB metadata"
    )


async def test_unknown_major_version_is_not_claimed_as_supported() -> None:
    session = AsyncMock()
    session.query.return_value = [{"oid": 42, "version": "3.0.0"}]

    profile = await discover(session)

    assert profile.feature.state == "unsupported"
    session.query.assert_awaited_once()


async def test_permission_refusal_is_an_unavailable_feature() -> None:
    session = AsyncMock()
    session.query.side_effect = ValueError("driver detail must not escape")

    profile = await discover(session)

    assert profile.feature.state == "unavailable"
    assert profile.feature.reason == (
        "This connection may not inspect installed extensions"
    )


async def test_network_failure_remains_a_source_failure() -> None:
    session = AsyncMock()
    session.query.side_effect = AdapterError("network", "Could not reach the server")

    with pytest.raises(AdapterError) as caught:
        await discover(session)

    assert caught.value.error_kind == "network"


async def test_one_adapter_shares_an_in_flight_profile() -> None:
    session = AsyncMock()
    session.query.return_value = []
    features = PostgresFeatures(session)

    first, second = await asyncio.gather(features.timescale(), features.timescale())

    assert first is second
    session.query.assert_awaited_once()



async def test_a_callers_reader_is_used_inline_and_its_answer_kept() -> None:
    session = AsyncMock()
    reader = AsyncMock()
    reader.query.return_value = []
    features = PostgresFeatures(session)

    first = await features.timescale(reader)
    second = await features.timescale()

    assert first is second
    reader.query.assert_awaited_once()
    session.query.assert_not_awaited()


async def test_a_cancelled_reader_does_not_spoil_discovery_for_others() -> None:
    session = AsyncMock()
    session.query.return_value = []
    reader = AsyncMock()
    started = asyncio.Event()

    async def hang(*_: object, **__: object) -> list[dict[str, object]]:
        started.set()
        await asyncio.Event().wait()
        return []

    reader.query.side_effect = hang
    features = PostgresFeatures(session)
    batch = asyncio.create_task(features.timescale(reader))
    await started.wait()
    batch.cancel()
    with pytest.raises(asyncio.CancelledError):
        await batch

    profile = await features.timescale()

    assert profile.feature.code == "timescaledb"
    session.query.assert_awaited_once()

def test_an_available_profile_yields_the_installed_version() -> None:
    profile = TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state="available", installed_version="2.30.0",
    ))

    assert require_available(profile) == "2.30.0"


@pytest.mark.parametrize("feature,message", [
    (SourceFeature(code="timescaledb", title="TimescaleDB", state="absent"), "is not installed"),
    (SourceFeature(code="timescaledb", title="TimescaleDB", state="unsupported",
                   installed_version="3.0.0", reason="This TimescaleDB major version is not supported"),
     "major version is not supported"),
    (SourceFeature(code="timescaledb", title="TimescaleDB", state="unavailable",
                   reason="This connection may not inspect TimescaleDB metadata"), "may not inspect"),
])
def test_an_unusable_profile_refuses_with_the_reason_discovery_found(
    feature: SourceFeature, message: str,
) -> None:
    with pytest.raises(ActionRefused, match=message) as caught:
        require_available(TimescaleProfile(feature))

    assert caught.value.reason == "not_applicable"
