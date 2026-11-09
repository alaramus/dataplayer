"""A symbol watched live: its day, candles, book and trades as they change (D323).

What a watch first says is read over REST, as the grid reads it; what
changes after comes from Binance's market streams, which cost no weight.
One upstream socket a symbol and interval for a connection, however many
screens watch it: a stream is kept with the connection's client (D316),
started by the first watcher and stopped by the last.

Every batch is rows in the columns the grid already shows for the same
feed, so the trade, book, candle and ticker rows read the same either way.
"""

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus, WebSocketException

from app.adapters.binance.feeds import (
    BOOK_COLUMNS,
    CANDLE_COLUMNS,
    TICKER_COLUMNS,
    TRADE_COLUMNS,
    Candle,
    book_rows,
    contract_size_of,
    read_candles,
    ticker_row,
    trade_row,
    whole_of,
)
from app.adapters.binance.markets import Market, MarketKey
from app.adapters.binance.options import Hosts
from app.adapters.binance.session import BinanceSession
from app.adapters.live import LiveRows
from app.adapters.protocol import AdapterError
from app.core.translation import say

logger = logging.getLogger(__name__)

# Where each market's streams are, by the hosts an endpoint speaks to.
STREAM_HOSTS: dict[Hosts, dict[MarketKey, str]] = {
    "binance": {
        "spot": "wss://stream.binance.com:9443",
        "usdm": "wss://fstream.binance.com",
        "coinm": "wss://dstream.binance.com",
    },
    "market_data": {
        "spot": "wss://data-stream.binance.vision",
        "usdm": "wss://fstream.binance.com",
        "coinm": "wss://dstream.binance.com",
    },
    "testnet": {
        "spot": "wss://stream.testnet.binance.vision",
        "usdm": "wss://stream.binancefuture.com",
        "coinm": "wss://dstream.binancefuture.com",
    },
}

DEFAULT_INTERVAL = "1m"
SNAPSHOT_CANDLES = 300
SNAPSHOT_TRADES = 100
BOOK_LEVELS = 20
# A watcher that falls this far behind loses the oldest batches first: a
# book or a candle is replaced by the next one anyway.
QUEUE_SIZE = 500
OPEN_TIMEOUT_SECONDS = 10.0
RETRY_SECONDS = (1.0, 2.0, 5.0, 10.0, 30.0)

type Item = dict[str, Any] | AdapterError


def stream_urls(hosts: Hosts, market: Market, symbol: str, interval: str) -> list[str]:
    """The streams of a symbol's trades, book, candle and day.

    Spot's book of twenty levels comes every second; futures' every half.
    USDⓈ-M serves its book from `/public` and the rest from `/market`: its
    plain `/stream` still answers and carries the book alone, which is how
    the split was found. Spot and COIN-M take all four on one socket.
    """
    name = symbol.lower()
    host = STREAM_HOSTS[hosts][market.key]
    depth = f"{name}@depth20" if market.key == "spot" else f"{name}@depth20@500ms"
    rest = (f"{name}@aggTrade", f"{name}@kline_{interval}", f"{name}@ticker")
    if market.key == "usdm":
        return [
            f"{host}/public/stream?streams={depth}",
            f"{host}/market/stream?streams={'/'.join(rest)}",
        ]
    return [f"{host}/stream?streams={'/'.join((depth, *rest))}"]


@dataclass
class MarketStream:
    """One upstream socket, and the queue of every watcher of it."""

    url: str
    on_idle: Callable[[MarketStream], None] = lambda stream: None
    queues: set[asyncio.Queue[Item]] = field(default_factory=set)
    task: asyncio.Task[None] | None = None

    @asynccontextmanager
    async def watched(self, queue: asyncio.Queue[Item]) -> AsyncIterator[None]:
        """What the stream says goes into the queue until the watcher leaves."""
        self.queues.add(queue)
        if self.task is None:
            self.task = asyncio.create_task(self._run())
        try:
            yield
        finally:
            self.queues.discard(queue)
            if not self.queues:
                await self.close()
                self.on_idle(self)

    def _publish(self, item: Item) -> None:
        for queue in self.queues:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(item)

    async def _run(self) -> None:
        """Read the upstream until nobody watches, coming back after a drop."""
        attempt = 0
        while True:
            try:
                async with connect(
                    self.url,
                    proxy=None,
                    open_timeout=OPEN_TIMEOUT_SECONDS,
                    # A watcher that leaves is not kept waiting for Binance to
                    # agree the socket is closed.
                    close_timeout=1.0,
                    max_size=2**20,
                ) as socket:
                    attempt = 0
                    async for message in socket:
                        self._publish(json.loads(message))
            except InvalidStatus as refusal:
                if refusal.response.status_code == 451:
                    self._publish(
                        AdapterError(
                            "config",
                            say(
                                "Binance does not serve this address; "
                                "choose another endpoint"
                            ),
                        )
                    )
                    return
                logger.warning(
                    "Binance stream refused: %s", refusal.response.status_code
                )
            except (OSError, TimeoutError, WebSocketException, ValueError) as failure:
                logger.info("Binance stream dropped: %r", failure)
            delay = RETRY_SECONDS[min(attempt, len(RETRY_SECONDS) - 1)]
            attempt += 1
            await asyncio.sleep(delay)

    async def close(self) -> None:
        task, self.task = self.task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ticker(data: dict[str, Any], contract_size: int | None) -> list[str | None]:
    """A day from the stream, named as the REST ticker names it.

    COIN-M's stream counts `v` in contracts and `q` in the base asset, as its
    REST answer does under other names (D321).
    """
    item: dict[str, Any] = {
        "symbol": data.get("s"),
        "lastPrice": data.get("c"),
        "priceChange": data.get("p"),
        "priceChangePercent": data.get("P"),
        "weightedAvgPrice": data.get("w"),
        "openPrice": data.get("o"),
        "highPrice": data.get("h"),
        "lowPrice": data.get("l"),
        "count": data.get("n"),
        "openTime": data.get("O"),
        "closeTime": data.get("C"),
        "volume": data.get("v"),
    }
    item["baseVolume" if contract_size is not None else "quoteVolume"] = data.get("q")
    return ticker_row(item, contract_size)


