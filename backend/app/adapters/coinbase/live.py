"""A product watched live over Coinbase's public feed (D441).

The frame is shared (D425): the stream first, then the snapshot over REST,
then batches. One socket a product, told on opening to send its `matches`,
`level2_batch` (the book's public channel, a snapshot then changes every
50 ms), `ticker` and `heartbeat`. Coinbase streams no candles, so the candle
still open is kept here from the trades as they come.
"""

import json
import time
from collections.abc import AsyncGenerator, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from app.adapters.coinbase.feeds import (
    COINBASE_CANDLE_COLUMNS,
    COINBASE_TICKER_COLUMNS,
    COINBASE_TRADE_COLUMNS,
    candle_row,
    iso_ms,
    newest_trade,
    read_candles,
    read_trades,
    ticker_row,
    trade_id,
    trade_row,
)
from app.adapters.coinbase.markets import INTERVALS, STREAM_HOSTS, Market
from app.adapters.coinbase.session import CoinbaseSession
from app.adapters.live import LiveRows
from app.adapters.market.columns import BOOK_COLUMNS, book_rows, names
from app.adapters.market.live import (
    BOOK_LEVELS,
    SNAPSHOT_CANDLES,
    SNAPSHOT_TRADES,
    watch,
)
from app.adapters.market.stream import StreamSpec
from app.adapters.protocol import AdapterError
from app.core.translation import say

CHANNELS = ["matches", "level2_batch", "ticker", "heartbeat"]
# The book's changes come every 50 ms; a screen is sent it at most this often.
BOOK_EVERY_SECONDS = 0.25


def stream_spec(hosts: str, symbol: str) -> StreamSpec:
    subscribe = {"type": "subscribe", "product_ids": [symbol], "channels": CHANNELS}
    return StreamSpec(url=STREAM_HOSTS[hosts], greeting=(json.dumps(subscribe),))


def _refusals() -> dict[int, AdapterError]:
    refused = AdapterError(
        "config",
        say("Coinbase refuses this address: a region it does not serve, or a block"),
    )
    return {403: refused, 451: refused}


def _number(text: Any) -> Decimal:
    try:
        return Decimal(str(text))
    except InvalidOperation:
        return Decimal(0)


class Book:
    """A side's levels by price, as Coinbase's snapshot and changes leave them."""

    def __init__(self) -> None:
        self.bids: dict[str, str] = {}
        self.asks: dict[str, str] = {}
        self.ready = False

    def reset(self, bids: Any, asks: Any) -> None:
        self.bids = {str(one[0]): str(one[1]) for one in bids or [] if len(one) >= 2}
        self.asks = {str(one[0]): str(one[1]) for one in asks or [] if len(one) >= 2}
        self.ready = True

    def change(self, changes: Any) -> None:
        for entry in changes if isinstance(changes, list) else []:
            if not isinstance(entry, list) or len(entry) < 3:
                continue
            side = self.bids if entry[0] == "buy" else self.asks
            price, size = str(entry[1]), str(entry[2])
            if _number(size) == 0:
                side.pop(price, None)
            else:
                side[price] = size

    def rows(self) -> list[list[str | None]]:
        bids = sorted(self.bids.items(), key=lambda one: _number(one[0]), reverse=True)
        asks = sorted(self.asks.items(), key=lambda one: _number(one[0]))
        answer = {
            "bids": [list(one) for one in bids[:BOOK_LEVELS]],
            "asks": [list(one) for one in asks[:BOOK_LEVELS]],
        }
        return book_rows(answer, BOOK_LEVELS)


