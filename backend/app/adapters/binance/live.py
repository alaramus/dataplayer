"""A symbol watched live: its day, candles, book and trades as they change (D323).

The frame is shared (D425): the snapshot over REST, then the streams, one
upstream socket a symbol and interval for a connection however many screens
watch it. This says where Binance's streams are and what their messages mean;
they cost no weight.
"""

import time
from collections.abc import AsyncGenerator, Sequence
from typing import Any

from app.adapters.binance.feeds import (
    Candle,
    contract_size_of,
    read_candles,
    ticker_row,
    trade_row,
)
from app.adapters.binance.markets import Market, MarketKey
from app.adapters.binance.options import Hosts
from app.adapters.binance.session import BinanceSession
from app.adapters.live import LiveRows
from app.adapters.market.columns import (
    BOOK_COLUMNS,
    CANDLE_COLUMNS,
    TICKER_COLUMNS,
    TRADE_COLUMNS,
    book_rows,
    names,
)
from app.adapters.market.live import (
    BOOK_LEVELS,
    DEFAULT_INTERVAL,
    SNAPSHOT_CANDLES,
    SNAPSHOT_TRADES,
    watch,
)
from app.adapters.market.stream import MarketStream, StreamSpec
from app.adapters.market.values import whole_of
from app.adapters.protocol import AdapterError
from app.core.translation import say

__all__ = ["DEFAULT_INTERVAL", "BinanceLive", "MarketStream", "stream_urls"]

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


def _refusals() -> dict[int, AdapterError]:
    return {
        451: AdapterError(
            "config",
            say("Binance does not serve this address; choose another endpoint"),
        )
    }


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


def _now_ms() -> int:
    return int(time.time() * 1000)


class BinanceWatch:
    """One watch of a symbol's Market node at one interval."""

    def __init__(
        self,
        session: BinanceSession,
        market: Market,
        symbol: str,
        interval: str,
        node_id: str,
        size: int | None,
    ) -> None:
        self._session = session
        self._market = market
        self._symbol = symbol
        self._interval = interval
        self._node_id = node_id
        self._size = size
        # The newest trade said, so a trade the snapshot held is not said twice.
        self._newest = -1

    def streams(self) -> Sequence[StreamSpec]:
        return [
            StreamSpec(url)
            for url in stream_urls(
                self._session.hosts, self._market, self._symbol, self._interval
            )
        ]

    async def snapshot(self) -> list[LiveRows]:
        """The symbol as it stands, and the newest trade id it holds."""
        session, market, symbol = self._session, self._market, self._symbol
        node_id, size = self._node_id, self._size
        now = _now_ms()
        day = await session.get(market, "ticker/24hr", {"symbol": symbol}, node_id)
        # COIN-M answers a list even for one symbol.
        day = day[0] if isinstance(day, list) and day else day
        candles = await read_candles(
            session, market, symbol, self._interval, [], True, SNAPSHOT_CANDLES, node_id
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
        self._newest = max((int(one["a"]) for one in trades), default=-1)
        return [
            LiveRows(
                part="ticker",
                mode="replace",
                columns=names(TICKER_COLUMNS),
                rows=[ticker_row(day, size)] if isinstance(day, dict) else [],
            ),
            LiveRows(
                part="candles",
                mode="replace",
                columns=names(CANDLE_COLUMNS),
                rows=[one.row(now, size) for one in reversed(candles)],
                key=["open_time"],
            ),
            LiveRows(
                part="order_book",
                mode="replace",
                columns=names(BOOK_COLUMNS),
                rows=book_rows(book, BOOK_LEVELS) if isinstance(book, dict) else [],
            ),
            LiveRows(
                part="trades",
                mode="replace",
                columns=names(TRADE_COLUMNS),
                rows=[trade_row(one) for one in trades],
            ),
        ]

    def batch(self, item: dict[str, Any]) -> list[LiveRows]:
        rows = self._batch(item)
        return [] if rows is None else [rows]

    def _batch(self, item: dict[str, Any]) -> LiveRows | None:
        stream = item.get("stream")
        data = item.get("data")
        if not isinstance(stream, str) or not isinstance(data, dict):
            return None
        if stream.endswith("@aggTrade"):
            trade_id = whole_of(data.get("a"))
            # Trades the snapshot already held are not said twice.
            if trade_id is None or trade_id <= self._newest:
                return None
            self._newest = trade_id
            return LiveRows(
                part="trades",
                mode="append",
                columns=names(TRADE_COLUMNS),
                rows=[trade_row(data)],
            )
        if "@depth" in stream:
            # Spot names the sides `bids` and `asks`, futures `b` and `a`.
            book = {
                "bids": data.get("bids", data.get("b")) or [],
                "asks": data.get("asks", data.get("a")) or [],
            }
            return LiveRows(
                part="order_book",
                mode="replace",
                columns=names(BOOK_COLUMNS),
                rows=book_rows(book, BOOK_LEVELS),
            )
        if "@kline_" in stream:
            candle = _candle(data)
            if candle is None:
                return None
            return LiveRows(
                part="candles",
                mode="upsert",
                columns=names(CANDLE_COLUMNS),
                rows=[candle.row(_now_ms(), self._size)],
                key=["open_time"],
            )
        if stream.endswith("@ticker"):
            return LiveRows(
                part="ticker",
                mode="replace",
                columns=names(TICKER_COLUMNS),
                rows=[_ticker(data, self._size)],
            )
        return None


class BinanceLive:
    """The watch of a symbol's Market node."""

    def __init__(self, session: BinanceSession) -> None:
        self._session = session

    async def watch(
        self, market: Market, symbol: str, interval: str, node_id: str
    ) -> AsyncGenerator[LiveRows]:
        size = await contract_size_of(self._session, market, symbol, node_id)
        one = BinanceWatch(self._session, market, symbol, interval, node_id, size)
        async for rows in watch(self._session, one, _refusals(), "Binance"):
            yield rows