def _candle(data: dict[str, Any]) -> Candle | None:
    """A candle from the stream, laid out as REST lays a kline."""
    k = data.get("k")
    if not isinstance(k, dict) or whole_of(k.get("t")) is None:
        return None
    raw = [k["t"], k.get("o"), k.get("h"), k.get("l"), k.get("c"), k.get("v")]
    raw += [k.get("T"), k.get("q"), k.get("n"), k.get("V"), k.get("Q")]
    return Candle(int(k["t"]), raw)


def _names(columns: list[Any]) -> list[str]:
    return [column.name for column in columns]


class BinanceLive:
    """The watch of a symbol's Market node."""

    def __init__(self, session: BinanceSession) -> None:
        self._session = session

    async def snapshot(
        self, market: Market, symbol: str, interval: str, node_id: str
    ) -> tuple[list[LiveRows], int]:
        """The symbol as it stands, and the newest trade id it holds."""
        session = self._session
        size = await contract_size_of(session, market, symbol, node_id)
        now = _now_ms()
        day = await session.get(market, "ticker/24hr", {"symbol": symbol}, node_id)
        # COIN-M answers a list even for one symbol.
        day = day[0] if isinstance(day, list) and day else day
        candles = await read_candles(
            session, market, symbol, interval, [], True, SNAPSHOT_CANDLES, node_id
        )
        book = await session.get(
            market, "depth", {"symbol": symbol, "limit": str(BOOK_LEVELS)}, node_id
        )
        trades = await session.get(
            market,
            "aggTrades",
            {"symbol": symbol, "limit": str(SNAPSHOT_TRADES)},
            node_id,
        )
        trades = [one for one in trades if isinstance(one, dict) and "a" in one]
        newest = max((int(one["a"]) for one in trades), default=-1)
        return [
            LiveRows(
                part="ticker",
                mode="replace",
                columns=_names(TICKER_COLUMNS),
                rows=[ticker_row(day, size)] if isinstance(day, dict) else [],
            ),
            LiveRows(
                part="candles",
                mode="replace",
                columns=_names(CANDLE_COLUMNS),
                rows=[one.row(now, size) for one in reversed(candles)],
                key=["open_time"],
            ),
            LiveRows(
                part="order_book",
                mode="replace",
                columns=_names(BOOK_COLUMNS),
                rows=book_rows(book, BOOK_LEVELS) if isinstance(book, dict) else [],
            ),
            LiveRows(
                part="trades",
                mode="replace",
                columns=_names(TRADE_COLUMNS),
                rows=[trade_row(one) for one in trades],
            ),
        ], newest

    def batch(
        self, item: dict[str, Any], size: int | None, newest: int
    ) -> tuple[LiveRows | None, int]:
        """One message of the stream as rows, and the newest trade id after it."""
        stream = item.get("stream")
        data = item.get("data")
        if not isinstance(stream, str) or not isinstance(data, dict):
            return None, newest
        if stream.endswith("@aggTrade"):
            trade_id = whole_of(data.get("a"))
            # Trades the snapshot already held are not said twice.
            if trade_id is None or trade_id <= newest:
                return None, newest
            rows = [trade_row(data)]
            return LiveRows(
                part="trades", mode="append", columns=_names(TRADE_COLUMNS), rows=rows
            ), trade_id
        if "@depth" in stream:
            # Spot names the sides `bids` and `asks`, futures `b` and `a`.
            book = {
                "bids": data.get("bids", data.get("b")) or [],
                "asks": data.get("asks", data.get("a")) or [],
            }
            return LiveRows(
                part="order_book",
                mode="replace",
                columns=_names(BOOK_COLUMNS),
                rows=book_rows(book, BOOK_LEVELS),
            ), newest
        if "@kline_" in stream:
            candle = _candle(data)
            if candle is None:
                return None, newest
            return LiveRows(
                part="candles",
                mode="upsert",
                columns=_names(CANDLE_COLUMNS),
                rows=[candle.row(_now_ms(), size)],
                key=["open_time"],
            ), newest
        if stream.endswith("@ticker"):
            return LiveRows(
                part="ticker",
                mode="replace",
                columns=_names(TICKER_COLUMNS),
                rows=[_ticker(data, size)],
            ), newest
        return None, newest

    async def watch(
        self, market: Market, symbol: str, interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        session = self._session
        size = await contract_size_of(session, market, symbol, node_id)
        queue: asyncio.Queue[Item] = asyncio.Queue(maxsize=QUEUE_SIZE)
        async with session.kept() as kept, contextlib.AsyncExitStack() as held:
            for url in stream_urls(session.hosts, market, symbol, interval):
                found = kept.streams.get(url)
                stream = found if isinstance(found, MarketStream) else None
                if stream is None:
                    stream = MarketStream(url, on_idle=kept.forget_stream)
                    kept.streams[url] = stream
                # Watched before the snapshot is read, so nothing between the
                # two is missed; what both hold is left out by its id.
                await held.enter_async_context(stream.watched(queue))
            frames, newest = await self.snapshot(market, symbol, interval, node_id)
            for frame in frames:
                yield frame
            while True:
                item = await queue.get()
                if isinstance(item, AdapterError):
                    raise item
                rows, newest = self.batch(item, size, newest)
                if rows is not None:
                    yield rows
