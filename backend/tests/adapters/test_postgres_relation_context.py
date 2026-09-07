from unittest.mock import AsyncMock

import pytest

from app.adapters.features import SourceFeature
from app.adapters.postgres.relation_context import PostgresRelationContext
from app.adapters.postgres.timescale.profile import TimescaleProfile
from app.adapters.protocol import AdapterError


def _features(feature: SourceFeature) -> AsyncMock:
    features = AsyncMock()
    features.timescale.return_value = TimescaleProfile(feature)
    return features


async def test_absent_timescale_means_an_ordinary_relation_without_a_query() -> None:
    session = AsyncMock()
    context = PostgresRelationContext(
        session,
        _features(
            SourceFeature(code="timescaledb", title="TimescaleDB", state="absent")
        ),
    )

    schema = await context.schema("public")

    assert schema.known is True
    assert schema.specialization_for("events") is None
    assert schema.ordinary_statistics_are_valid_for("events") is True
    session.query.assert_not_awaited()


def _available_features() -> AsyncMock:
    return _features(
        SourceFeature(
            code="timescaledb", title="TimescaleDB", state="available",
            installed_version="2.18.0",
        )
    )


async def test_internal_membership_protects_relations_in_a_user_schema() -> None:
    session = AsyncMock()
    session.query.return_value = [
        {"relation_name": "chunk", "specialization": "internal"},
        {"relation_name": "materialized", "specialization": "timescale_hypertable"},
        {"relation_name": "materialized", "specialization": "internal"},
        {"relation_name": "materialized", "specialization": "internal"},
    ]
    context = await PostgresRelationContext(session, _available_features()).schema(
        "public"
    )
    assert context.internal_relations == {"chunk", "materialized"}
    assert context.specialization_for("materialized") is None
    assert context.structured_operations_reason("chunk") == (
        "TimescaleDB internal relations are read-only"
    )
    assert context.ordinary_statistics_are_valid_for("materialized") is False
    assert context.structured_operations_reason("ordinary") is None


@pytest.mark.parametrize(
    "failure", [ValueError("secret driver text"), AdapterError("unknown", "secret")]
)
async def test_failed_membership_read_preserves_reads_without_authorizing_writes(
    failure: Exception,
) -> None:
    session = AsyncMock()
    session.query.side_effect = failure
    context = await PostgresRelationContext(session, _available_features()).schema(
        "public"
    )
    assert context.known is False
    assert context.structured_operations_reason("ordinary") == (
        "TimescaleDB relation metadata could not be inspected"
    )


async def test_malformed_membership_cannot_be_ignored_as_an_ordinary_relation() -> None:
    session = AsyncMock()
    session.query.return_value = [{"relation_name": None, "specialization": "internal"}]
    context = await PostgresRelationContext(session, _available_features()).schema(
        "public"
    )
    assert context.known is False


async def test_dedicated_namespace_is_protected_even_without_inventory_rows() -> None:
    session = AsyncMock()
    session.query.return_value = []
    context = await PostgresRelationContext(session, _available_features()).schema(
        "_timescaledb_internal"
    )
    assert context.structured_operations_reason("compressed") == (
        "TimescaleDB internal relations are read-only"
    )


async def test_one_public_metadata_read_classifies_a_whole_schema() -> None:
    session = AsyncMock()
    session.query.return_value = [
        {
            "relation_name": "events",
            "specialization": "timescale_hypertable",
        },
        {
            "relation_name": "hourly_events",
            "specialization": "timescale_continuous_aggregate",
        },
    ]
    context = PostgresRelationContext(
        session,
        _features(
            SourceFeature(
                code="timescaledb",
                title="TimescaleDB",
                installed_version="2.18.0",
                state="available",
            )
        ),
    )

    schema = await context.schema("metrics")

    assert schema.specialization_for("events") is not None
    assert schema.specialization_for("events").kind == "timescale_hypertable"
    assert schema.specialization_for("hourly_events") is not None
    assert (
        schema.specialization_for("hourly_events").kind
        == "timescale_continuous_aggregate"
    )
    assert schema.ordinary_statistics_are_valid_for("events") is False
    assert schema.ordinary_statistics_are_valid_for("ordinary") is True
    assert schema.structured_operations_reason("events") == (
        "TimescaleDB relations are read-only in this version"
    )
    assert schema.structured_operations_reason("ordinary") is None
    session.query.assert_awaited_once()


async def test_unsupported_timescale_never_certifies_a_relation_as_ordinary() -> None:
    session = AsyncMock()
    context = PostgresRelationContext(
        session,
        _features(
            SourceFeature(
                code="timescaledb",
                title="TimescaleDB",
                installed_version="3.0.0",
                state="unsupported",
                reason="This major version is not supported",
            )
        ),
    )

    schema = await context.schema("public")

    assert schema.known is False
    assert schema.ordinary_statistics_are_valid_for("events") is False
    assert schema.structured_operations_reason("events") == (
        "This major version is not supported"
    )
    session.query.assert_not_awaited()
