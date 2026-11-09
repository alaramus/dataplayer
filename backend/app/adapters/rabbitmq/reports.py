"""What the broker says about itself, as setting-and-value rows (D331).

A Broker section at the top, before the virtual hosts, as Kafka's Cluster
section is (D310). Each report is one management API answer read into rows,
so the grid, its download and its chart need nothing new.
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.adapters.catalog import ReportNode
from app.adapters.content import NodeRepresentation
from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import NodeNotFound
from app.adapters.rabbitmq.session import RabbitmqSession
from app.adapters.report_rows import export as export_report_rows
from app.adapters.report_rows import page as report_page
from app.core.translation import N_, say

SECTION_ID = "broker"
REPORT_PREFIX = "report:"
SECTION_TITLE = N_("Broker")
SECTION_DESCRIPTION = N_("What this RabbitMQ broker says about itself")
SETTING_COLUMN = N_("Setting")
VALUE_COLUMN = N_("Value")

# The API's largest page; a list past it is cut and says so.
LISTED = 500

_TABLE = NodeRepresentation(kind="table", title=N_("View as table"))

type Rows = list[tuple[str, str]]


def size(count: Any) -> str:
    """Bytes in the largest unit that keeps a digit before the point."""
    if not isinstance(count, int | float):
        return "—"
    value = float(count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return "—"


def duration(milliseconds: Any) -> str:
    if not isinstance(milliseconds, int | float):
        return "—"
    seconds = int(milliseconds // 1000)
    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return say("{days} d {hours} h", days=days, hours=hours)
    if hours:
        return say("{hours} h {minutes} min", hours=hours, minutes=minutes)
    return say("{minutes} min", minutes=minutes)


def _number(value: Any) -> str:
    return str(value) if isinstance(value, int | float) else "—"


def _rate(stats: Any, name: str) -> str:
    details = stats.get(name) if isinstance(stats, dict) else None
    rate = details.get("rate") if isinstance(details, dict) else None
    return say("{n}/s", n=round(rate, 1)) if isinstance(rate, int | float) else "—"


async def _listed(
    session: RabbitmqSession, path: str, columns: str
) -> tuple[list[dict[str, Any]], int]:
    answer = await session.api(
        path,
        {"page": "1", "page_size": str(LISTED), "sort": "name", "columns": columns},
    )
    items = answer.get("items", []) if isinstance(answer, dict) else answer or []
    total = (
        answer.get("total_count", len(items))
        if isinstance(answer, dict)
        else len(items)
    )
    return [one for one in items if isinstance(one, dict)], int(total)


def _cut(rows: Rows, total: int) -> Rows:
    if total > len(rows):
        rows.append(
            ("…", say("{shown} of {total} are shown", shown=len(rows), total=total))
        )
    return rows


async def _overview(session: RabbitmqSession) -> Rows:
    seen = await session.api("/overview")
    totals = seen.get("object_totals") or {}
    queued = seen.get("queue_totals") or {}
    stats = seen.get("message_stats") or {}
    return [
        (
            say("Release"),
            f"{seen.get('product_name', 'RabbitMQ')} {seen.get('rabbitmq_version', '')}".strip(),
        ),
        (say("Erlang"), str(seen.get("erlang_version", "—"))),
        (say("Cluster"), str(seen.get("cluster_name", "—"))),
        (say("Node answering"), str(seen.get("node", "—"))),
        (say("Connections"), _number(totals.get("connections"))),
        (say("Channels"), _number(totals.get("channels"))),
        (say("Queues"), _number(totals.get("queues"))),
        (say("Exchanges"), _number(totals.get("exchanges"))),
        (say("Consumers"), _number(totals.get("consumers"))),
        (say("Messages ready"), _number(queued.get("messages_ready"))),
        (
            say("Messages unacknowledged"),
            _number(queued.get("messages_unacknowledged")),
        ),
        (say("Published"), _rate(stats, "publish_details")),
        (say("Delivered"), _rate(stats, "deliver_get_details")),
    ]


async def _nodes(session: RabbitmqSession) -> Rows:
    rows: Rows = []
    for node in await session.api("/nodes") or []:
        if not isinstance(node, dict):
            continue
        if not node.get("running"):
            rows.append((str(node.get("name", "")), say("not running")))
            continue
        rows.append(
            (
                str(node.get("name", "")),
                say(
                    "memory {used} of {limit}, disk free {free} above {floor}, "
                    "file descriptors {fd} of {fd_total}, up {uptime}",
                    used=size(node.get("mem_used")),
                    limit=size(node.get("mem_limit")),
                    free=size(node.get("disk_free")),
                    floor=size(node.get("disk_free_limit")),
                    fd=_number(node.get("fd_used")),
                    fd_total=_number(node.get("fd_total")),
                    uptime=duration(node.get("uptime")),
                ),
            )
        )
    return rows


async def _alarms(session: RabbitmqSession) -> Rows:
    rows: Rows = []
    for node in await session.api("/nodes") or []:
        if not isinstance(node, dict):
            continue
        name = str(node.get("name", ""))
        if node.get("mem_alarm"):
            rows.append(
                (
                    name,
                    say(
                        "memory alarm: {used} used of {limit}; publishers are blocked",
                        used=size(node.get("mem_used")),
                        limit=size(node.get("mem_limit")),
                    ),
                )
            )
        if node.get("disk_free_alarm"):
            rows.append(
                (
                    name,
                    say(
                        "disk alarm: {free} free, under {floor}; publishers are blocked",
                        free=size(node.get("disk_free")),
                        floor=size(node.get("disk_free_limit")),
                    ),
                )
            )
    return rows


async def _connections(session: RabbitmqSession) -> Rows:
    items, total = await _listed(
        session,
        "/connections",
        "name,user,vhost,state,channels,client_properties",
    )
    rows: Rows = []
    for one in items:
        client = one.get("client_properties") or {}
        product = " ".join(
            str(part) for part in (client.get("product"), client.get("version")) if part
        )
        rows.append(
            (
                str(one.get("name", "")),
                say(
                    "{user} on {vhost}, {client}, {channels} channels, {state}",
                    user=one.get("user", "—"),
                    vhost=one.get("vhost", "—"),
                    client=product or say("a client that does not say"),
                    channels=_number(one.get("channels")),
                    state=one.get("state", "—"),
                ),
            )
        )
    return _cut(rows, total)


async def _channels(session: RabbitmqSession) -> Rows:
    items, total = await _listed(
        session,
        "/channels",
        "name,user,vhost,consumer_count,prefetch_count,messages_unacknowledged",
    )
    return _cut(
        [
            (
                str(one.get("name", "")),
                say(
                    "{user} on {vhost}, {consumers} consumers, prefetch {prefetch}, "
                    "{unacked} unacknowledged",
                    user=one.get("user", "—"),
                    vhost=one.get("vhost", "—"),
                    consumers=_number(one.get("consumer_count")),
                    prefetch=_number(one.get("prefetch_count")),
                    unacked=_number(one.get("messages_unacknowledged")),
                ),
            )
            for one in items
        ],
        total,
    )


async def _policies(session: RabbitmqSession) -> Rows:
    rows: Rows = []
    for one in await session.api("/policies") or []:
        if not isinstance(one, dict):
            continue
        rows.append(
            (
                f"{one.get('vhost', '')} {one.get('name', '')}",
                say(
                    "{pattern} for {applies}, priority {priority}: {definition}",
                    pattern=one.get("pattern", ""),
                    applies=one.get("apply-to", "all"),
                    priority=_number(one.get("priority")),
                    definition=json.dumps(one.get("definition") or {}, sort_keys=True),
                ),
            )
        )
    return sorted(rows)[:LISTED]


@dataclass(frozen=True)
class BrokerReport:
    key: str
    title: str
    description: str
    read: Callable[[RabbitmqSession], Awaitable[Rows]]
    refresh_seconds: int | None = None

    @property
    def node_id(self) -> str:
        return REPORT_PREFIX + self.key


REPORTS: tuple[BrokerReport, ...] = (
    BrokerReport(
        "overview",
        N_("Overview"),
        N_("The release, the counts of everything, and messages a second"),
        _overview,
        refresh_seconds=10,
    ),
    BrokerReport(
        "nodes",
        N_("Nodes"),
        N_("Each node's memory, disk, file descriptors and uptime"),
        _nodes,
    ),
    BrokerReport(
        "alarms",
        N_("Alarms"),
        N_(
            "Nodes short of memory or disk, which blocks publishers; empty when all is well"
        ),
        _alarms,
        refresh_seconds=10,
    ),
    BrokerReport(
        "connections",
        N_("Connections"),
        N_("Each client, its user, virtual host and channels"),
        _connections,
        refresh_seconds=10,
    ),
    BrokerReport(
        "channels",
        N_("Channels"),
        N_("Each channel's consumers, prefetch and unacknowledged messages"),
        _channels,
    ),
    BrokerReport(
        "policies",
        N_("Policies"),
        N_("Each policy, what it matches and what it sets"),
        _policies,
    ),
)

_BY_ID = {report.node_id: report for report in REPORTS}


def is_section(node_id: str | None) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str | None) -> bool:
    return (node_id or "").startswith(REPORT_PREFIX)


def report_for(node_id: str | None) -> BrokerReport | None:
    return _BY_ID.get(node_id or "")


def section_node() -> ReportNode:
    return ReportNode(
        id=SECTION_ID,
        name=say(SECTION_TITLE),
        description=say(SECTION_DESCRIPTION),
        has_children=True,
        representations=[],
    )


def report_node(report: BrokerReport) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=say(report.title),
        description=say(report.description),
        has_children=False,
        representations=[_TABLE.model_copy(update={"title": say(_TABLE.title)})],
    )


class RabbitmqReports:
    def __init__(self, session: RabbitmqSession) -> None:
        self._session = session

    def _report(self, node_id: str) -> BrokerReport:
        report = report_for(node_id)
        if report is None:
            raise NodeNotFound(node_id)
        return report

    async def fetch(self, request: FetchRequest) -> FetchResult:
        report = self._report(request.node_id)
        rows = await report.read(self._session)
        return report_page(
            request,
            rows,
            name_column=say(SETTING_COLUMN),
            value_column=say(VALUE_COLUMN),
            read_only_reason=say(
                '"{title}" is a report and holds no rows of its own',
                title=say(report.title),
            ),
            refresh_seconds=report.refresh_seconds,
            page_commands=["download", "chart", "share"],
        )

    async def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        report = self._report(request.node_id)
        rows = await report.read(self._session)
        selected = export_report_rows(
            request,
            rows,
            name_column=say(SETTING_COLUMN),
            value_column=say(VALUE_COLUMN),
        )
        for start in range(0, len(selected), EXPORT_BATCH_SIZE):
            yield ExportBatch(rows=selected[start : start + EXPORT_BATCH_SIZE])
