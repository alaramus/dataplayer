"""An exchange's market data as a source, the shared part (D317, D318, D425).

The catalog, the path to a node, which feed a node reads, an export to its
depth, a watch of a symbol, a search and the metrics are the same on every
exchange; an exchange's adapter says how it reads its tickers, candles,
trades and book, and what it watches. Read only: nothing on an exchange is
changed from here.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any, ClassVar

from app.adapters.catalog import CatalogNode, FeedName
from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest
from app.adapters.features import SourceFeatures
from app.adapters.fetch import MAX_LIMIT, FetchColumn, FetchRequest, FetchResult
from app.adapters.live import LiveRows, LiveStart
from app.adapters.market.catalog import (
    PRIVATE,
    Place,
    account_children,
    account_node,
    candle_nodes,
    is_markets,
    listed_folder,
    listed_folders,
    listed_market,
    listed_node,
    listed_nodes,
    market_children,
    market_node,
    market_nodes,
    markets_node,
    quote_node,
    symbol_children,
    symbol_node,
)
from app.adapters.market.columns import DEPTH_CEILING
from app.adapters.market.feeds import book_page, symbols_page, tickers_page
from app.adapters.market.live import DEFAULT_INTERVAL
from app.adapters.market.metrics import metric_samples
from app.adapters.market.reports import ExchangeReports, in_section, is_section
from app.adapters.market.search import MarketSearch
from app.adapters.market.session import MarketSession
from app.adapters.market.shape import Market
from app.adapters.metrics import MetricPreset, MetricSample
from app.adapters.protocol import ConnectionCheckResult, NodeNotFound
from app.adapters.reading_on import Bookmark, ReadBlock, ReadStart, UnreadSpan
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
from app.core.translation import say


def key_checked(
    checked: ConnectionCheckResult, more_than_reading: bool
) -> ConnectionCheckResult:
    """A key that passed, said when it may do more than read (D322, D431).

    Accepted either way: nothing changing is ever sent from here, and the
    owner of the key decides what it is for.
    """
    if not more_than_reading:
        return checked
    return checked.model_copy(
        update={
            "message": say(
                "Connection successful. This key may also trade or move "
                "money; DataPlayer only reads, but a key that can only "
                "read is safer"
            )
        }
    )


class MarketReading[M: Market]:
    """A symbol's feeds read on by a pipeline's link (D319); each exchange's own."""

    def reads_on(self, node_id: str) -> bool:
        raise NotImplementedError

    async def unread(self, node_id: str, reader: str, start: ReadStart) -> UnreadSpan:
        raise NotImplementedError

    async def read_on(
        self, node_id: str, columns: list[str], at: Bookmark, line: Bookmark, limit: int
    ) -> ReadBlock:
        raise NotImplementedError

    async def mark_read(self, node_id: str, reader: str, at: Bookmark) -> None:
        raise NotImplementedError

    def row_key(self, node_id: str) -> list[str]:
        raise NotImplementedError


