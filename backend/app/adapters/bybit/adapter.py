"""Bybit's market data as a source: spot, linear and inverse, their symbols
and feeds (D426, D427).

Read only, and no key in this round: nothing on Bybit is changed from here.
Everything every exchange shares is the shared adapter's (D425); this says
how Bybit's tickers, candles, trades and book are read.
"""

from collections.abc import AsyncGenerator
from typing import Any

from app.adapters.bybit.account import (
    account_feeds,
    account_page,
    key_info,
    more_than_reading,
)
from app.adapters.bybit.feeds import (
    BYBIT_TICKER_COLUMNS,
    BybitPlace,
    book_answer,
    candles_page,
    ticker_rows,
    trades_page,
)
from app.adapters.bybit.live import BybitLive
from app.adapters.bybit.markets import BY_KEY, HOSTS, Market
from app.adapters.bybit.options import BybitOptions
from app.adapters.bybit.reading import BybitReading
from app.adapters.bybit.reports import PRESETS, bybit_reports
from app.adapters.bybit.session import BybitSession
from app.adapters.catalog import FeedName
from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult
from app.adapters.live import LiveRows
from app.adapters.market.adapter import MarketAdapter, key_checked
from app.adapters.market.catalog import place_in
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.adapters.reading_on import BookmarkAccess
from app.adapters.registry import AdapterContext, register
from app.core.translation import N_


class BybitAdapter(MarketAdapter[Market]):
    presets = PRESETS

    def __init__(
        self, session: BybitSession, bookmarks: BookmarkAccess | None = None
    ) -> None:
        super().__init__(
            session, bybit_reports(session), BybitReading(session, bookmarks)
        )
        self._session = session
        self._live = BybitLive(session)

    def connection_string(self) -> str:
        """The REST host this connection speaks to."""
        return HOSTS[self._session.hosts]

    def place_of(self, node_id: str) -> BybitPlace:
        return place_in(BY_KEY, node_id)

    async def check_connection(self) -> ConnectionCheckResult:
        """The markets reached, and with a key what Bybit says it may do (D431).

        Any key may read the account; one that is not read-only passes and is
        said to do more.
        """
        checked = await self._session.check()
        if not checked.ok or not self._session.keyed:
            return checked
        try:
            info = await key_info(self._session)
        except AdapterError as failure:
            return ConnectionCheckResult(
                ok=False, message=failure.message, error_kind=failure.error_kind
            )
        return key_checked(checked, more_than_reading(info))

    # --- the account a key reads (D431) --------------------------------------

    def account_feeds(self, market: Market) -> list[FeedName]:
        return account_feeds(market)

    async def account_page(
        self, place: BybitPlace, request: FetchRequest
    ) -> FetchResult:
        return await account_page(self._session, place, request)

    async def ticker_rows(
        self, market: Market
    ) -> tuple[list[FetchColumn], list[list[str | None]]]:
        return BYBIT_TICKER_COLUMNS, await ticker_rows(self._session, market)

    async def candles_page(
        self, place: BybitPlace, request: FetchRequest
    ) -> FetchResult:
        return await candles_page(self._session, place, request)

    async def trades_page(
        self, place: BybitPlace, request: FetchRequest
    ) -> FetchResult:
        return await trades_page(self._session, place, request)

    async def read_book(
        self, market: Market, symbol: str, depth: int, node_id: str
    ) -> dict[str, Any]:
        return await book_answer(self._session, market, symbol, depth, node_id)

    def watch(
        self, place: BybitPlace, interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        assert place.symbol is not None
        return self._live.watch(place.market, place.symbol, interval, node_id)


@register(
    name="bybit",
    title=N_("Bybit"),
    category="market",
    description=N_(
        "Bybit's public market data: spot, USDT and USDC futures and inverse "
        "futures. See every symbol's last day and trading rules, read a "
        "symbol's candles of any interval, its newest trades and its order "
        "book as rows, and watch its market live. With a read-only key, its "
        "unified account too. Nothing is changed on Bybit."
    ),
    options_schema=BybitOptions,
    adapter_class=BybitAdapter,
)
def _build(options: BybitOptions, context: AdapterContext) -> BybitAdapter:
    return BybitAdapter(BybitSession(options, context.pooling), context.bookmarks)
