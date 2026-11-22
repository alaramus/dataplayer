"""A symbol watched live over Bybit's public streams (D429).

The frame is shared (D425): the streams first, then the snapshot over REST,
then batches. One socket a symbol and interval, told on opening which topics
to send — the trades, the book of fifty, the candle and the day — and pinged
every twenty seconds, as Bybit asks. Bybit sends the book as a snapshot then
deltas, and a futures ticker as a snapshot then the fields that changed, so
a watch keeps both and sends them whole, as Binance's are sent.
"""

import json
import time
from collections.abc import AsyncGenerator, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from app.adapters.bybit.feeds import (
    BYBIT_CANDLE_COLUMNS,
    BYBIT_TICKER_COLUMNS,
    BYBIT_TRADE_COLUMNS,
    candle_row,
    read_candles,
    recent_trades,
    ticker_row,
    trade_row,
    trade_time,
)
from app.adapters.bybit.markets import INTERVALS, STREAM_HOSTS, Market
from app.adapters.bybit.session import BybitSession
from app.adapters.live import LiveRows
from app.adapters.market.columns import BOOK_COLUMNS, book_rows, names
from app.adapters.market.live import (
    BOOK_LEVELS,
    SNAPSHOT_CANDLES,
    SNAPSHOT_TRADES,
    watch,
)
from app.adapters.market.stream import StreamSpec
from app.adapters.market.values import milliseconds
from app.adapters.protocol import AdapterError
from app.core.translation import say

# The depth of the book Bybit streams; twenty of its levels are shown.
STREAM_DEPTH = 50
PING = json.dumps({"op": "ping"})
# Bybit pushes the book of fifty every 20 ms; a screen is sent it at most
# this often, as Binance's comes twice or once a second.
BOOK_EVERY_SECONDS = 0.25


def stream_spec(
    endpoint: str, market: Market, symbol: str, interval: str
) -> StreamSpec:
    """The category's public socket, subscribed to one symbol's four topics.

    A topic Bybit does not know makes it drop the whole subscription on spot,
    so only these four are ever asked.
    """
    topics = [
        f"publicTrade.{symbol}",
        f"orderbook.{STREAM_DEPTH}.{symbol}",
        f"kline.{INTERVALS[interval]}.{symbol}",
        f"tickers.{symbol}",
    ]
    subscribe = json.dumps({"op": "subscribe", "args": topics})
    return StreamSpec(
        url=f"{STREAM_HOSTS[endpoint]}/v5/public/{market.key}",
        greeting=(subscribe,),
        ping=PING,
        ping_seconds=20.0,
    )


def _refusals() -> dict[int, AdapterError]:
    refused = AdapterError(
        "config",
        say(
            "Bybit refuses this address: too many requests, or a region it does not serve"
        ),
    )
    return {403: refused, 451: refused}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _price(text: Any) -> Decimal:
    try:
        return Decimal(str(text))
    except InvalidOperation:
        return Decimal(0)


class Book:
    """A side's levels by price, as Bybit's snapshot and deltas leave them."""

    def __init__(self) -> None:
        self.bids: dict[str, str] = {}
        self.asks: dict[str, str] = {}
        self.ready = False

    def apply(self, kind: str, data: dict[str, Any]) -> None:
        if kind == "snapshot":
            self.bids, self.asks, self.ready = {}, {}, True
        if not self.ready:
            return
        for side, key in ((self.bids, "b"), (self.asks, "a")):
            for entry in data.get(key) or []:
                if not isinstance(entry, list) or len(entry) < 2:
                    continue
                price, size = str(entry[0]), str(entry[1])
                if _price(size) == 0:
                    side.pop(price, None)
                else:
                    side[price] = size

    def rows(self) -> list[list[str | None]]:
        bids = sorted(self.bids.items(), key=lambda one: _price(one[0]), reverse=True)
        asks = sorted(self.asks.items(), key=lambda one: _price(one[0]))
        answer = {
            "bids": [list(one) for one in bids[:BOOK_LEVELS]],
            "asks": [list(one) for one in asks[:BOOK_LEVELS]],
        }
        return book_rows(answer, BOOK_LEVELS)


