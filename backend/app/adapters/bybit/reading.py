"""A symbol's candles and trades read on by a pipeline's link (D428), and
with a key its own trades (D431).

Bybit keeps no reader's place, so the bookmark is kept by this application,
through the store the adapter is handed, as Binance's is (D319). Its `""` is
the next candle's open time, or for trades the time of the next trade to
read: Bybit gives its newest trades with nothing to page by — no id, no
time — so a trade is found by its time among them. A block that stops inside
a millisecond reads that millisecond again; the made table is keyed by the
trade's id, so a trade read twice arrives once.
"""

import time
from typing import Any

from app.adapters.bybit.account import MY_TRADE_COLUMNS, my_trade_row, own_trades
from app.adapters.bybit.feeds import (
    BYBIT_CANDLE_COLUMNS,
    BYBIT_TRADE_COLUMNS,
    BybitPlace,
    candle_row,
    close_ms,
    recent_trades,
    trade_row,
    trade_time,
)
from app.adapters.bybit.markets import BY_KEY, CANDLES_PER_REQUEST, INTERVALS, Market
from app.adapters.bybit.session import BybitSession
from app.adapters.market.adapter import MarketReading
from app.adapters.market.catalog import place_in
from app.adapters.market.shape import INTERVAL_MS
from app.adapters.market.values import milliseconds
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
# A month's candle is at least this long; a count of months is an upper bound.
_SHORTEST_MS = {"1M": 28 * DAY_MS}
_READ_ON = {"trades", "candles", "my_trades"}
# Bybit answers own trades seven days at a time, and those days by default.
WEEK_MS = 7 * DAY_MS


def _now_ms() -> int:
    return int(time.time() * 1000)


def _at(positions: dict[str, int]) -> Bookmark:
    return Bookmark(positions=positions)


def _picked(columns: list[str], names: list[str]) -> list[int]:
    unknown = [one for one in columns if one not in names]
    if unknown:
        raise ValueError(say("Unknown column: {column}", column=unknown[0]))
    return [names.index(one) for one in columns]


