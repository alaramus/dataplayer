"""Coinbase Exchange's market data as a source: its spot products and their
feeds (D438, D439).

Read only: nothing on Coinbase is changed from here. Everything every
exchange shares is the shared adapter's (D425); this says how Coinbase's
tickers, candles, trades and book are read.
"""

from collections.abc import AsyncGenerator
from typing import Any

from app.adapters.coinbase.feeds import (
    COINBASE_TICKER_COLUMNS,
    CoinbasePlace,
    book_answer,
    candles_page,
    ticker_rows,
    trades_page,
)
from app.adapters.coinbase.live import CoinbaseLive
from app.adapters.coinbase.markets import BY_KEY, HOSTS, Market
from app.adapters.coinbase.options import CoinbaseOptions
from app.adapters.coinbase.reading import CoinbaseReading
from app.adapters.coinbase.reports import PRESETS, coinbase_reports
from app.adapters.coinbase.session import CoinbaseSession
from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult
from app.adapters.live import LiveRows
from app.adapters.market.adapter import MarketAdapter
from app.adapters.market.catalog import place_in
from app.adapters.reading_on import BookmarkAccess
from app.adapters.registry import AdapterContext, register
from app.core.translation import N_


class CoinbaseAdapter(MarketAdapter[Market]):
    presets = PRESETS

    def __init__(
        self, session: CoinbaseSession, bookmarks: BookmarkAccess | None = None
    ) -> None:
        super().__init__(
            session, coinbase_reports(session), CoinbaseReading(session, bookmarks)
        )
        self._session = session
        self._live = CoinbaseLive(session)

    def connection_string(self) -> str:
        """The REST host this connection speaks to."""
        return HOSTS[self._session.hosts]

    def place_of(self, node_id: str) -> CoinbasePlace:
        return place_in(BY_KEY, node_id)

    async def ticker_rows(
        self, market: Market
    ) -> tuple[list[FetchColumn], list[list[str | None]]]:
        return COINBASE_TICKER_COLUMNS, await ticker_rows(self._session, market)

    async def candles_page(
        self, place: CoinbasePlace, request: FetchRequest
    ) -> FetchResult:
        return await candles_page(self._session, place, request)

    async def trades_page(
        self, place: CoinbasePlace, request: FetchRequest
    ) -> FetchResult:
        return await trades_page(self._session, place, request)

    async def read_book(
        self, market: Market, symbol: str, depth: int, node_id: str
    ) -> dict[str, Any]:
        return await book_answer(self._session, market, symbol, depth, node_id)

    def watch(
        self, place: CoinbasePlace, interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        assert place.symbol is not None
        return self._live.watch(place.market, place.symbol, interval, node_id)


@register(
    name="coinbase",
    title=N_("Coinbase Exchange"),
    category="market",
    description=N_(
        "Coinbase Exchange's public market data. See every product's last "
        "day and trading rules, read a product's candles, every trade it "
        "ever had and its order book as rows, and watch its market live. "
        "Nothing is changed on Coinbase."
    ),
    options_schema=CoinbaseOptions,
    adapter_class=CoinbaseAdapter,
)
def _build(options: CoinbaseOptions, context: AdapterContext) -> CoinbaseAdapter:
    return CoinbaseAdapter(CoinbaseSession(options, context.pooling), context.bookmarks)