class BybitWatch:
    """One watch of a symbol's Market node at one interval."""

    def __init__(
        self,
        session: BybitSession,
        market: Market,
        symbol: str,
        interval: str,
        node_id: str,
    ) -> None:
        self._session = session
        self._market = market
        self._symbol = symbol
        self._interval = interval
        self._node_id = node_id
        self._book = Book()
        self._day: dict[str, Any] = {}
        # The newest trade said, by its time and the ids at that time, so a
        # trade the snapshot held is not said twice.
        self._newest_ms = -1
        self._newest_ids: set[str] = set()
        self._book_sent = 0.0

    def streams(self) -> Sequence[StreamSpec]:
        return [
            stream_spec(
                self._session.endpoint, self._market, self._symbol, self._interval
            )
        ]

    async def snapshot(self) -> list[LiveRows]:
        session, market, symbol = self._session, self._market, self._symbol
        node_id, interval = self._node_id, self._interval
        answer = await session.ask(market, "tickers", {"symbol": symbol}, node_id)
        days = [one for one in answer.get("list") or [] if isinstance(one, dict)]
        self._day = dict(days[0]) if days else {}
        klines = await read_candles(
            session, market, symbol, interval, [], True, SNAPSHOT_CANDLES, node_id
        )
        # The stream's own snapshot reaches only the watcher that opened it;
        # one that joins later starts from this and lays the deltas over it.
        book = await session.ask(
            market, "orderbook", {"symbol": symbol, "limit": str(STREAM_DEPTH)}, node_id
        )
        self._book.apply("snapshot", book)
        trades = (await recent_trades(session, market, symbol, node_id))[
            -SNAPSHOT_TRADES:
        ]
        for one in trades:
            self._remember(one)
        now = _now_ms()
        return [
            LiveRows(
                part="ticker",
                mode="replace",
                columns=names(BYBIT_TICKER_COLUMNS),
                rows=[ticker_row(market, self._day)] if self._day else [],
            ),
            LiveRows(
                part="candles",
                mode="replace",
                columns=names(BYBIT_CANDLE_COLUMNS),
                rows=[
                    candle_row(market, interval, raw, now) for raw in reversed(klines)
                ],
                key=["open_time"],
            ),
            LiveRows(
                part="order_book",
                mode="replace",
                columns=names(BOOK_COLUMNS),
                rows=self._book.rows(),
            ),
            LiveRows(
                part="trades",
                mode="replace",
                columns=names(BYBIT_TRADE_COLUMNS),
                rows=[trade_row(one) for one in trades],
            ),
        ]

    def _remember(self, trade: dict[str, Any]) -> None:
        at = trade_time(trade) or 0
        name = str(trade.get("execId", trade.get("i")))
        if at > self._newest_ms:
            self._newest_ms, self._newest_ids = at, {name}
        elif at == self._newest_ms:
            self._newest_ids.add(name)

    def _is_new(self, trade: dict[str, Any]) -> bool:
        at = trade_time(trade)
        if at is None or at < self._newest_ms:
            return False
        name = str(trade.get("execId", trade.get("i")))
        return not (at == self._newest_ms and name in self._newest_ids)

    def batch(self, item: dict[str, Any]) -> list[LiveRows]:
        topic = item.get("topic")
        data = item.get("data")
        if not isinstance(topic, str):
            # A subscription's answer or a pong: nothing to show.
            return []
        if topic.startswith("publicTrade.") and isinstance(data, list):
            fresh = [one for one in data if isinstance(one, dict) and self._is_new(one)]
            fresh.sort(key=lambda one: trade_time(one) or 0)
            for one in fresh:
                self._remember(one)
            if not fresh:
                return []
            return [
                LiveRows(
                    part="trades",
                    mode="append",
                    columns=names(BYBIT_TRADE_COLUMNS),
                    rows=[trade_row(one) for one in fresh],
                )
            ]
        if topic.startswith("orderbook.") and isinstance(data, dict):
            self._book.apply(str(item.get("type")), data)
            now = time.monotonic()
            if not self._book.ready or now - self._book_sent < BOOK_EVERY_SECONDS:
                return []
            self._book_sent = now
            return [
                LiveRows(
                    part="order_book",
                    mode="replace",
                    columns=names(BOOK_COLUMNS),
                    rows=self._book.rows(),
                )
            ]
        if topic.startswith("kline.") and isinstance(data, list):
            now = _now_ms()
            rows = [
                candle_row(
                    self._market,
                    self._interval,
                    [
                        one.get("start"),
                        one.get("open"),
                        one.get("high"),
                        one.get("low"),
                        one.get("close"),
                        one.get("volume"),
                        one.get("turnover"),
                    ],
                    now,
                )
                for one in data
                if isinstance(one, dict) and milliseconds(one.get("start")) is not None
            ]
            if not rows:
                return []
            return [
                LiveRows(
                    part="candles",
                    mode="upsert",
                    columns=names(BYBIT_CANDLE_COLUMNS),
                    rows=rows,
                    key=["open_time"],
                )
            ]
        if topic.startswith("tickers.") and isinstance(data, dict):
            # A futures delta carries only the fields that changed.
            if item.get("type") == "snapshot":
                self._day = {}
            self._day.update(data)
            return [
                LiveRows(
                    part="ticker",
                    mode="replace",
                    columns=names(BYBIT_TICKER_COLUMNS),
                    rows=[ticker_row(self._market, self._day)],
                )
            ]
        return []


class BybitLive:
    """The watch of a symbol's Market node."""

    def __init__(self, session: BybitSession) -> None:
        self._session = session

    async def watch(
        self, market: Market, symbol: str, interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        one = BybitWatch(self._session, market, symbol, interval, node_id)
        async for rows in watch(self._session, one, _refusals(), "Bybit"):
            yield rows
