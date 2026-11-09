"""What the connection says about Binance and itself (D320).

An Exchange section at the top, beside the two markets, as Kafka's Cluster
section is (D310). Each report is setting-and-value rows, so the grid, its
download and its chart need nothing new.
"""

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.adapters.binance.account import PERMISSIONS, restrictions
from app.adapters.binance.markets import BY_KEY, MARKETS
from app.adapters.binance.session import CEILING_SHARE, BinanceSession
from app.adapters.catalog import ReportNode
from app.adapters.content import NodeRepresentation
from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import NodeNotFound
from app.adapters.report_rows import export as export_report_rows
from app.adapters.report_rows import page as report_page
from app.core.translation import N_, say

SECTION_ID = "exchange"
REPORT_PREFIX = "report:"
SECTION_TITLE = N_("Exchange")
SECTION_DESCRIPTION = N_("What Binance and this connection say about themselves")
SETTING_COLUMN = N_("Setting")
VALUE_COLUMN = N_("Value")

ENDPOINT_TITLES = {
    "binance": N_("Binance"),
    "binance_key": N_("Binance, with an API key"),
    "market_data": N_("Binance, market data only"),
    "testnet": N_("Testnet"),
    "testnet_key": N_("Testnet, with an API key"),
}

_TABLE = NodeRepresentation(kind="table", title=N_("View as table"))

type Rows = list[tuple[str, str]]


def _moment(milliseconds: float) -> str:
    at = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def _status(session: BinanceSession) -> Rows:
    endpoint = session.options.endpoint
    status = await session.system_status()
    rows: Rows = [
        (say("Endpoint"), say(ENDPOINT_TITLES[endpoint])),
        (
            say("System status"),
            say("not known on this endpoint")
            if status is None
            else say("normal")
            if status == "normal"
            else say("maintenance"),
        ),
    ]
    for key, pinged in (await session.pinged()).items():
        rows.append((say(BY_KEY[key].title), pinged.failure or say("reached")))
    return rows


async def _clock(session: BinanceSession) -> Rows:
    rows: Rows = []
    for key in MARKETS:
        market = BY_KEY[key]
        before = time.time() * 1000
        answer = await session.get(market, "time", {})
        after = time.time() * 1000
        server = answer.get("serverTime") if isinstance(answer, dict) else None
        if not isinstance(server, int):
            continue
        # Against the middle of the request: half the way there, half back.
        difference = int(server - (before + after) / 2)
        rows.append(
            (
                say("{market}: server time", market=say(market.title)),
                _moment(server),
            )
        )
        rows.append(
            (
                say("{market}: ahead of this server", market=say(market.title)),
                say("{ms} ms", ms=difference),
            )
        )
    rows.append((say("This server's time"), _moment(time.time() * 1000)))
    return rows


async def _limits(session: BinanceSession) -> Rows:
    rows: Rows = []
    now = time.time()
    minute = int(now // 60)
    for key, pinged in (await session.pinged()).items():
        state = pinged.state
        title = say(BY_KEY[key].title)
        used = state.used if state.minute == minute else 0
        rows += [
            (say("{market}: limit a minute", market=title), str(state.limit)),
            (say("{market}: used this minute", market=title), str(used)),
            (
                say("{market}: this connection stops at", market=title),
                str(int(state.limit * CEILING_SHARE)),
            ),
            (
                say("{market}: requests held", market=title),
                say("until {at}", at=_moment(state.held_until * 1000))
                if state.held_until > now
                else say("no"),
            ),
        ]
    return rows


async def _markets(session: BinanceSession) -> Rows:
    rows: Rows = []
    for key in MARKETS:
        market = BY_KEY[key]
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
    for key in MARKETS:
        read_at = states[key].symbols_read_at
        if read_at is not None:
            rows.append(
                (
                    say("{market}: symbol list read", market=say(BY_KEY[key].title)),
                    _moment(read_at * 1000),
                )
            )
    return rows


async def _key(session: BinanceSession) -> Rows:
    """What Binance says the connection's key may do (D322)."""
    answer = await restrictions(session)
    if answer is None:
        return [(say("What the key may do"), say("not known on the testnet"))]
    rows: Rows = [
        (say(word), say("yes") if answer.get(flag) is True else say("no"))
        for flag, word in PERMISSIONS
    ]
    rows.append(
        (
            say("limited to listed addresses"),
            say("yes") if answer.get("ipRestrict") is True else say("no"),
        )
    )
    created = answer.get("createTime")
    if isinstance(created, int):
        rows.append((say("created"), _moment(created)))
    return rows


@dataclass(frozen=True)
class ExchangeReport:
    key: str
    title: str
    description: str
    read: Callable[[BinanceSession], Awaitable[Rows]]
    refresh_seconds: int | None = None
    # Only a connection with a key has it.
    keyed: bool = False

    @property
    def node_id(self) -> str:
        return REPORT_PREFIX + self.key


REPORTS: tuple[ExchangeReport, ...] = (
    ExchangeReport(
        "status",
        N_("Status"),
        N_("The endpoint, Binance's own status, and whether each market answers"),
        _status,
        refresh_seconds=30,
    ),
    ExchangeReport(
        "clock",
        N_("Clock"),
        N_("Each market's time against this server's"),
        _clock,
    ),
    ExchangeReport(
        "rate-limit",
        N_("Rate limit"),
        N_("What each market allows a minute, what was used, and where this stops"),
        _limits,
        refresh_seconds=10,
    ),
    ExchangeReport(
        "markets",
        N_("Markets"),
        N_("How many symbols trade and in how many quote assets"),
        _markets,
    ),
    ExchangeReport(
        "key",
        N_("API key"),
        N_("What Binance lets this connection's key do"),
        _key,
        keyed=True,
    ),
)


def reports_of(session: BinanceSession) -> list[ExchangeReport]:
    """The section's reports for this connection: the key's only with a key."""
    return [one for one in REPORTS if session.keyed or not one.keyed]


_BY_ID = {report.node_id: report for report in REPORTS}


def is_section(node_id: str | None) -> bool:
    return node_id == SECTION_ID


def in_section(node_id: str | None) -> bool:
    return (node_id or "").startswith(REPORT_PREFIX)


def report_for(node_id: str | None) -> ExchangeReport | None:
    return _BY_ID.get(node_id or "")


def section_node() -> ReportNode:
    return ReportNode(
        id=SECTION_ID,
        name=say(SECTION_TITLE),
        description=say(SECTION_DESCRIPTION),
        has_children=True,
        representations=[],
    )


def report_node(report: ExchangeReport) -> ReportNode:
    return ReportNode(
        id=report.node_id,
        name=say(report.title),
        description=say(report.description),
        has_children=False,
        representations=[_TABLE.model_copy(update={"title": say(_TABLE.title)})],
    )


class BinanceReports:
    def __init__(self, session: BinanceSession) -> None:
        self._session = session

    def _report(self, node_id: str) -> ExchangeReport:
        report = report_for(node_id)
        if report is None or (report.keyed and not self._session.keyed):
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
