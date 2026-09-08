import json

import pytest
from psycopg import sql

from app.adapters.fetch import FetchRequest, ScalarFilter
from app.adapters.postgres.timescale.policy_projection import policy_columns
from app.adapters.postgres.timescale.reports import REPORTS
from compatibility.timescale.source import TimescaleSource


@pytest.mark.parametrize(("routine", "kind", "key"), [
    ("policy_retention", "retention", "drop_after"),
    ("policy_compression", "compression", "compress_after"),
    ("policy_refresh_continuous_aggregate", "refresh", "start_offset"),
])
async def test_policy_projection_validates_values_without_exposing_config(
    source: TimescaleSource, routine: str, kind: str, key: str,
) -> None:
    session = source.session()
    statement = sql.SQL("""SELECT {} FROM (
        SELECT %s::text AS proc_schema, %s::text AS proc_name, %s::jsonb AS config
    ) AS source""").format(sql.SQL(", ").join(policy_columns())).as_string()
    for value, interval, integer in [
        ("1 mon", "1 mon", None),
        (9007199254740993, None, 9007199254740993),
        ("secret-not-an-interval", None, None),
        ({"secret": "hidden"}, None, None),
        (9223372036854775808, None, None),
        (None, None, None),
    ]:
        rows = await session.query(statement, (
            "_timescaledb_functions", routine,
            json.dumps({key: value, "password": "secret-sentinel"}),
        ))
        assert len(rows) == 1
        assert rows[0]["policy_kind"] == kind
        assert rows[0][f"{key}_interval"] == interval
        assert rows[0][f"{key}_integer"] == integer
        assert "secret" not in str(rows)
    spoofed = await session.query(statement, (
        "public", routine, json.dumps({key: "1 mon"}),
    ))
    assert all(value is None for value in spoofed[0].values())


async def test_retention_policy_report_exposes_interval_without_raw_config(
    source: TimescaleSource,
) -> None:
    report = next(report for report in REPORTS if report.public_view == "jobs")
    result = await source.adapter(user="fixture_reader").fetch(FetchRequest(
        node_id=report.node_id,
        filters=[
            ScalarFilter(column="hypertable_schema", op="eq", value="lab"),
            ScalarFilter(column="hypertable_name", op="eq", value="metrics"),
        ],
    ))
    assert len(result.rows) == 1
    row = dict(zip((column.name for column in result.columns), result.rows[0], strict=True))
    assert "config" not in row
    assert row["policy_kind"] == "retention"
    assert row["drop_after_interval"] == "10 years"
    assert row["drop_after_integer"] is None
    assert row["compress_after_interval"] is None
