"""A symbol watched live over OKX's public streams (D435).

The frame is shared (D425): the streams first, then the snapshot over REST,
then batches. OKX puts the book and the ticker on its `public` socket and
candles and every single trade on its `business` one, so a watch has two
sockets, each told on opening what to send and pinged with a plain `ping`
every twenty seconds; OKX answers a plain `pong`. The book comes as a
snapshot then updates, a size of 0 removing a level, so a watch keeps it and
sends it whole, as Bybit's.
"""

import json
import time
from collections.abc import AsyncGenerator, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from app.adapters.live import LiveRows
from app.adapters.market.columns import BOOK_COLUMNS, book_rows, names
from app.adapters.market.live import (
    BOOK_LEVELS,
    SNAPSHOT_CANDLES,
    SNAPSHOT_TRADES,
    watch,
)
from app.adapters.market.stream import StreamSpec
from app.adapters.okx.feeds import (
    OKX_CANDLE_COLUMNS,
    candle_row,
    newest_trade,
    read_candles,
    read_trades,
    sized,
    ticker_columns,
    ticker_row,
    trade_columns,
    trade_id,
    trade_row,
)
from app.adapters.okx.markets import DEEPEST_BOOK, INTERVALS, STREAM_HOSTS, Market
from app.adapters.okx.session import BOOKS, TICKER, OkxSession, OkxSymbol
from app.adapters.protocol import AdapterError
from app.core.translation import say

PING = "ping"
PONG = "pong"
# OKX pushes the book every 100 ms; a screen is sent it at most this often.
BOOK_EVERY_SECONDS = 0.25


def stream_specs(hosts: str, symbol: str, interval: str) -> list[StreamSpec]:
    """The public socket for the book and the day, the business one for
    candles and trades: OKX serves a candle on no other."""
    host = STREAM_HOSTS[hosts]

    def spec(path: str, channels: list[str]) -> StreamSpec:
        args = [{"channel": channel, "instId": symbol} for channel in channels]
        return StreamSpec(
            url=f"{host}/ws/v5/{path}",
            greeting=(json.dumps({"op": "subscribe", "args": args}),),
            ping=PING,
            ping_seconds=20.0,
            pong=PONG,
        )

    return [
        spec("public", ["books", "tickers"]),
        spec("business", [f"candle{INTERVALS[interval]}", "trades-all"]),
    ]


def _refusals() -> dict[int, AdapterError]:
    refused = AdapterError(
        "config",
        say("OKX does not serve this address or region; choose another endpoint"),
    )
    return {403: refused, 451: refused}


def _price(text: Any) -> Decimal:
    try:
        return Decimal(str(text))
    except InvalidOperation:
        return Decimal(0)


class Book:
    """A side's levels by price, in contracts or the base, as OKX leaves them."""

    def __init__(self) -> None:
        self.bids: dict[str, str] = {}
        self.asks: dict[str, str] = {}
        self.ready = False

    def apply(self, action: str, data: dict[str, Any]) -> None:
        if action == "snapshot":
            self.bids, self.asks, self.ready = {}, {}, True
        if not self.ready:
            return
        for side, key in ((self.bids, "bids"), (self.asks, "asks")):
            for entry in data.get(key) or []:
                if not isinstance(entry, list) or len(entry) < 2:
                    continue
                price, size = str(entry[0]), str(entry[1])
                if _price(size) == 0:
                    side.pop(price, None)
                else:
                    side[price] = size

    def rows(self, market: Market, value: str | None) -> list[list[str | None]]:
        bids = sorted(self.bids.items(), key=lambda one: _price(one[0]), reverse=True)
        asks = sorted(self.asks.items(), key=lambda one: _price(one[0]))
        answer = {
            "bids": sized(market, [list(one) for one in bids[:BOOK_LEVELS]], value),
            "asks": sized(market, [list(one) for one in asks[:BOOK_LEVELS]], value),
        }
        return book_rows(answer, BOOK_LEVELS)


