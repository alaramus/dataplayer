"""A bounded, read-only view of Redis server information and safe settings."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from redis.exceptions import ResponseError

from app.adapters.catalog import ReportNode
from app.adapters.content import NodeRepresentation
from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import NodeNotFound
from app.adapters.redis.session import RedisSession, text
from app.adapters.report_rows import export as export_report_rows
from app.adapters.report_rows import page as report_page
from app.core.translation import N_, say

SECTION_ID = "\\system"
SECTION_TITLE = N_("System")
SECTION_DESCRIPTION = N_("What this server says about itself")
SETTING_COLUMN = N_("Setting")
VALUE_COLUMN = N_("Value")

_TABLE = NodeRepresentation(kind="table", title=N_("View as table"))


@dataclass(frozen=True)
class SystemReport:
    key: str
    title: str
    description: str
    info_sections: tuple[str, ...] = ()
    settings: tuple[str, ...] = ()
    refresh_seconds: int | None = None

    @property
    def node_id(self) -> str:
        return f"{SECTION_ID}/{self.key}"


_INFO_FIELDS: dict[str, tuple[str, ...]] = {
    "server": (
        "redis_version",
        "redis_mode",
        "os",
        "arch_bits",
        "process_id",
        "tcp_port",
        "uptime_in_seconds",
        "uptime_in_days",
    ),
    "clients": ("connected_clients", "blocked_clients", "tracking_clients"),
    "memory": (
        "used_memory_human",
        "used_memory_rss_human",
        "used_memory_peak_human",
        "maxmemory_human",
        "maxmemory_policy",
        "allocator",
    ),
    "persistence": (
        "rdb_bgsave_in_progress",
        "rdb_last_bgsave_status",
        "aof_enabled",
        "aof_rewrite_in_progress",
        "aof_last_write_status",
    ),
    "replication": (
        "role",
        "connected_replicas",
        "connected_slaves",
        "master_link_status",
        "master_sync_in_progress",
    ),
    "stats": (
        "instantaneous_ops_per_sec",
        "total_commands_processed",
        "total_connections_received",
        "rejected_connections",
        "expired_keys",
        "evicted_keys",
        "keyspace_hits",
        "keyspace_misses",
    ),
}

_SAFE_SETTINGS = (
    "databases",
    "timeout",
    "tcp-keepalive",
    "maxclients",
    "maxmemory",
    "maxmemory-policy",
    "appendonly",
    "appendfsync",
    "save",
    "protected-mode",
)

REPORTS: tuple[SystemReport, ...] = (
    SystemReport(
        key="server",
        title=N_("Server"),
        description=N_("Version, uptime, clients, memory, persistence and replication"),
        info_sections=tuple(_INFO_FIELDS),
        refresh_seconds=10,
    ),
    SystemReport(
        key="settings",
        title=N_("Settings"),
        description=N_("Selected non-secret configuration values reported by Redis"),
        settings=_SAFE_SETTINGS,
    ),
)
_BY_ID = {report.node_id: report for report in REPORTS}


def is_section(node_id: str | None) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str | None) -> bool:
    return (node_id or "").startswith(SECTION_ID + "/")


def report_for(node_id: str | None) -> SystemReport | None:
    return _BY_ID.get(node_id or "")


def section_node() -> ReportNode:
    return ReportNode(
        id=SECTION_ID,
        name=say(SECTION_TITLE),
        description=say(SECTION_DESCRIPTION),
        has_children=True,
        representations=[],
    )


def report_node(report: SystemReport) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=say(report.title),
        description=say(report.description),
        has_children=False,
        representations=[_TABLE.model_copy(update={"title": say(_TABLE.title)})],
    )


class RedisReports:
    def __init__(self, session: RedisSession) -> None:
        self._session = session

    async def fetch(self, request: FetchRequest) -> FetchResult:
        report = report_for(request.node_id)
        if report is None:
            raise NodeNotFound(request.node_id)
        rows = await self._rows(report)
        reason = say(
            '"{title}" is a report and holds no rows of its own',
            title=say(report.title),
        )
        return report_page(
            request,
            rows,
            name_column=say(SETTING_COLUMN),
            value_column=say(VALUE_COLUMN),
            read_only_reason=reason,
            refresh_seconds=report.refresh_seconds,
            page_commands=["download", "chart", "share"],
        )

    async def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        report = report_for(request.node_id)
        if report is None:
            raise NodeNotFound(request.node_id)
        rows = await self._rows(report)
        selected = export_report_rows(
            request,
            rows,
            name_column=say(SETTING_COLUMN),
            value_column=say(VALUE_COLUMN),
        )
        for start in range(0, len(selected), EXPORT_BATCH_SIZE):
            yield ExportBatch(rows=selected[start : start + EXPORT_BATCH_SIZE])

    async def _rows(self, report: SystemReport) -> list[tuple[str, str]]:
        if report.settings:
            return await self._settings(report.settings)

        rows: list[tuple[str, str]] = []
        async with self._session.connection() as client:
            for section in report.info_sections:
                try:
                    info: dict[str, Any] = await client.info(section)
                except ResponseError:
                    rows.append(
                        (f"{section}.INFO", say("INFO is unavailable for this Redis user"))
                    )
                    continue
                for field in _INFO_FIELDS[section]:
                    value = info.get(field)
                    if value is not None and not isinstance(value, dict | list | tuple):
                        rows.append((f"{section}.{field}", _display(value)))
        return rows

    async def _settings(self, names: tuple[str, ...]) -> list[tuple[str, str]]:
        async with self._session.connection() as client:
            pipeline = client.pipeline(transaction=False)
            for name in names:
                pipeline.config_get(name)
            try:
                answers = await pipeline.execute()
            except ResponseError:
                return [
                    (
                        "CONFIG GET",
                        say("Configuration commands are unavailable on this server"),
                    )
                ]

        rows: list[tuple[str, str]] = []
        for name, answer in zip(names, answers, strict=True):
            values = {text(key): value for key, value in dict(answer).items()}
            if name in values:
                rows.append((name, _display(values[name])))
        return rows


def _display(value: object) -> str:
    if isinstance(value, bytes):
        return text(value)
    if isinstance(value, list | tuple):
        return " ".join(_display(item) for item in value)
    return str(value)
