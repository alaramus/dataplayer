from unittest.mock import AsyncMock

from app.adapters.features import SourceFeature
from app.adapters.postgres.relation_context import PostgresRelationContext
from app.adapters.postgres.timescale.profile import TimescaleProfile


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
