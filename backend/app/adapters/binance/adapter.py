"""Binance's market data as a source: markets, symbols and their feeds, and
with a key the account it reads (D322).

Read only: nothing on Binance is changed from here (D316). Everything is
read over REST through one client a connection.
"""

import time
from collections.abc import AsyncGenerator, AsyncIterator

from app.adapters.binance.account import (
    account_feeds,
    account_page,
    more_than_reading,
    restrictions,
)
from app.adapters.binance.catalog import (
    PRIVATE,
    Place,
    account_children,
    account_node,
    candle_nodes,
    market_children,
    market_node,
    markets,
    place_of,
    quote_node,
    symbol_children,
    symbol_node,
)
from app.adapters.binance.feeds import (
    CANDLE_COLUMNS,
    DEPTH_CEILING,
    book_page,
    candles_page,
    checked_candles,
    contract_size_of,
    read_candles,
    symbols_page,
    tickers_page,
    trades_page,
)
from app.adapters.binance.live import DEFAULT_INTERVAL, BinanceLive
from app.adapters.binance.markets import HOSTS, market_of
from app.adapters.binance.metrics import PRESETS as METRIC_PRESETS
from app.adapters.binance.metrics import BinanceMetrics
from app.adapters.binance.options import HOSTS_OF, BinanceOptions
from app.adapters.binance.reading import BinanceReading
from app.adapters.binance.reports import (
    BinanceReports,
    in_section,
    is_section,
    report_for,
    report_node,
    reports_of,
    section_node,
)
from app.adapters.binance.search import BinanceSearch
from app.adapters.binance.session import BinanceSession
from app.adapters.catalog import CatalogNode, FeedName
from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.features import SourceFeatures
from app.adapters.fetch import MAX_LIMIT, FetchRequest, FetchResult
from app.adapters.live import LiveRows, LiveStart
from app.adapters.metrics import MetricPreset, MetricSample
from app.adapters.protocol import AdapterError, ConnectionCheckResult, NodeNotFound
from app.adapters.reading_on import (
    Bookmark,
    BookmarkAccess,
    ReadBlock,
    ReadStart,
    UnreadSpan,
)
from app.adapters.registry import AdapterContext, register
from app.adapters.search import (
    LastSearch,
    NameBatch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    SearchedField,
    SourceCost,
)
from app.core.schemas import get_datetime_utc
from app.core.translation import N_, say


def _now_ms() -> int:
    return int(time.time() * 1000)