class BybitReading(MarketReading[Market]):
    def __init__(self, session: BybitSession, bookmarks: BookmarkAccess | None) -> None:
        self._session = session
        self._bookmarks = bookmarks

    def reads_on(self, node_id: str) -> bool:
        try:
            place = place_in(BY_KEY, node_id)
        except ValueError:
            return False
        return place.feed in _READ_ON

    def _store(self) -> BookmarkAccess:
        if self._bookmarks is None:
            raise ValueError(say("This connection keeps no reader's place here"))
        return self._bookmarks

    async def _place(self, node_id: str) -> BybitPlace:
        place = place_in(BY_KEY, node_id)
        if place.feed not in _READ_ON or place.symbol is None:
            raise ValueError(say("Only trades and candles are read on"))
        if place.feed == "my_trades" and not self._session.keyed:
            raise ValueError(say("This connection has no API key"))
        await self._session.symbol(place.market, place.symbol, node_id)
        return place

    # --- what is unread ------------------------------------------------------

    async def unread(self, node_id: str, reader: str, start: ReadStart) -> UnreadSpan:
        place = await self._place(node_id)
        kept = await self._store().read(node_id, reader)
        if place.feed == "trades":
            return await self._unread_trades(place, node_id, kept, start)
        if place.feed == "my_trades":
            return await self._unread_mine(place, node_id, kept, start)
        return await self._unread_candles(place, node_id, kept, start)

    async def _unread_mine(
        self,
        place: BybitPlace,
        node_id: str,
        kept: Bookmark | None,
        start: ReadStart,
    ) -> UnreadSpan:
        """The key's own trades of a symbol, by time (D431).

        The newest page of the last seven days says where the line is; how
        many lie between is counted on that page only, so it is a floor.
        """
        assert place.symbol is not None
        newest = await own_trades(
            self._session, place.market, place.symbol, node_id, most=1
        )
        times = [milliseconds(one.get("execTime")) or 0 for one in newest]
        now = _now_ms()
        if kept is None or NEXT not in kept.positions:
            begin = now - WEEK_MS if start == "earliest" else None
        else:
            begin = kept.positions[NEXT]
        line = times[-1] + 1 if times else (begin if begin is not None else now)
        begin = line if begin is None else min(begin, line)
        between = sum(1 for one in times if begin <= one < line)
        return UnreadSpan(
            start=_at({NEXT: begin}),
            line=_at({NEXT: line}),
            count=max(between, 1 if line > begin else 0),
            fresh=kept is None,
        )

    async def _trades(self, place: BybitPlace, node_id: str) -> list[dict[str, Any]]:
        assert place.symbol is not None
        return await recent_trades(self._session, place.market, place.symbol, node_id)

    async def _unread_trades(
        self,
        place: BybitPlace,
        node_id: str,
        kept: Bookmark | None,
        start: ReadStart,
    ) -> UnreadSpan:
        """From the bookmark to the newest trade's time.

        Bybit answers its newest trades only. When they fill an answer and
        the oldest of them is after the bookmark, what lay between is gone;
        how many is not known, so one is counted lost.
        """
        trades = await self._trades(place, node_id)
        times = [trade_time(one) or 0 for one in trades]
        line = times[-1] + 1 if times else 0
        oldest = times[0] if times else line
        lost = 0
        if kept is None or NEXT not in kept.positions:
            begin = oldest if start == "earliest" else line
        else:
            begin = kept.positions[NEXT]
            full = len(trades) >= place.market.trades_per_request
            if full and oldest > begin:
                lost = 1
                begin = oldest
        begin = min(begin, line)
        return UnreadSpan(
            start=_at({NEXT: begin}),
            line=_at({NEXT: line}),
            count=sum(1 for one in times if begin <= one < line),
            lost=lost,
            fresh=kept is None,
        )

    async def _newest_kline(
        self, market: Market, symbol: str, interval: str, node_id: str, **more: str
    ) -> list[Any] | None:
        params = {"symbol": symbol, "interval": INTERVALS[interval], "limit": "1"}
        answer = await self._session.ask(market, "kline", {**params, **more}, node_id)
        rows = answer.get("list") if isinstance(answer, dict) else None
        found = [raw for raw in rows or [] if raw and milliseconds(raw[0]) is not None]
        return found[0] if found else None

    async def _unread_candles(
        self,
        place: BybitPlace,
        node_id: str,
        kept: Bookmark | None,
        start: ReadStart,
    ) -> UnreadSpan:
        assert place.symbol is not None and place.interval is not None
        market, symbol, interval = place.market, place.symbol, place.interval
        now = _now_ms()
        newest = await self._newest_kline(market, symbol, interval, node_id)
        line = 0
        if newest is not None:
            open_ms = int(newest[0])
            closing = close_ms(interval, open_ms)
            # The candle still open is never read: its prices are not final.
            line = closing + 1 if closing < now else open_ms
        if kept is None or NEXT not in kept.positions:
            begin = line
            if start == "earliest":
                # From a start Bybit answers the oldest candle after it.
                first = await self._newest_kline(
                    market, symbol, interval, node_id, start=str(now - DAY_MS)
                )
                if first is not None:
                    begin = min(int(first[0]), line)
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
        shape = {
            "trades": BYBIT_TRADE_COLUMNS,
            "my_trades": MY_TRADE_COLUMNS,
        }.get(place.feed or "", BYBIT_CANDLE_COLUMNS)
        picked = _picked(columns, [column.name for column in shape])
        begin = at.positions.get(NEXT, 0)
        end = line.positions.get(NEXT, 0)
        if begin >= end:
            return ReadBlock(rows=[], after=at, done=True)
        if place.feed == "trades":
            return await self._trades_block(
                place, node_id, picked, at, begin, end, limit
            )
        if place.feed == "my_trades":
            return await self._mine_block(place, node_id, picked, at, begin, end, limit)
        return await self._candles_block(place, node_id, picked, at, begin, end, limit)

    async def _trades_block(
        self,
        place: BybitPlace,
        node_id: str,
        picked: list[int],
        at: Bookmark,
        begin: int,
        end: int,
        limit: int,
    ) -> ReadBlock:
        within = [
            one
            for one in await self._trades(place, node_id)
            if begin <= (trade_time(one) or 0) < end
        ]
        block, rest = within[:limit], within[limit:]
        rows = [[full[index] for index in picked] for full in map(trade_row, block)]
        after = dict(at.positions)
        if not block:
            # Nothing left between: gone from Bybit's newest, or none made.
            after[NEXT] = end
        else:
            last = trade_time(block[-1]) or begin
            # A millisecond split by the limit is read again from its start.
            split = bool(rest) and trade_time(rest[0]) == last and last > begin
            after[NEXT] = last if split else last + 1
        return ReadBlock(rows=rows, after=_at(after), done=after[NEXT] >= end)

    async def _mine_block(
        self,
        place: BybitPlace,
        node_id: str,
        picked: list[int],
        at: Bookmark,
        begin: int,
        end: int,
        limit: int,
    ) -> ReadBlock:
        """Own trades of one window of at most seven days, the most Bybit
        answers; an empty window moves the bookmark past it."""
        assert place.symbol is not None
        last_ms = min(end - 1, begin + WEEK_MS - 1)
        found = await own_trades(
            self._session,
            place.market,
            place.symbol,
            node_id,
            {"startTime": str(begin), "endTime": str(last_ms)},
        )
        within = [
            one
            for one in found
            if begin <= (milliseconds(one.get("execTime")) or 0) <= last_ms
        ]
        block, rest = within[:limit], within[limit:]
        rows = [
            [full[index] for index in picked]
            for full in (my_trade_row(place.market, one) for one in block)
        ]
        after = dict(at.positions)
        if not block:
            after[NEXT] = last_ms + 1
        else:
            last = milliseconds(block[-1].get("execTime")) or begin
            split = (
                bool(rest)
                and milliseconds(rest[0].get("execTime")) == last
                and last > begin
            )
            after[NEXT] = last if split else last + 1
        return ReadBlock(rows=rows, after=_at(after), done=after[NEXT] >= end)

    async def _candles_block(
        self,
        place: BybitPlace,
        node_id: str,
        picked: list[int],
        at: Bookmark,
        begin: int,
        end: int,
        limit: int,
    ) -> ReadBlock:
        assert place.symbol is not None and place.interval is not None
        market, interval = place.market, place.interval
        params = {
            "symbol": place.symbol,
            "interval": INTERVALS[interval],
            "start": str(begin),
            "end": str(end - 1),
            "limit": str(min(limit, CANDLES_PER_REQUEST)),
        }
        answer = await self._session.ask(market, "kline", params, node_id)
        klines = [
            raw
            for raw in reversed(answer.get("list") or [])
            if raw and begin <= (milliseconds(raw[0]) or -1) < end
        ]
        now = _now_ms()
        rows = [
            [full[index] for index in picked]
            for full in (candle_row(market, interval, raw, now) for raw in klines)
        ]
        after = dict(at.positions)
        after[NEXT] = close_ms(interval, int(klines[-1][0])) + 1 if klines else end
        return ReadBlock(rows=rows, after=_at(after), done=after[NEXT] >= end)

    def row_key(self, node_id: str) -> list[str]:
        """A trade is named by its id, a candle of a series by its open time."""
        feed = place_in(BY_KEY, node_id).feed
        return ["id"] if feed in {"trades", "my_trades"} else ["open_time"]

    async def mark_read(self, node_id: str, reader: str, at: Bookmark) -> None:
        place_in(BY_KEY, node_id)
        await self._store().write(node_id, reader, at)
