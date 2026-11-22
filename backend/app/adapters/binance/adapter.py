"""Binance's market data as a source: markets, symbols and their feeds, and
with a key the account it reads (D322).

Read only: nothing on Binance is changed from here (D316). Everything is
read over REST through one client a connection; what every exchange shares
is the shared adapter's (D425).
"""

import time
from collections.abc import AsyncGenerator
from typing import Any

from app.adapters.binance.account import (
    account_feeds,
    account_page,
    more_than_reading,
    restrictions,
)
from app.adapters.binance.catalog import place_of
from app.adapters.binance.feeds import (
    BinancePlace,
    book_answer,
    candles_page,
    checked_candles,
    contract_size_of,
    read_candles,
    ticker_rows,
    trades_page,
)
from app.adapters.binance.live import BinanceLive
from app.adapters.binance.markets import HOSTS, Market, market_of
from app.adapters.binance.metrics import PRESETS as METRIC_PRESETS
from app.adapters.binance.options import HOSTS_OF, BinanceOptions
from app.adapters.binance.reading import BinanceReading
from app.adapters.binance.reports import binance_reports
from app.adapters.binance.session import BinanceSession
from app.adapters.catalog import FeedName
from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult
from app.adapters.live import LiveRows
from app.adapters.market.adapter import MarketAdapter, key_checked
from app.adapters.market.columns import CANDLE_COLUMNS, DEPTH_CEILING, TICKER_COLUMNS
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.adapters.reading_on import BookmarkAccess
from app.adapters.registry import AdapterContext, register
from app.core.translation import N_, say


def _now_ms() -> int:
    return int(time.time() * 1000)


class BinanceAdapter(MarketAdapter[Market]):
    presets = METRIC_PRESETS

    def __init__(
        self, session: BinanceSession, bookmarks: BookmarkAccess | None = None
    ) -> None:
        super().__init__(
            session, binance_reports(session), BinanceReading(session, bookmarks)
        )
        self._session = session
        self._live = BinanceLive(session)

    def connection_string(self) -> str:
        """The spot host this connection speaks to; a key is never part of it."""
        return HOSTS[HOSTS_OF[self._session.options.endpoint]]["spot"]

    def place_of(self, node_id: str) -> BinancePlace:
        return place_of(node_id)

    async def check_connection(self) -> ConnectionCheckResult:
        checked = await self._session.check()
        if not checked.ok or not self._session.keyed:
            return checked
        return await self._check_key(checked)

    async def _check_key(self, checked: ConnectionCheckResult) -> ConnectionCheckResult:
        """The key read with, and said when it may do more than read (D322).

        The testnet cannot be asked what a key may do, so its key is only
        tried.
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
        return key_checked(checked, answer is not None and more_than_reading(answer))

    # --- what Binance reads its own way ---------------------------------------------

    def account_feeds(self, market: Market) -> list[FeedName]:
        return account_feeds(market, self._session.main_hosts)

    async def account_page(
        self, place: BinancePlace, request: FetchRequest
    ) -> FetchResult:
        return await account_page(self._session, place, request)

    async def ticker_rows(
        self, market: Market
    ) -> tuple[list[FetchColumn], list[list[str | None]]]:
        return TICKER_COLUMNS, await ticker_rows(self._session, market)

    async def candles_page(
        self, place: BinancePlace, request: FetchRequest
    ) -> FetchResult:
        return await candles_page(self._session, place, request, _now_ms())

    async def trades_page(
        self, place: BinancePlace, request: FetchRequest
    ) -> FetchResult:
        return await trades_page(self._session, place, request)

    async def read_book(
        self, market: Market, symbol: str, depth: int, node_id: str
    ) -> dict[str, Any]:
        return await book_answer(self._session, market, symbol, depth, node_id)

    def watch(
        self, place: BinancePlace, interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        assert place.symbol is not None
        return self._live.watch(place.market, place.symbol, interval, node_id)

    async def export_candles(
        self, place: BinancePlace, request: ExportRequest
    ) -> tuple[list[list[str | None]], list[str]] | None:
        assert place.symbol is not None and place.interval is not None
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
        return [one.row(now, size) for one in candles], [c.name for c in CANDLE_COLUMNS]


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
