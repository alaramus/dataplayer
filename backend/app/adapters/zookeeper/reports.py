"""What the server says about itself, from its four-letter words (D301).

Each report is one command sent on the session's connection and its answer
read as setting-and-value rows. A server answers only the words its
`4lw.commands.whitelist` allows; one it refuses is a row saying so rather than
a failed report, since every other report may still be allowed.
"""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from kazoo.client import KazooClient

from app.adapters.catalog import ReportNode
from app.adapters.content import NodeRepresentation
from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import NodeNotFound
from app.adapters.report_rows import export as export_report_rows
from app.adapters.report_rows import page as report_page
from app.adapters.zookeeper.session import ZookeeperSession
from app.core.translation import N_, say

# Not a path: a znode's id always starts with `/`, so the two never meet.
SECTION_ID = "\\server"
SECTION_TITLE = N_("Server")
SECTION_DESCRIPTION = N_("What this ZooKeeper server says about itself")
SETTING_COLUMN = N_("Setting")
VALUE_COLUMN = N_("Value")

_TABLE = NodeRepresentation(kind="table", title=N_("View as table"))

type Rows = list[tuple[str, str]]


def _colon_pairs(answer: str) -> Rows:
    """`srvr`: `Name: value` per line."""
    rows: Rows = []
    for line in answer.splitlines():
        name, sign, value = line.partition(":")
        if sign and name.strip():
            rows.append((name.strip(), value.strip()))
    return rows


def _tab_pairs(answer: str) -> Rows:
    """`mntr`: `zk_name<TAB>value` per line."""
    rows: Rows = []
    for line in answer.splitlines():
        name, sign, value = line.partition("\t")
        if sign:
            rows.append((name.strip(), value.strip()))
    return rows


def _equals_pairs(answer: str) -> Rows:
    """`conf`: `name=value` per line."""
    rows: Rows = []
    for line in answer.splitlines():
        name, sign, value = line.partition("=")
        if sign and name.strip():
            rows.append((name.strip(), value.strip()))
    return rows


def _connections(answer: str) -> Rows:
    """`cons`: the client's address, then what the server keeps about it."""
    rows: Rows = []
    for line in answer.splitlines():
        line = line.strip()
        if not line:
            continue
        address, bracket, rest = line.partition("[")
        rows.append((address, (bracket + rest) if bracket else ""))
    return rows


def _watches(answer: str) -> Rows:
    """`wchs`: a sentence and a total, kept as the server wrote them."""
    rows: Rows = []
    for line in answer.splitlines():
        line = line.strip()
        if not line:
            continue
        name, sign, value = line.partition(":")
        rows.append((name.strip(), value.strip()) if sign else (line, ""))
    return rows


@dataclass(frozen=True)
class ServerReport:
    command: str
    title: str
    description: str
    read: Callable[[str], Rows]
    refresh_seconds: int | None = None

    @property
    def node_id(self) -> str:
        return f"{SECTION_ID}/{self.command}"


REPORTS: tuple[ServerReport, ...] = (
    ServerReport(
        "srvr",
        N_("Server"),
        N_("Version, mode, latency, connections and the number of znodes"),
        _colon_pairs,
        refresh_seconds=10,
    ),
    ServerReport(
        "mntr",
        N_("Monitoring"),
        N_("Every counter the server keeps, as monitoring tools read them"),
        _tab_pairs,
        refresh_seconds=10,
    ),
    ServerReport(
        "cons",
        N_("Connections"),
        N_("Each client connected to this server and what it has sent"),
        _connections,
        refresh_seconds=10,
    ),
    ServerReport(
        "wchs",
        N_("Watches"),
        N_("How many watches are set, and on how many paths"),
        _watches,
        refresh_seconds=10,
    ),
    ServerReport(
        "conf",
        N_("Configuration"),
        N_("The settings this server runs with"),
        _equals_pairs,
    ),
)
_BY_ID = {report.node_id: report for report in REPORTS}


def is_section(node_id: str | None) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str | None) -> bool:
    return (node_id or "").startswith(SECTION_ID + "/")


def report_for(node_id: str | None) -> ServerReport | None:
    return _BY_ID.get(node_id or "")


def section_node() -> ReportNode:
    return ReportNode(
        id=SECTION_ID,
        name=say(SECTION_TITLE),
        description=say(SECTION_DESCRIPTION),
        has_children=True,
        representations=[],
    )


def report_node(report: ServerReport) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=say(report.title),
        description=say(report.description),
        has_children=False,
        representations=[_TABLE.model_copy(update={"title": say(_TABLE.title)})],
    )


def refused(answer: str) -> bool:
    """The server's own line for a word its whitelist leaves out."""
    return "not in the whitelist" in answer or "not executed" in answer


def ask(client: KazooClient, command: str) -> str:
    answer: str = client.command(command.encode("ascii"))
    return answer


class ZookeeperReports:
    def __init__(self, session: ZookeeperSession) -> None:
        self._session = session

    async def rows(self, report: ServerReport) -> Rows:
        answer = await self._session.run(lambda client: ask(client, report.command))
        if refused(answer):
            return [
                (
                    report.command,
                    say(
                        "The server does not answer {command}; add it to 4lw.commands.whitelist",
                        command=report.command,
                    ),
                )
            ]
        return report.read(answer)

    def _report(self, node_id: str) -> ServerReport:
        report = report_for(node_id)
        if report is None:
            raise NodeNotFound(node_id)
        return report

    async def fetch(self, request: FetchRequest) -> FetchResult:
        report = self._report(request.node_id)
        return report_page(
            request,
            await self.rows(report),
            name_column=say(SETTING_COLUMN),
            value_column=say(VALUE_COLUMN),
            read_only_reason=say(
                '"{title}" is a report and holds no rows of its own', title=say(report.title)
            ),
            refresh_seconds=report.refresh_seconds,
            page_commands=["download", "chart", "share"],
        )

    async def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        report = self._report(request.node_id)
        selected = export_report_rows(
            request,
            await self.rows(report),
            name_column=say(SETTING_COLUMN),
            value_column=say(VALUE_COLUMN),
        )
        for start in range(0, len(selected), EXPORT_BATCH_SIZE):
            yield ExportBatch(rows=selected[start : start + EXPORT_BATCH_SIZE])