class OkxWatch:
    """One watch of a symbol's Market node at one interval."""

    def __init__(
        self,
        session: OkxSession,
        market: Market,
        instrument: OkxSymbol,
        interval: str,
        node_id: str,
    ) -> None:
        self._session = session
        self._market = market
        self._instrument = instrument
        self._symbol = instrument.name
        self._interval = interval
        self._node_id = node_id
        self._book = Book()
        self._book_sent = 0.0
        # The newest trade said: OKX's ids only grow, so anything at or
        # below it the snapshot already held.
        self._newest_id = 0

    def streams(self) -> Sequence[StreamSpec]:
        return stream_specs(self._session.hosts, self._symbol, self._interval)

    def _ticker(self, item: dict[str, Any]) -> LiveRows:
        return LiveRows(
            part="ticker",
            mode="replace",
            columns=names(ticker_columns(self._market)),
            rows=[ticker_row(self._market, item, self._instrument)],
        )

    def _book_rows(self) -> LiveRows:
        return LiveRows(
            part="order_book",
            mode="replace",
            columns=names(BOOK_COLUMNS),
            rows=self._book.rows(self._market, self._instrument.contract_value),
        )

    def _trades(self, found: list[dict[str, Any]], mode: str) -> LiveRows:
        value = self._instrument.contract_value
        return LiveRows(
            part="trades",
            mode="append" if mode == "append" else "replace",
            columns=names(trade_columns(self._market)),
            rows=[trade_row(self._market, one, value) for one in found],
        )

    async def snapshot(self) -> list[LiveRows]:
        session, market, symbol = self._session, self._market, self._symbol
        node_id, interval = self._node_id, self._interval
        days = await session.get(market, TICKER, {"instId": symbol}, node_id)
        day = next((one for one in days or [] if isinstance(one, dict)), None)
        candles = await read_candles(
            session, market, symbol, interval, [], True, SNAPSHOT_CANDLES, node_id
        )
        # The stream's own snapshot reaches only the watcher that opened it;
        # one that joins later starts from this and lays the updates over it.
        books = await session.get(
            market, BOOKS, {"instId": symbol, "sz": str(DEEPEST_BOOK)}, node_id
        )
        self._book.apply("snapshot", books[0] if books else {})
        newest = await newest_trade(session, market, symbol, node_id)
        trades: list[dict[str, Any]] = []
        if newest is not None:
            top = trade_id(newest) or 0
            first = max(1, top - SNAPSHOT_TRADES + 1)
            trades = await read_trades(session, market, symbol, first, top, node_id)
            self._newest_id = top
        return [
            self._ticker(day)
            if day is not None
            else LiveRows(
                part="ticker",
                mode="replace",
                columns=names(ticker_columns(market)),
                rows=[],
            ),
            LiveRows(
                part="candles",
                mode="replace",
                columns=names(OKX_CANDLE_COLUMNS),
                rows=[candle_row(market, interval, raw) for raw in reversed(candles)],
                key=["open_time"],
            ),
            self._book_rows(),
            self._trades(trades, "replace"),
        ]

    def batch(self, item: dict[str, Any]) -> list[LiveRows]:
        argument = item.get("arg")
        data = item.get("data")
        if not isinstance(argument, dict) or not isinstance(data, list):
            # A subscription's answer, a notice or an error: nothing to show.
            return []
        channel = str(argument.get("channel") or "")
        if channel == "trades-all":
            fresh = [
                one
                for one in data
                if isinstance(one, dict) and (trade_id(one) or 0) > self._newest_id
            ]
            fresh.sort(key=lambda one: trade_id(one) or 0)
            if not fresh:
                return []
            self._newest_id = trade_id(fresh[-1]) or self._newest_id
            return [self._trades(fresh, "append")]
        if channel == "books":
            for one in data:
                if isinstance(one, dict):
                    self._book.apply(str(item.get("action")), one)
            now = time.monotonic()
            if not self._book.ready or now - self._book_sent < BOOK_EVERY_SECONDS:
                return []
            self._book_sent = now
            return [self._book_rows()]
        if channel.startswith("candle"):
            rows = [
                candle_row(self._market, self._interval, raw)
                for raw in data
                if isinstance(raw, list) and raw
            ]
            if not rows:
                return []
            return [
                LiveRows(
                    part="candles",
                    mode="upsert",
                    columns=names(OKX_CANDLE_COLUMNS),
                    rows=rows,
                    key=["open_time"],
                )
            ]
        if channel == "tickers":
            days = [one for one in data if isinstance(one, dict)]
            return [self._ticker(days[-1])] if days else []
        return []


class OkxLive:
    """The watch of a symbol's Market node."""

    def __init__(self, session: OkxSession) -> None:
        self._session = session

    async def watch(
        self, market: Market, symbol: str, interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        instrument = await self._session.instrument(market, symbol, node_id)
        one = OkxWatch(self._session, market, instrument, interval, node_id)
        async for rows in watch(self._session, one, _refusals(), "OKX"):
            yield rows