class CoinbaseWatch:
    """One watch of a product's Market node at one interval."""

    def __init__(
        self,
        session: CoinbaseSession,
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
        self._book_sent = 0.0
        self._newest_id = 0
        self._day: dict[str, Any] = {"id": symbol}
        # The candle still open, as Coinbase writes one: seconds, low, high,
        # open, close, volume.
        self._candle: list[Any] | None = None

    def streams(self) -> Sequence[StreamSpec]:
        return [stream_spec(self._session.hosts, self._symbol)]

    def _ticker(self) -> LiveRows:
        return LiveRows(
            part="ticker",
            mode="replace",
            columns=names(COINBASE_TICKER_COLUMNS),
            rows=[ticker_row(self._day)],
        )

    def _book_rows(self) -> LiveRows:
        return LiveRows(
            part="order_book",
            mode="replace",
            columns=names(BOOK_COLUMNS),
            rows=self._book.rows(),
        )

    async def snapshot(self) -> list[LiveRows]:
        session, market, symbol = self._session, self._market, self._symbol
        node_id, interval = self._node_id, self._interval
        stats = await session.get(market, f"/products/{symbol}/stats", {}, node_id)
        if isinstance(stats, dict):
            self._day = {"id": symbol, **stats}
        candles = await read_candles(
            session, market, symbol, interval, [], True, SNAPSHOT_CANDLES, node_id
        )
        self._candle = list(candles[0]) if candles else None
        book = await session.get(
            market, f"/products/{symbol}/book", {"level": "2"}, node_id
        )
        if isinstance(book, dict):
            self._book.reset(book.get("bids"), book.get("asks"))
        newest = await newest_trade(session, market, symbol, node_id)
        trades: list[dict[str, Any]] = []
        if newest is not None:
            top = trade_id(newest) or 0
            trades = await read_trades(
                session, market, symbol, max(1, top - SNAPSHOT_TRADES + 1), top, node_id
            )
            self._newest_id = top
        now = int(time.time() * 1000)
        return [
            self._ticker(),
            LiveRows(
                part="candles",
                mode="replace",
                columns=names(COINBASE_CANDLE_COLUMNS),
                rows=[candle_row(interval, raw, now) for raw in reversed(candles)],
                key=["open_time"],
            ),
            self._book_rows(),
            LiveRows(
                part="trades",
                mode="replace",
                columns=names(COINBASE_TRADE_COLUMNS),
                rows=[trade_row(one) for one in trades],
            ),
        ]

    def _lay(self, trade: dict[str, Any]) -> list[str | None] | None:
        """The candle still open with a trade laid over it."""
        at = iso_ms(trade.get("time"))
        price, size = str(trade.get("price")), _number(trade.get("size"))
        if at is None:
            return None
        step = INTERVALS[self._interval]
        opens = at // 1000 - (at // 1000) % step
        candle = self._candle
        if candle is None or opens > int(candle[0]):
            candle = [opens, price, price, price, price, str(size)]
        elif opens == int(candle[0]):
            if _number(price) < _number(candle[1]):
                candle[1] = price
            if _number(price) > _number(candle[2]):
                candle[2] = price
            candle[4] = price
            candle[5] = str(_number(candle[5]) + size)
        else:
            return None
        self._candle = candle
        return candle_row(self._interval, candle, int(time.time() * 1000))

    def batch(self, item: dict[str, Any]) -> list[LiveRows]:
        kind = item.get("type")
        if kind in {"match", "last_match"}:
            if (trade_id(item) or 0) <= self._newest_id:
                return []
            self._newest_id = trade_id(item) or self._newest_id
            found = [
                LiveRows(
                    part="trades",
                    mode="append",
                    columns=names(COINBASE_TRADE_COLUMNS),
                    rows=[trade_row(item)],
                )
            ]
            candle = self._lay(item)
            if candle is not None:
                found.append(
                    LiveRows(
                        part="candles",
                        mode="upsert",
                        columns=names(COINBASE_CANDLE_COLUMNS),
                        rows=[candle],
                        key=["open_time"],
                    )
                )
            return found
        if kind in {"snapshot", "l2update"}:
            if kind == "snapshot":
                self._book.reset(item.get("bids"), item.get("asks"))
            else:
                self._book.change(item.get("changes"))
            now = time.monotonic()
            if not self._book.ready or now - self._book_sent < BOOK_EVERY_SECONDS:
                return []
            self._book_sent = now
            return [self._book_rows()]
        if kind == "ticker":
            self._day.update(
                {
                    "last": item.get("price"),
                    "open": item.get("open_24h"),
                    "high": item.get("high_24h"),
                    "low": item.get("low_24h"),
                    "volume": item.get("volume_24h"),
                }
            )
            return [self._ticker()]
        # Subscriptions, heartbeats and errors change nothing on screen.
        return []


class CoinbaseLive:
    def __init__(self, session: CoinbaseSession) -> None:
        self._session = session

    async def watch(
        self, market: Market, symbol: str, interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        one = CoinbaseWatch(self._session, market, symbol, interval, node_id)
        async for rows in watch(self._session, one, _refusals(), "Coinbase"):
            yield rows
