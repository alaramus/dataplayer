from unittest.mock import AsyncMock

import pytest

from app.adapters.fetch import FetchRequest, Sort
from app.adapters.postgres.fetch import PostgresFetch
from app.adapters.postgres.timescale.reports import REPORTS
from tests.adapters.test_postgres_timescale_reports import discovery


async def test_job_counters_keep_precision_nulls_and_numeric_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery(monkeypatch, "available")
    report = next(report for report in REPORTS if report.public_view == "job_stats")
    session = AsyncMock()
    session.describe.return_value = [
        ("job_id", 20), ("total_runs", 20), ("last_successful_finish", 25),
        ("last_run_duration", 25),
    ]
    session.query.side_effect = [
        [
            {"oid": 20, "sql_type": "bigint", "type_name": "int8", "type_category": "N"},
            {"oid": 25, "sql_type": "text", "type_name": "text", "type_category": "S"},
        ],
        [{"job_id": 1000, "total_runs": 9007199254740993,
          "last_successful_finish": "-infinity", "last_run_duration": None}],
    ]
    result = await PostgresFetch(session).fetch(FetchRequest(
        node_id=report.node_id, sort=[Sort(column="total_runs", descending=True)],
    ))
    assert result.rows == [["1000", "9007199254740993", "-infinity", None]]
    statement = session.query.await_args.args[0]
    assert 'ORDER BY "total_runs" DESC, "job_id" ASC LIMIT %s OFFSET %s' in statement
    assert '"total_runs"::text' not in statement
    assert not result.update_supported and result.row_handles == [None]


def test_job_statistics_projection_excludes_config_and_error_messages() -> None:
    report = next(report for report in REPORTS if report.public_view == "job_stats")
    statement = report.statement.as_string()
    assert '"last_run_duration"::text' in statement
    assert '"next_start"::text' in statement
    assert {"total_runs", "total_successes", "total_failures"} <= set(report.required_columns)
    for forbidden in ("config", "err_message", "job_errors", "job_history", "_timescaledb"):
        assert forbidden not in statement