class BinanceAdapter:
    def __init__(
        self, session: BinanceSession, bookmarks: BookmarkAccess | None = None
    ) -> None:
        self._session = session
        self._reading = BinanceReading(session, bookmarks)
        self._reports = BinanceReports(session)
        self._metrics = BinanceMetrics(session)
        self._search = BinanceSearch(session)
        self._live = BinanceLive(session)

    def connection_string(self) -> str:
        """The spot host this connection speaks to; a key is never part of it."""
        return HOSTS[HOSTS_OF[self._session.options.endpoint]]["spot"]

    async def check_connection(self) -> ConnectionCheckResult:
        checked = await self._session.check()
        if not checked.ok or not self._session.keyed:
            return checked
        return await self._check_key(checked)

    async def _check_key(self, checked: ConnectionCheckResult) -> ConnectionCheckResult:
        """The key read with, and said when it may do more than read (D322).

        Accepted either way: nothing changing is ever sent from here, and the
        owner of the key decides what it is for. The testnet cannot be asked
        what a key may do, so its key is only tried.
        """
        session = self._session
        try:
            answer = await restrictions(session)
            if answer is None:
                await session.signed(
                    market_of("spot"), "account", {"omitZeroBalances": "true"}
                )
        except AdapterError as failure:
            return ConnectionCheckResult(
                ok=False, message=failure.message, error_kind=failure.error_kind
            )
        if answer is not None and answer.get("enableReading") is not True:
            return ConnectionCheckResult(
                ok=False,
                message=say("Binance says this key may not read the account"),
                error_kind="auth",
            )
        if answer is not None and more_than_reading(answer):
            return checked.model_copy(
                update={
                    "message": say(
                        "Connection successful. This key may also trade or move "
                        "money; DataPlayer only reads, but a key that can only "
                        "read is safer"
                    )
                }
            )
        return checked

    async def source_features(self) -> SourceFeatures:
        return SourceFeatures(
            observed_at=get_datetime_utc(), server_version=None, features=[]
        )

    # --- the catalog (D317) -----------------------------------------------------

    async def _known(self, place: Place, node_id: str) -> None:
        """A symbol or a quote asset named by a client is one the market has,
        and the account's nodes exist only with a key that reads them."""
        private = place.what == "account" or place.feed in PRIVATE
        if private and not self._session.keyed:
            raise NodeNotFound(node_id)
        if (
            place.symbol is None
            and place.feed in PRIVATE
            and place.feed not in self._account_feeds(place)
        ):
            raise NodeNotFound(node_id)
        if place.symbol is not None:
            await self._session.symbol(place.market, place.symbol, node_id)
        if place.quote is not None:
            symbols = await self._session.symbols(place.market)
            if not any(one.quote == place.quote for one in symbols):
                raise NodeNotFound(node_id)

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            # The connection's own section first, as Kafka puts its own (D320).
            return [section_node(), *markets()]
        if is_section(node_id):
            return [report_node(report) for report in reports_of(self._session)]
        if in_section(node_id):
            if report_for(node_id) not in reports_of(self._session):
                raise NodeNotFound(node_id)
            return []
        place = place_of(node_id)
        await self._known(place, node_id)
        market = place.market
        keyed = self._session.keyed
        if place.what == "market":
            return market_children(market, await self._session.symbols(market), keyed)
        if place.what == "account":
            return account_children(market, self._account_feeds(place))
        if place.what == "quote":
            return [
                symbol_node(market, one)
                for one in sorted(
                    await self._session.symbols(market), key=lambda one: one.name
                )
                if one.quote == place.quote
            ]
        if place.what == "symbol" and place.symbol is not None:
            return symbol_children(market, place.symbol, keyed)
        if place.what == "candles" and place.symbol is not None:
            return candle_nodes(market, place.symbol)
        return []

    def _account_feeds(self, place: Place) -> list[FeedName]:
        return account_feeds(place.market, self._session.main_hosts)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        if is_section(node_id):
            return [section_node()]
        if in_section(node_id):
            report = report_for(node_id)
            if report is None or report not in reports_of(self._session):
                raise NodeNotFound(node_id)
            return [section_node(), report_node(report)]
        place = place_of(node_id)
        await self._known(place, node_id)
        market = place.market
        path: list[CatalogNode] = [market_node(market)]
        if place.what == "market":
            return path
        if place.what in {"tickers", "symbols"}:
            found = [one for one in market_children(market, []) if one.id == node_id]
            return path + found
        if place.what == "account" or (place.symbol is None and place.feed in PRIVATE):
            path.append(account_node(market))
            if place.what == "account":
                return path
            return path + [
                one
                for one in account_children(market, self._account_feeds(place))
                if one.id == node_id
            ]
        if place.quote is not None:
            return [*path, quote_node(market, place.quote)]
        assert place.symbol is not None
        symbol = await self._session.symbol(market, place.symbol, node_id)
        path += [quote_node(market, symbol.quote), symbol_node(market, symbol)]
        if place.what == "symbol":
            return path
        children = symbol_children(market, place.symbol, self._session.keyed)
        if place.what == "candles" or place.feed == "candles":
            path += [one for one in children if one.id.endswith(":candles")]
            if place.feed == "candles":
                path += [
                    one
                    for one in candle_nodes(market, place.symbol)
                    if one.id == node_id
                ]
            return path
        return path + [one for one in children if one.id == node_id]

    # --- a symbol watched live (D323) ----------------------------------------------

    async def _watched(self, node_id: str, interval: str | None) -> tuple[Place, str]:
        place = place_of(node_id)
        if place.feed != "market" or place.symbol is None:
            raise ValueError(say("Only a symbol's market is watched live"))
        await self._known(place, node_id)
        chosen = interval or DEFAULT_INTERVAL
        if chosen not in place.market.intervals:
            raise ValueError(
                say("This market has no {interval} candles", interval=chosen)
            )
        return place, chosen

    async def live_start(self, node_id: str, interval: str | None) -> LiveStart:
        place, chosen = await self._watched(node_id, interval)
        return LiveStart(intervals=list(place.market.intervals), interval=chosen)

    async def live(
        self, node_id: str, interval: str | None
    ) -> AsyncGenerator[LiveRows]:
        place, chosen = await self._watched(node_id, interval)
        assert place.symbol is not None
        async for rows in self._live.watch(place.market, place.symbol, chosen, node_id):
            yield rows

    # --- the feeds as rows (D318) ------------------------------------------------

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if in_section(request.node_id):
            return await self._reports.fetch(request)
        place = place_of(request.node_id)
        await self._known(place, request.node_id)
        if place.feed in PRIVATE:
            return await account_page(self._session, place, request)
        if place.what == "tickers":
            return await tickers_page(self._session, place, request)
        if place.what == "symbols":
            return await symbols_page(self._session, place, request)
        if place.feed == "candles":
            return await candles_page(self._session, place, request, _now_ms())
        if place.feed == "trades":
            return await trades_page(self._session, place, request)
        if place.feed == "order_book":
            return await book_page(self._session, place, request)
        raise ValueError(say("This node is not read as rows"))

    async def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        """Every row the page's filters and order would show, to its depth."""
        if in_section(request.node_id):
            async for batch in self._reports.export_rows(request):
                yield batch
            return
        rows, names = await self._export(request)
        unknown = [column for column in request.columns if column not in names]
        if unknown:
            raise ValueError(say("Unknown column: {column}", column=unknown[0]))
        picked = [names.index(column) for column in request.columns]
        for start in range(0, len(rows), EXPORT_BATCH_SIZE):
            yield ExportBatch(
                rows=[
                    [row[index] for index in picked]
                    for row in rows[start : start + EXPORT_BATCH_SIZE]
                ]
            )

    async def _export(
        self, request: ExportRequest
    ) -> tuple[list[list[str | None]], list[str]]:
        place = place_of(request.node_id)
        await self._known(place, request.node_id)
        if place.feed == "candles" and place.symbol is not None:
            assert place.interval is not None
            checked_candles(request.filters, request.sort)
            newest = not any(
                one.column == "open_time" and not one.descending for one in request.sort
            )
            now = _now_ms()
            candles = await read_candles(
                self._session,
                place.market,
                place.symbol,
                place.interval,
                request.filters,
                newest,
                DEPTH_CEILING,
                request.node_id,
            )
            size = await contract_size_of(
                self._session, place.market, place.symbol, request.node_id
            )
            return [one.row(now, size) for one in candles], [
                c.name for c in CANDLE_COLUMNS
            ]
        rows: list[list[str | None]] = []
        names: list[str] = []
        offset = 0
        while offset < DEPTH_CEILING:
            page = await self.fetch(
                FetchRequest(
                    node_id=request.node_id,
                    limit=MAX_LIMIT,
                    offset=offset,
                    filters=request.filters,
                    sort=request.sort,
                )
            )
            names = [column.name for column in page.columns]
            rows.extend(page.rows)
            if not page.has_more:
                break
            offset += MAX_LIMIT
        return rows, names

    # --- measured and searched (D320) -------------------------------------------

    async def metric_samples(self) -> list[MetricSample]:
        return await self._metrics.metric_samples()

    @classmethod
    def metric_presets(cls) -> tuple[MetricPreset, ...]:
        return METRIC_PRESETS

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        return await self._search.search_nodes(request, bounds)

    def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        return self._search.enumerate_names(limit, bounds)

    @classmethod
    def search_cost(cls, field: SearchedField, last: LastSearch | None) -> SourceCost:
        """Names are read from the list the connection keeps; nothing else is searched."""
        del last
        return "cheap" if field == "names" else "costly"

    # --- read on by a pipeline's link (D319) --------------------------------------

    def reads_on(self, node_id: str) -> bool:
        return self._reading.reads_on(node_id)

    async def unread(self, node_id: str, reader: str, start: ReadStart) -> UnreadSpan:
        return await self._reading.unread(node_id, reader, start)

    async def read_on(
        self, node_id: str, columns: list[str], at: Bookmark, line: Bookmark, limit: int
    ) -> ReadBlock:
        return await self._reading.read_on(node_id, columns, at, line, limit)

    async def mark_read(self, node_id: str, reader: str, at: Bookmark) -> None:
        await self._reading.mark_read(node_id, reader, at)

    def row_key(self, node_id: str) -> list[str]:
        return self._reading.row_key(node_id)


@register(
    name="binance",
    title=N_("Binance"),
    category="market",
    description=N_(
        "Binance's public market data, spot and USDⓈ-M futures. See every "
        "symbol's last day and trading rules, and read a symbol's candles of "
        "any interval, its trades and its order book as rows. Nothing is "
        "changed on Binance, and no key is asked for."
    ),
    options_schema=BinanceOptions,
    adapter_class=BinanceAdapter,
)
def _build(options: BinanceOptions, context: AdapterContext) -> BinanceAdapter:
    return BinanceAdapter(BinanceSession(options, context.pooling), context.bookmarks)
