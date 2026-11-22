"""An Exchange section of reports, the same frame on every exchange (D320, D425).

A section at the top, beside the markets, as Kafka's Cluster section is
(D310). Each report is setting-and-value rows, so the grid, its download and
its chart need nothing new. The readers of status, clock, rate limit and
markets are shared; an exchange names its reports in its own words and may
add its own, as Binance adds what its key may do.
"""

import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.adapters.catalog import ReportNode
from app.adapters.content import NodeRepresentation
from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.market.session import MarketSession
from app.adapters.protocol import NodeNotFound
from app.adapters.report_rows import export as export_report_rows
from app.adapters.report_rows import page as report_page
from app.core.translation import N_, say

SECTION_ID = "exchange"
REPORT_PREFIX = "report:"
SECTION_TITLE = N_("Exchange")
SETTING_COLUMN = N_("Setting")
VALUE_COLUMN = N_("Value")

_TABLE = NodeRepresentation(kind="table", title=N_("View as table"))

type Rows = list[tuple[str, str]]
type AnySession = MarketSession[Any]


def moment_of(milliseconds: float) -> str:
    at = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


# --- the shared readers ---------------------------------------------------------


async def status_rows(
    session: AnySession, endpoint_titles: Mapping[str, str], endpoint: str
) -> Rows:
    """The endpoint, the exchange's own status where it has one, each market pinged."""
    status = await session.system_status()
    rows: Rows = [
        (say("Endpoint"), say(endpoint_titles[endpoint])),
        (
            say("System status"),
            say("not known on this endpoint")
            if status is None
            else say("normal")
            if status == "normal"
            else say("maintenance"),
        ),
    ]
    titles = {market.key: market.title for market in session.markets}
    for key, pinged in (await session.pinged()).items():
        rows.append((say(titles[key]), pinged.failure or say("reached")))
    return rows


async def clock_rows(session: AnySession) -> Rows:
    rows: Rows = []
    for market in session.markets:
        before = time.time() * 1000
        server = await session.server_time_ms(market)
        after = time.time() * 1000
        if server is None:
            continue
        # Against the middle of the request: half the way there, half back.
        difference = int(server - (before + after) / 2)
        title = say(market.title)
        rows.append((say("{market}: server time", market=title), moment_of(server)))
        rows.append(
            (
                say("{market}: ahead of this server", market=title),
                say("{ms} ms", ms=difference),
            )
        )
    rows.append((say("This server's time"), moment_of(time.time() * 1000)))
    return rows


async def limit_rows(session: AnySession) -> Rows:
    """Each market's limit, what was used of it, where this connection stops."""
    rows: Rows = []
    now = time.time()
    titles = {market.key: market.title for market in session.markets}
    pinged = await session.pinged()
    budgets = [(say(titles[key]), one.state) for key, one in pinged.items()]
    if session.per_address:
        # One budget for every market: said once.
        budgets = [(say("All markets"), one.state) for one in pinged.values()][:1]
    for title, state in budgets:
        if state.window_seconds == 60:
            limit_word = say("{market}: limit a minute", market=title)
            used_word = say("{market}: used this minute", market=title)
        else:
            limit_word = say(
                "{market}: limit in {seconds} s",
                market=title,
                seconds=state.window_seconds,
            )
            used_word = say(
                "{market}: used in these {seconds} s",
                market=title,
                seconds=state.window_seconds,
            )
        rows += [
            (limit_word, str(state.limit)),
            (used_word, str(state.used_at(now))),
            (
                say("{market}: this connection stops at", market=title),
                str(state.ceiling),
            ),
            (
                say("{market}: requests held", market=title),
                say("until {at}", at=moment_of(state.held_until * 1000))
                if state.held_until > now
                else say("no"),
            ),
        ]
    return rows


async def market_rows(session: AnySession) -> Rows:
    rows: Rows = []
    for market in session.markets:
        symbols = await session.symbols(market)
        title = say(market.title)
        rows += [
            (say("{market}: symbols trading", market=title), str(len(symbols))),
            (
                say("{market}: quote assets", market=title),
                str(len({one.quote for one in symbols})),
            ),
        ]
    states = await session.states()
    for market in session.markets:
        read_at = states[market.key].symbols_read_at
        if read_at is not None:
            rows.append(
                (
                    say("{market}: symbol list read", market=say(market.title)),
                    moment_of(read_at * 1000),
                )
            )
    return rows


# --- the section ------------------------------------------------------------------


@dataclass(frozen=True)
class ExchangeReport[S: AnySession]:
    key: str
    title: str
    description: str
    read: Callable[[S], Awaitable[Rows]]
    refresh_seconds: int | None = None
    # Only a connection with a key has it.
    keyed: bool = False

    @property
    def node_id(self) -> str:
        return REPORT_PREFIX + self.key


def is_section(node_id: str | None) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str | None) -> bool:
    return (node_id or "").startswith(REPORT_PREFIX)


def report_node(report: ExchangeReport[Any]) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=say(report.title),
        description=say(report.description),
        has_children=False,
        representations=[_TABLE.model_copy(update={"title": say(_TABLE.title)})],
    )


class ExchangeReports[S: AnySession]:
    """An exchange's section: its own description and reports, the shared frame."""

    def __init__(
        self, session: S, description: str, reports: tuple[ExchangeReport[S], ...]
    ) -> None:
        self._session = session
        self._description = description
        self._reports = reports
        self._by_id = {report.node_id: report for report in reports}

    def available(self) -> list[ExchangeReport[S]]:
        """The section's reports for this connection: a key's only with a key."""
        keyed = self._session.keyed
        return [one for one in self._reports if keyed or not one.keyed]

    def section_node(self) -> ReportNode:
        return ReportNode(
            id=SECTION_ID,
            name=say(SECTION_TITLE),
            description=say(self._description),
            has_children=True,
            representations=[],
        )

    def report_for(self, node_id: str | None) -> ExchangeReport[S] | None:
        """The report an id names, if this connection has it."""
        report = self._by_id.get(node_id or "")
        if report is None or report not in self.available():
            return None
        return report

    def children(self) -> list[ReportNode]:
        return [report_node(report) for report in self.available()]

    def path_to(self, node_id: str) -> list[ReportNode]:
        report = self.report_for(node_id)
        if report is None:
            raise NodeNotFound(node_id)
        return [self.section_node(), report_node(report)]

    def _report(self, node_id: str) -> ExchangeReport[S]:
        report = self.report_for(node_id)
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
            page_commands=["download", "share"],
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