class MarketAdapter[M: Market]:
    presets: ClassVar[tuple[MetricPreset, ...]] = ()

    def __init__(
        self,
        session: MarketSession[M],
        reports: ExchangeReports[Any],
        reading: MarketReading[M],
    ) -> None:
        self._market_session = session
        self._reports = reports
        self._reading = reading
        self._search = MarketSearch(session, self.place_of)
        self._by_key: dict[str, M] = {market.key: market for market in session.markets}

    # --- what an exchange says ----------------------------------------------------

    def place_of(self, node_id: str) -> Place[M]:
        raise NotImplementedError

    async def ticker_rows(
        self, market: M
    ) -> tuple[list[FetchColumn], list[list[str | None]]]:
        """Every trading symbol's day, in the shared ticker columns it fills."""
        raise NotImplementedError

    async def candles_page(self, place: Place[M], request: FetchRequest) -> FetchResult:
        raise NotImplementedError

    async def trades_page(self, place: Place[M], request: FetchRequest) -> FetchResult:
        raise NotImplementedError

    async def read_book(
        self, market: M, symbol: str, depth: int, node_id: str
    ) -> dict[str, Any]:
        """The book to a depth, as `bids` and `asks` of a price and a quantity."""
        raise NotImplementedError

    def watch(
        self, place: Place[M], interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        raise NotImplementedError

    def account_feeds(self, market: M) -> list[FeedName]:
        """The account's feeds of a market a key reads (D322); none without one."""
        del market
        return []

    async def account_page(self, place: Place[M], request: FetchRequest) -> FetchResult:
        raise NodeNotFound(request.node_id)

    async def export_candles(
        self, place: Place[M], request: ExportRequest
    ) -> tuple[list[list[str | None]], list[str]] | None:
        """Candles to the depth, where the exchange reads them faster than a
        page at a time; None reads them page by page."""
        del place, request
        return None

    # --- the shared part ---------------------------------------------------------------

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._market_session.check()

    async def source_features(self) -> SourceFeatures:
        return SourceFeatures(
            observed_at=get_datetime_utc(), server_version=None, features=[]
        )

    async def _known(self, place: Place[M], node_id: str) -> None:
        """A symbol or a quote asset named by a client is one the market has,
        and the account's nodes exist only with a key that reads them."""
        session = self._market_session
        private = place.what == "account" or place.feed in PRIVATE
        if private and not session.keyed:
            raise NodeNotFound(node_id)
        if (
            place.symbol is None
            and place.feed in PRIVATE
            and place.feed not in self.account_feeds(place.market)
        ):
            raise NodeNotFound(node_id)
        if place.symbol is not None:
            await session.symbol(place.market, place.symbol, node_id)
        if place.quote is not None:
            symbols = await session.symbols(place.market)
            if not any(one.quote == place.quote for one in symbols):
                raise NodeNotFound(node_id)

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        session = self._market_session
        reports = self._reports
        if node_id is None:
            # The connection's own section first, as Kafka puts its own (D320).
            return [
                reports.section_node(),
                markets_node(),
                *market_nodes(session.markets),
            ]
        if is_markets(node_id):
            return listed_folders(session.markets)
        if (folder := listed_market(self._by_key, node_id)) is not None:
            return listed_nodes(folder, await session.symbols(folder))
        if is_section(node_id):
            return [*reports.children()]
        if in_section(node_id):
            if reports.report_for(node_id) is None:
                raise NodeNotFound(node_id)
            return []
        place = self.place_of(node_id)
        await self._known(place, node_id)
        market = place.market
        keyed = session.keyed
        if place.what == "market":
            return market_children(market, await session.symbols(market), keyed)
        if place.what == "account":
            return account_children(market, self.account_feeds(market))
        if place.what == "quote":
            return [
                symbol_node(market, one)
                for one in sorted(
                    await session.symbols(market), key=lambda one: one.name
                )
                if one.quote == place.quote
            ]
        if place.what == "symbol" and place.symbol is not None:
            return symbol_children(market, place.symbol, keyed)
        if place.what == "candles" and place.symbol is not None:
            return candle_nodes(market, place.symbol)
        return []

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        session = self._market_session
        if is_markets(node_id):
            return [markets_node()]
        if (folder := listed_market(self._by_key, node_id)) is not None:
            return [markets_node(), listed_folder(folder)]
        if is_section(node_id):
            return [self._reports.section_node()]
        if in_section(node_id):
            return [*self._reports.path_to(node_id)]
        place = self.place_of(node_id)
        await self._known(place, node_id)
        market = place.market
        if place.listed:
            assert place.symbol is not None
            return [
                markets_node(),
                listed_folder(market),
                listed_node(market, place.symbol),
            ]
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
                for one in account_children(market, self.account_feeds(market))
                if one.id == node_id
            ]
        if place.quote is not None:
            return [*path, quote_node(market, place.quote)]
        assert place.symbol is not None
        symbol = await session.symbol(market, place.symbol, node_id)
        path += [quote_node(market, symbol.quote), symbol_node(market, symbol)]
        if place.what == "symbol":
            return path
        children = symbol_children(market, place.symbol, session.keyed)
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

    async def _watched(
        self, node_id: str, interval: str | None
    ) -> tuple[Place[M], str]:
        place = self.place_of(node_id)
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
        async for rows in self.watch(place, chosen, node_id):
            yield rows

    # --- the feeds as rows (D318) ------------------------------------------------

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if in_section(request.node_id):
            return await self._reports.fetch(request)
        place = self.place_of(request.node_id)
        await self._known(place, request.node_id)
        if place.feed in PRIVATE:
            return await self.account_page(place, request)
        if place.what == "tickers":
            columns, rows = await self.ticker_rows(place.market)
            return tickers_page(columns, rows, request)
        if place.what == "symbols":
            symbols = await self._market_session.symbols(place.market)
            return symbols_page(place.market, symbols, request)
        if place.feed == "candles":
            return await self.candles_page(place, request)
        if place.feed == "trades":
            return await self.trades_page(place, request)
        if place.feed == "order_book":
            return await book_page(place, request, self.read_book)
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
        place = self.place_of(request.node_id)
        await self._known(place, request.node_id)
        if place.feed == "candles" and place.symbol is not None:
            read = await self.export_candles(place, request)
            if read is not None:
                return read
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
        return await metric_samples(self._market_session)

    @classmethod
    def metric_presets(cls) -> tuple[MetricPreset, ...]:
        return cls.presets

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
