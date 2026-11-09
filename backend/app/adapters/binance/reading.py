"""A symbol's trades and candles read on by a pipeline's link (D319).

Binance keeps no reader's position, so the bookmark is kept by this
application, through the store the adapter is handed. A bookmark has the
next position under `""` — the next aggregated trade id, or the next candle's
open time — and, for trades, the time of the last one read under `"time"`,
so a reader that fell behind what Binance still answers is noticed without
asking every time.
"""

import time

from app.adapters.binance.catalog import Place, place_of
from app.adapters.binance.feeds import (
    CANDLE_COLUMNS,
    HOUR_MS,
    TRADE_COLUMNS,
    Candle,
    contract_size_of,
    newest_trade_id,
    oldest_trade_id,
    read_trades,
    trade_row,
)
from app.adapters.binance.markets import INTERVAL_MS, Market
from app.adapters.binance.session import BinanceSession
from app.adapters.reading_on import (
    Bookmark,
    BookmarkAccess,
    ReadBlock,
    ReadStart,
    UnreadSpan,
)
from app.core.translation import say

DAY_MS = 86_400_000
NEXT = ""
LAST_TIME = "time"
# A month's candle is at least this long; a count of months is an upper bound.
_SHORTEST_MS = {"1M": 28 * DAY_MS}
# Spot keeps about two years of trades; a reader this far behind is checked.
_SPOT_KEPT_MS = 700 * DAY_MS


def _now_ms() -> int:
    return int(time.time() * 1000)


def _at(positions: dict[str, int]) -> Bookmark:
    return Bookmark(positions=positions)


