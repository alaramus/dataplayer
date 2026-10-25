"""Redis's fixed reports expose only the server facts the catalog names."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.redis.reports import REPORTS, RedisReports
from app.adapters.redis.session import RedisSession


class _Pipeline:
    def __init__(self) -> None:
        self.names: list[str] = []

    def config_get(self, name: str) -> _Pipeline:
        self.names.append(name)
        return self

    async def execute(self) -> list[dict[bytes, bytes]]:
        return [{name.encode(): f"value-{name}".encode()} for name in self.names]


class _Client:
    def __init__(self) -> None:
        self.pipeline_ = _Pipeline()

    async def info(self, section: str) -> dict[str, object]:
        if section == "server":
            return {
                "redis_version": "7.2.4",
                "redis_mode": "standalone",
                "config_file": "/private/redis.conf",
            }
        return {}

    def pipeline(self, *, transaction: bool) -> _Pipeline:
        assert transaction is False
        return self.pipeline_


class _Session:
    def __init__(self) -> None:
        self.client = _Client()

    @asynccontextmanager
    async def connection(self, database: int | None = None) -> AsyncIterator[_Client]:
        del database
        yield self.client


def _reports(session: _Session) -> RedisReports:
    return RedisReports(cast(RedisSession, session))


async def test_server_report_uses_a_fixed_info_allowlist_and_is_read_only() -> None:
    session = _Session()
    report = _reports(session)

    page = await report.fetch(FetchRequest(node_id=REPORTS[0].node_id))

    assert [row for row in page.rows if row[0] == "server.redis_version"] == [
        ["server.redis_version", "7.2.4"]
    ]
    assert all("config_file" not in str(row) for row in page.rows)
    assert page.record_supported is False
    assert page.update_supported is False
    assert page.insert_supported is False
    assert page.delete_supported is False
    assert page.refresh_seconds == 10
    assert page.page_commands == ["download", "chart", "share"]


async def test_settings_report_requests_only_non_secret_config_keys() -> None:
    session = _Session()

    page = await _reports(session).fetch(FetchRequest(node_id=REPORTS[1].node_id))

    requested = session.client.pipeline_.names
    assert "maxmemory" in requested
    assert "appendonly" in requested
    assert not {"requirepass", "masterauth", "user", "aclfile", "dir"} & set(requested)
    assert [row for row in page.rows if row[0] == "databases"] == [
        ["databases", "value-databases"]
    ]


async def test_report_rows_filter_sort_and_export_by_the_displayed_columns() -> None:
    reports = _reports(_Session())
    request = FetchRequest(
        node_id=REPORTS[0].node_id,
        filters=[ScalarFilter(column="Setting", op="contains", value="redis_mode")],
        sort=[Sort(column="Value", descending=True)],
    )

    page = await reports.fetch(request)
    batches = [
        batch
        async for batch in reports.export_rows(
            ExportRequest(
                node_id=REPORTS[0].node_id,
                columns=["Value"],
                filters=request.filters,
                sort=request.sort,
            )
        )
    ]

    assert page.rows == [["server.redis_mode", "standalone"]]
    assert [row for batch in batches for row in batch.rows] == [["standalone"]]
