import pytest

from app.adapters.actions import ActionRefused
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.interval_plan import plan_chunk_interval
from app.adapters.postgres.timescale.plans import TimeDuration
from compatibility.timescale.source import TimescaleSource


@pytest.mark.parametrize("schema,table", [("lab", "metrics"), ("other", "metrics"), ("lab", "empty_metrics")])
async def test_planning_keeps_the_source_interval_unchanged(
    source: TimescaleSource, schema: str, table: str,
) -> None:
    session = source.session()
    statement = """
        SELECT time_interval::text AS interval FROM timescaledb_information.dimensions
        WHERE hypertable_schema = %s AND hypertable_name = %s ORDER BY dimension_number
    """
    before = await session.query(statement, (schema, table), inspection=True)
    assert before
    planned = await plan_chunk_interval(session, schema, table, TimeDuration(amount=2, unit="day"))
    after = await session.query(statement, (schema, table), inspection=True)
    assert after == before
    assert planned.target.schema_name == schema
    assert planned.target.table_name == table
    assert planned.target.current_interval == before[0]["interval"]
    assert planned.strategy.extension_version == source.version
    repeated = await plan_chunk_interval(session, schema, table, TimeDuration(amount=2, unit="day"))
    repeated.require_unchanged(planned.fingerprint())


@pytest.mark.parametrize("schema,table", [
    ("public", "ordinary"), ("lab", "integer_metrics"), ("lab", "hourly"),
    ("lab", "metrics'; SELECT 1; --"),
])
async def test_planning_refuses_ineligible_targets(
    source: TimescaleSource, schema: str, table: str,
) -> None:
    with pytest.raises(ActionRefused):
        await plan_chunk_interval(source.session(), schema, table, TimeDuration(amount=2, unit="day"))


async def test_reader_cannot_plan_an_owner_operation(source: TimescaleSource) -> None:
    session = PostgresSession(source.options(user="fixture_reader"))
    with pytest.raises(ActionRefused):
        await plan_chunk_interval(session, "lab", "metrics", TimeDuration(amount=2, unit="day"))


async def test_plain_database_has_no_interval_plan(source: TimescaleSource) -> None:
    with pytest.raises(ActionRefused):
        await plan_chunk_interval(
            source.session(database="plain_fixture"), "public", "ordinary",
            TimeDuration(amount=2, unit="day"),
        )