class BinanceReading:
    def __init__(
        self, session: BinanceSession, bookmarks: BookmarkAccess | None
    ) -> None:
        self._session = session
        self._bookmarks = bookmarks

    def reads_on(self, node_id: str) -> bool:
        try:
            place = place_of(node_id)
        except ValueError:
            return False
        return place.feed in {"trades", "candles"}

    def _store(self) -> BookmarkAccess:
        if self._bookmarks is None:
            raise ValueError(say("This connection keeps no reader's place here"))
        return self._bookmarks

    async def _place(self, node_id: str) -> Place:
        place = place_of(node_id)
        if place.feed not in {"trades", "candles"} or place.symbol is None:
            raise ValueError(say("Only trades and candles are read on"))
        await self._session.symbol(place.market, place.symbol, node_id)
        return place

    # --- what is unread ------------------------------------------------------

    async def unread(self, node_id: str, reader: str, start: ReadStart) -> UnreadSpan:
        place = await self._place(node_id)
        kept = await self._store().read(node_id, reader)
        if place.feed == "trades":
            return await self._unread_trades(place, node_id, kept, start)
        return await self._unread_candles(place, node_id, kept, start)

    async def _unread_trades(
        self, place: Place, node_id: str, kept: Bookmark | None, start: ReadStart
    ) -> UnreadSpan:
        assert place.symbol is not None
        market, symbol = place.market, place.symbol
        newest = await newest_trade_id(self._session, market, symbol, node_id)
        line = 0 if newest is None else newest + 1
        lost = 0
        if kept is None or NEXT not in kept.positions:
            begin = line
            if start == "earliest" and newest is not None:
                begin = await self._trade_an_hour_ago(market, symbol, node_id, line)
        else:
            begin = kept.positions[NEXT]
            if self._may_be_forgotten(market, kept):
                oldest = await oldest_trade_id(self._session, market, symbol, node_id)
                if oldest is not None and begin < oldest:
                    lost = oldest - begin
                    begin = oldest
        begin = min(begin, line)
        return UnreadSpan(
            start=_at({NEXT: begin}),
            line=_at({NEXT: line}),
            count=line - begin,
            lost=lost,
            fresh=kept is None,
        )

    def _may_be_forgotten(self, market: Market, kept: Bookmark) -> bool:
        """Whether the last trade read is older than Binance may still answer."""
        last = kept.positions.get(LAST_TIME)
        if last is None:
            return True
        kept_ms = market.trades_window_ms or _SPOT_KEPT_MS
        return _now_ms() - last > kept_ms - HOUR_MS

    async def _trade_an_hour_ago(
        self, market: Market, symbol: str, node_id: str, line: int
    ) -> int:
        """The first trade of the last hour.

        An hour, not the day candles start from: a busy symbol makes close to
        a million trades a day, a thousand a request, which would spend most
        of a minute's rate limit and minutes of time on the first run.
        """
        since = _now_ms() - HOUR_MS
        params = {
            "symbol": symbol,
            "startTime": str(since),
            "endTime": str(since + HOUR_MS - 1),
            "limit": "1",
        }
        answer = await self._session.get(market, "aggTrades", params, node_id)
        found = [one for one in answer if isinstance(one, dict) and "a" in one]
        # A symbol quiet that whole hour starts from now.
        return int(found[0]["a"]) if found else line

    async def _unread_candles(
        self, place: Place, node_id: str, kept: Bookmark | None, start: ReadStart
    ) -> UnreadSpan:
        assert place.symbol is not None and place.interval is not None
        market, symbol, interval = place.market, place.symbol, place.interval
        now = _now_ms()
        newest = await self._session.get(
            market,
            "klines",
            {"symbol": symbol, "interval": interval, "limit": "1"},
            node_id,
        )
        line = 0
        if newest:
            open_ms, close_ms = int(newest[-1][0]), int(newest[-1][6])
            # The candle still open is never read: its prices are not final.
            line = close_ms + 1 if close_ms < now else open_ms
        if kept is None or NEXT not in kept.positions:
            begin = line
            if start == "earliest":
                first = await self._session.get(
                    market,
                    "klines",
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "startTime": str(now - DAY_MS),
                        "limit": "1",
                    },
                    node_id,
                )
                if first:
                    begin = min(int(first[0][0]), line)
        else:
            begin = min(kept.positions[NEXT], line)
        shortest = _SHORTEST_MS.get(interval, INTERVAL_MS[interval])
        return UnreadSpan(
            start=_at({NEXT: begin}),
            line=_at({NEXT: line}),
            count=-(-(line - begin) // shortest),
            fresh=kept is None,
        )

    # --- reading a block -----------------------------------------------------

    async def read_on(
        self, node_id: str, columns: list[str], at: Bookmark, line: Bookmark, limit: int
    ) -> ReadBlock:
        place = await self._place(node_id)
        shape = TRADE_COLUMNS if place.feed == "trades" else CANDLE_COLUMNS
        names = [column.name for column in shape]
        unknown = [one for one in columns if one not in names]
        if unknown:
            raise ValueError(say("Unknown column: {column}", column=unknown[0]))
        picked = [names.index(one) for one in columns]
        begin = at.positions.get(NEXT, 0)
        end = line.positions.get(NEXT, 0)
        if begin >= end:
            return ReadBlock(rows=[], after=at, done=True)
        if place.feed == "trades":
            return await self._trades_block(
                place, node_id, picked, at, begin, end, limit
            )
        return await self._candles_block(place, node_id, picked, at, begin, end, limit)

    async def _trades_block(
        self,
        place: Place,
        node_id: str,
        picked: list[int],
        at: Bookmark,
        begin: int,
        end: int,
        limit: int,
    ) -> ReadBlock:
        assert place.symbol is not None
        last = min(end - 1, begin + limit - 1)
        trades = await read_trades(
            self._session, place.market, place.symbol, begin, last, node_id
        )
        rows = [[full[index] for index in picked] for full in map(trade_row, trades)]
        after = dict(at.positions)
        after[NEXT] = int(trades[-1]["a"]) + 1 if trades else last + 1
        if trades and isinstance(trades[-1].get("T"), int):
            after[LAST_TIME] = int(trades[-1]["T"])
        return ReadBlock(rows=rows, after=_at(after), done=after[NEXT] >= end)

    async def _candles_block(
        self,
        place: Place,
        node_id: str,
        picked: list[int],
        at: Bookmark,
        begin: int,
        end: int,
        limit: int,
    ) -> ReadBlock:
        assert place.symbol is not None and place.interval is not None
        market = place.market
        params = {
            "symbol": place.symbol,
            "interval": place.interval,
            "startTime": str(begin),
            "endTime": str(end - 1),
            "limit": str(min(limit, market.candles_per_request)),
        }
        answer = await self._session.get(market, "klines", params, node_id)
        candles = [Candle(int(raw[0]), raw) for raw in answer if raw]
        candles = [one for one in candles if begin <= one.open_ms < end]
        now = _now_ms()
        size = await contract_size_of(self._session, market, place.symbol, node_id)
        rows = [
            [full[index] for index in picked]
            for full in (c.row(now, size) for c in candles)
        ]
        after = dict(at.positions)
        after[NEXT] = int(candles[-1].raw[6]) + 1 if candles else end
        return ReadBlock(rows=rows, after=_at(after), done=after[NEXT] >= end)

    def row_key(self, node_id: str) -> list[str]:
        """A trade is named by its id, a candle of a series by its open time."""
        return ["id"] if place_of(node_id).feed == "trades" else ["open_time"]

    async def mark_read(self, node_id: str, reader: str, at: Bookmark) -> None:
        place_of(node_id)
        await self._store().write(node_id, reader, at)
