import re

import pytest

from app.adapters.postgres.timescale.policy_projection import (
    INTEGER_TEXT,
    INTERVAL_TEXT,
)
from app.adapters.postgres.timescale.reports import REPORTS


def test_jobs_project_only_typed_policy_parameters_after_routine_verification() -> None:
    report = next(report for report in REPORTS if report.public_view == "jobs")
    statement = report.statement.as_string()
    assert "config" in report.required_columns
    assert '"config",' not in statement
    assert "source.config ->>" in statement
    assert "e.extname = 'timescaledb'" in statement
    assert "d.deptype = 'e'" in statement
    assert "p.prokind = 'p'" in statement
    assert "p.proargtypes = '23 3802'" in statement
    assert "OPERATOR(pg_catalog.~)" in statement
    assert INTERVAL_TEXT in statement and INTEGER_TEXT in statement
    # No cast decides validity, so nothing here needs PostgreSQL 16.
    assert "pg_input_is_valid" not in statement
    for key in ("drop_after", "compress_after", "start_offset", "end_offset"):
        assert f'AS "{key}_integer"' in statement
        assert f'AS "{key}_interval"' in statement
    assert "err_message" not in statement
    assert "job_errors" not in statement


@pytest.mark.parametrize("value", [
    "1 mon", "10 years", "7 days", "01:00:00", "-00:00:01", "00:00:01.500000",
    "1 year 2 mons 3 days 04:05:06",
])
def test_postgresql_interval_output_is_recognised(value: str) -> None:
    assert re.fullmatch(INTERVAL_TEXT, value)


@pytest.mark.parametrize("value", [
    "", "secret-not-an-interval", "10 parsecs", "999999999 years", "P1Y2M3D",
    "@ 1 year ago", "1 day; DROP TABLE x",
])
def test_anything_else_is_not_recognised_as_an_interval(value: str) -> None:
    # A count wide enough to overflow the type is refused too: whatever matches
    # must survive the cast that follows it.
    assert re.fullmatch(INTERVAL_TEXT, value) is None


@pytest.mark.parametrize("value,recognised", [
    ("9007199254740993", True), ("-42", True),
    ("9223372036854775808", False), ("1.5", False), ("", False),
])
def test_only_bigint_sized_digits_are_recognised(value: str, recognised: bool) -> None:
    assert bool(re.fullmatch(INTEGER_TEXT, value)) is recognised
