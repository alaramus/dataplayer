import asyncio
from unittest.mock import AsyncMock

import pytest

from app.adapters.postgres.features import PostgresFeatures
from app.adapters.postgres.timescale.profile import discover
from app.adapters.protocol import AdapterError

BASELINE_COLUMNS = [
    {"view_name": "hypertables", "column_name": "hypertable_schema"},
    {"view_name": "hypertables", "column_name": "hypertable_name"},
    {"view_name": "continuous_aggregates", "column_name": "view_schema"},
    {"view_name": "continuous_aggregates", "column_name": "view_name"},
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
