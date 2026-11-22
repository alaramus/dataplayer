"""A product's candles and trades read on by a pipeline's link (D440).

Coinbase keeps no reader's place, so the bookmark is kept by this
application, as every exchange's is (D319). Its `""` is the next candle's
open time, or for trades the id of the next trade to read: Coinbase numbers
a product's trades one after another and keeps them all, so nothing is lost
however long a link waits.
"""

import time

from app.adapters.coinbase.feeds import (
    COINBASE_CANDLE_COLUMNS,
    COINBASE_TRADE_COLUMNS,
    CoinbasePlace,
    candle_row,
    candles_between,
    newest_trade,
    read_trades,
    trade_id,
    trade_row,
)
from app.adapters.coinbase.markets import BY_KEY, CANDLES_PER_REQUEST, INTERVALS, Market
from app.adapters.coinbase.session import CoinbaseSession
from app.adapters.market.adapter import MarketReading
from app.adapters.market.catalog import place_in
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
# A fresh reader's `earliest` trades: the newest this many.
EARLIEST_TRADES = 1000
_READ_ON = {"trades", "candles"}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _at(positions: dict[str, int]) -> Bookmark:
    return Bookmark(positions=positions)


def _picked(columns: list[str], names: list[str]) -> list[int]:
    unknown = [one for one in columns if one not in names]
    if unknown:
        raise ValueError(say("Unknown column: {column}", column=unknown[0]))
    return [names.index(one) for one in columns]


class CoinbaseReading(MarketReading[Market]):
    def __init__(
        self, session: CoinbaseSession, bookmarks: BookmarkAccess | None
    ) -> None:
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

    async def _place(self, node_id: str) -> CoinbasePlace:
        place = place_in(BY_KEY, node_id)
        if place.feed not in _READ_ON or place.symbol is None:
            raise ValueError(say("Only trades and candles are read on"))
        await self._session.symbol(place.market, place.symbol, node_id)
        return place

    async def unread(self, node_id: str, reader: str, start: ReadStart) -> UnreadSpan:
        place = await self._place(node_id)
        kept = await self._store().read(node_id, reader)
        if place.feed == "trades":
            return await self._unread_trades(place, node_id, kept, start)
        return await self._unread_candles(place, node_id, kept, start)

    async def _unread_trades(
        self,
        place: CoinbasePlace,
        node_id: str,
        kept: Bookmark | None,
        start: ReadStart,
    ) -> UnreadSpan:
        assert place.symbol is not None
        newest = await newest_trade(self._session, place.market, place.symbol, node_id)
        line = (trade_id(newest) or 0) + 1 if newest is not None else 1
        if kept is None or NEXT not in kept.positions:
            begin = max(1, line - EARLIEST_TRADES) if start == "earliest" else line
        else:
            begin = kept.positions[NEXT]
        begin = min(begin, line)
        return UnreadSpan(
            start=_at({NEXT: begin}),
            line=_at({NEXT: line}),
            count=line - begin,
            fresh=kept is None,
        )

    async def _unread_candles(
        self,
        place: CoinbasePlace,
        node_id: str,
        kept: Bookmark | None,
        start: ReadStart,
    ) -> UnreadSpan:
        """To the open of the candle still open: the time, not an answer, says
        where it is, since Coinbase publishes no candle for a quiet interval."""
        assert place.interval is not None
        step_ms = INTERVALS[place.interval] * 1000
        now = _now_ms()
        line = now - now % step_ms
        if kept is None or NEXT not in kept.positions:
            begin = line - DAY_MS if start == "earliest" else line
        else:
            begin = kept.positions[NEXT]
        begin = min(begin, line)
        return UnreadSpan(
            start=_at({NEXT: begin}),
            line=_at({NEXT: line}),
            count=-(-(line - begin) // step_ms),
            fresh=kept is None,
        )

    async def read_on(
        self, node_id: str, columns: list[str], at: Bookmark, line: Bookmark, limit: int
    ) -> ReadBlock:
        place = await self._place(node_id)
        assert place.symbol is not None
        shape = (
            COINBASE_TRADE_COLUMNS
            if place.feed == "trades"
            else COINBASE_CANDLE_COLUMNS
        )
        picked = _picked(columns, [column.name for column in shape])
        begin = at.positions.get(NEXT, 0)
        end = line.positions.get(NEXT, 0)
        if begin >= end:
            return ReadBlock(rows=[], after=at, done=True)
        after = dict(at.positions)
        if place.feed == "trades":
            last = min(end - 1, begin + max(limit, 1) - 1)
            found = await read_trades(
                self._session, place.market, place.symbol, begin, last, node_id
            )
            rows = [[trade_row(one)[index] for index in picked] for one in found]
            after[NEXT] = last + 1
            return ReadBlock(rows=rows, after=_at(after), done=after[NEXT] >= end)
        assert place.interval is not None
        step = INTERVALS[place.interval]
        count = max(1, min(limit, CANDLES_PER_REQUEST))
        first_s = begin // 1000
        last_s = min((end - 1) // 1000, first_s + (count - 1) * step)
        candles = await candles_between(
            self._session,
            place.market,
            place.symbol,
            place.interval,
            first_s,
            last_s,
            node_id,
        )
        now = _now_ms()
        rows = [
            [candle_row(place.interval, raw, now)[index] for index in picked]
            for raw in candles
        ]
        after[NEXT] = (last_s + step) * 1000
        return ReadBlock(rows=rows, after=_at(after), done=after[NEXT] >= end)

    def row_key(self, node_id: str) -> list[str]:
        feed = place_in(BY_KEY, node_id).feed
        return ["id"] if feed == "trades" else ["open_time"]

    async def mark_read(self, node_id: str, reader: str, at: Bookmark) -> None:
        place_in(BY_KEY, node_id)
        await self._store().write(node_id, reader, at)
