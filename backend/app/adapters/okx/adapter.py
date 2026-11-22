"""OKX's market data as a source: spot, linear and inverse, their symbols
and feeds (D432, D433).

Read only: nothing on OKX is changed from here. Everything every exchange
shares is the shared adapter's (D425); this says how OKX's tickers, candles,
trades and book are read.
"""

from collections.abc import AsyncGenerator
from typing import Any, ClassVar

from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult
from app.adapters.live import LiveRows
from app.adapters.market.adapter import MarketAdapter
from app.adapters.market.catalog import place_in
from app.adapters.metrics import MetricSample
from app.adapters.okx.feeds import (
    OkxPlace,
    book_answer,
    candles_page,
    ticker_columns,
    ticker_rows,
    trades_page,
)
from app.adapters.okx.live import OkxLive
from app.adapters.okx.markets import BY_KEY, HOSTS, Market
from app.adapters.okx.options import OkxOptions
from app.adapters.okx.reading import OkxReading
from app.adapters.okx.reports import PRESETS, metric_samples, okx_reports
from app.adapters.okx.session import OkxSession
from app.adapters.reading_on import BookmarkAccess
from app.adapters.registry import AdapterContext, register
from app.core.translation import N_


class OkxAdapter(MarketAdapter[Market]):
    presets = PRESETS
    # OKX says a minimum order size, not a minimum notional.
    symbol_columns_left_out: ClassVar[frozenset[str]] = frozenset({"min_notional"})

    def __init__(
        self, session: OkxSession, bookmarks: BookmarkAccess | None = None
    ) -> None:
        super().__init__(session, okx_reports(session), OkxReading(session, bookmarks))
        self._session = session
        self._live = OkxLive(session)

    def connection_string(self) -> str:
        """The REST host this connection speaks to."""
        return HOSTS[self._session.hosts]

    def place_of(self, node_id: str) -> OkxPlace:
        return place_in(BY_KEY, node_id)

    async def metric_samples(self) -> list[MetricSample]:
        return await metric_samples(self._session)

    async def ticker_rows(
        self, market: Market
    ) -> tuple[list[FetchColumn], list[list[str | None]]]:
        return ticker_columns(market), await ticker_rows(self._session, market)

    async def candles_page(self, place: OkxPlace, request: FetchRequest) -> FetchResult:
        return await candles_page(self._session, place, request)

    async def trades_page(self, place: OkxPlace, request: FetchRequest) -> FetchResult:
        return await trades_page(self._session, place, request)

    async def read_book(
        self, market: Market, symbol: str, depth: int, node_id: str
    ) -> dict[str, Any]:
        return await book_answer(self._session, market, symbol, depth, node_id)

    def watch(
        self, place: OkxPlace, interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        assert place.symbol is not None
        return self._live.watch(place.market, place.symbol, interval, node_id)


@register(
    name="okx",
    title=N_("OKX"),
    category="market",
    description=N_(
        "OKX's public market data: spot, USDT and USDC futures and inverse "
        "futures, perpetual and dated. See every symbol's last day and "
        "trading rules, read a symbol's candles of any interval, its trades "
        "of the last three months and its order book as rows, and watch its "
        "market live. Nothing is changed on OKX."
    ),
    options_schema=OkxOptions,
    adapter_class=OkxAdapter,
)
def _build(options: OkxOptions, context: AdapterContext) -> OkxAdapter:
    return OkxAdapter(OkxSession(options, context.pooling), context.bookmarks)
