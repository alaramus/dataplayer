from unittest.mock import AsyncMock

import pytest

from app.adapters.features import SourceFeature
from app.adapters.postgres.report_registry import resolve_report
from app.adapters.postgres.timescale.profile import TimescaleProfile
from app.adapters.postgres.timescale.report_access import require_report
from app.adapters.postgres.timescale.reports import REPORTS, TimescaleReport
from app.adapters.protocol import AdapterError

OPTIONAL_REPORTS = [report for report in REPORTS if isinstance(report, TimescaleReport)]


@pytest.mark.parametrize("report", OPTIONAL_REPORTS, ids=lambda report: report.key)
async def test_optional_view_requires_extension_membership_and_every_used_column(
    report: TimescaleReport,
) -> None:
    session = AsyncMock()
    session.query.side_effect = [
        [{"column_name": name} for name in report.required_columns], [],
    ]
    await require_report(session, report)
    lookup, probe = session.query.await_args_list
    query, params = lookup.args
    assert "dependency.deptype = 'e'" in query
    assert "extension.extname = 'timescaledb'" in query
    assert "namespace.nspname = 'timescaledb_information'" in query
    assert params == (
        report.public_view, list(report.required_columns), len(report.required_columns) + 1,
    )
    assert lookup.kwargs["inspection"] is True
    assert probe.kwargs["inspection"] is True
    assert probe.args[0].endswith("AS report LIMIT 0")
    assert report.statement.as_string() in probe.args[0]


@pytest.mark.parametrize("report", OPTIONAL_REPORTS, ids=lambda report: report.key)
async def test_missing_column_refuses_before_reading_optional_view(
    report: TimescaleReport,
) -> None:
    session = AsyncMock()
    session.query.return_value = [
        {"column_name": name} for name in report.required_columns[:-1]
    ]
    with pytest.raises(ValueError, match="lacks the public API"):
        await require_report(session, report)
    session.query.assert_awaited_once()


async def test_same_named_view_without_extension_membership_is_refused() -> None:
    session = AsyncMock()
    session.query.return_value = []
    with pytest.raises(ValueError, match="lacks the public API"):
        await require_report(session, OPTIONAL_REPORTS[0])
    session.query.assert_awaited_once()


async def test_permission_failure_is_not_an_empty_inventory() -> None:
    report = OPTIONAL_REPORTS[0]
    session = AsyncMock()
    session.query.side_effect = [
        [{"column_name": name} for name in report.required_columns],
        AdapterError("config", "driver detail"),
    ]
    with pytest.raises(ValueError, match="cannot be inspected") as failure:
        await require_report(session, report)
    assert "driver detail" not in str(failure.value)


async def test_connection_failure_remains_a_connection_failure() -> None:
    session = AsyncMock()
    session.query.side_effect = AdapterError("network", "Connection failed")
    with pytest.raises(AdapterError):
        await require_report(session, OPTIONAL_REPORTS[0])


async def test_other_report_remains_readable_when_one_api_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.adapters.postgres.report_registry.discover",
        AsyncMock(return_value=TimescaleProfile(SourceFeature(
            code="timescaledb", title="TimescaleDB", state="available",
            installed_version="2.18.0",
        ))),
    )
    session = AsyncMock()
    session.query.return_value = []
    with pytest.raises(ValueError, match="lacks the public API"):
        await resolve_report(session, REPORTS[2].node_id)
    session.query.reset_mock()
    session.query.side_effect = [
        [{"column_name": name} for name in REPORTS[0].required_columns], [],
    ]
    assert await resolve_report(session, REPORTS[0].node_id) == REPORTS[0]
    assert session.query.await_count == 2
