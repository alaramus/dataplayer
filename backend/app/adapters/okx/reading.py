"""A symbol's candles and trades read on by a pipeline's link (D434).

OKX keeps no reader's place, so the bookmark is kept by this application,
through the store the adapter is handed, as Binance's and Bybit's are (D319,
D428). Its `""` is the next candle's open time, or for trades the id of the
next trade to read: OKX numbers a symbol's trades one after another and
keeps three months of them, so a block is a span of ids and what was lost is
counted exactly.
"""

import time
from typing import Any

from app.adapters.market.adapter import MarketReading
from app.adapters.market.catalog import place_in
from app.adapters.market.values import milliseconds
from app.adapters.okx.feeds import (
    OKX_CANDLE_COLUMNS,
    OkxPlace,
    candle_row,
    candles_between,
    close_ms,
    klines,
    newest_trade,
    oldest_trade_id,
    read_trades,
    shortest_ms,
    trade_before,
    trade_columns,
    trade_id,
    trade_row,
)
from app.adapters.okx.markets import BY_KEY, CANDLES_PER_REQUEST, INTERVALS, Market
from app.adapters.okx.session import CANDLES, OkxSession
from app.adapters.reading_on import (
    Bookmark,
    BookmarkAccess,
    ReadBlock,
    ReadStart,
    UnreadSpan,
)
from app.core.translation import say

DAY_MS = 86_400_000
HOUR_MS = 3_600_000
NEXT = ""
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


class OkxReading(MarketReading[Market]):
    def __init__(self, session: OkxSession, bookmarks: BookmarkAccess | None) -> None:
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

    async def _place(self, node_id: str) -> OkxPlace:
        place = place_in(BY_KEY, node_id)
        if place.feed not in _READ_ON or place.symbol is None:
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
        self,
        place: OkxPlace,
        node_id: str,
        kept: Bookmark | None,
        start: ReadStart,
    ) -> UnreadSpan:
        """From the bookmark to the newest trade.

        A bookmark older than OKX's three months finds its trade gone: the
        reader moves to the oldest OKX still has, and what lay between is
        counted lost, exactly, as the ids run one after another.
        """
        assert place.symbol is not None
        market, symbol = place.market, place.symbol
        newest = await newest_trade(self._session, market, symbol, node_id)
        line = (trade_id(newest) or 0) + 1 if newest is not None else 1
        lost = 0
        if kept is None or NEXT not in kept.positions:
            begin = line
            if start == "earliest":
                before = await trade_before(
                    self._session, market, symbol, _now_ms() - HOUR_MS, node_id
                )
                begin = 1 if before is None else before + 1
        else:
            begin = kept.positions[NEXT]
            if begin < line and not await read_trades(
                self._session, market, symbol, begin, begin, node_id
            ):
                oldest = await oldest_trade_id(self._session, market, symbol, node_id)
                if oldest is not None and oldest > begin:
                    lost = min(oldest, line) - begin
                    begin = oldest
        begin = min(begin, line)
        return UnreadSpan(
            start=_at({NEXT: begin}),
            line=_at({NEXT: line}),
            count=line - begin,
            lost=lost,
            fresh=kept is None,
        )

    async def _newest_candle(
        self, market: Market, symbol: str, interval: str, node_id: str
    ) -> list[Any] | None:
        params = {"instId": symbol, "bar": INTERVALS[interval], "limit": "1"}
        found = klines(await self._session.get(market, CANDLES, params, node_id))
        return found[0] if found else None

    async def _unread_candles(
        self,
        place: OkxPlace,
        node_id: str,
        kept: Bookmark | None,
        start: ReadStart,
    ) -> UnreadSpan:
        assert place.symbol is not None and place.interval is not None
        market, symbol, interval = place.market, place.symbol, place.interval
        now = _now_ms()
        newest = await self._newest_candle(market, symbol, interval, node_id)
        line = 0
        if newest is not None:
            open_ms = int(newest[0])
            # The candle still open is never read: its prices are not final.
            confirmed = str(newest[8]) == "1" if len(newest) > 8 else False
            line = close_ms(interval, open_ms) + 1 if confirmed else open_ms
        if kept is None or NEXT not in kept.positions:
            begin = line
            if start == "earliest":
                first = await candles_between(
                    self._session,
                    market,
                    symbol,
                    interval,
                    now - DAY_MS,
                    1,
                    None,
                    node_id,
                )
                if first:
                    begin = min(int(first[0][0]), line)
        else:
            begin = min(kept.positions[NEXT], line)
        return UnreadSpan(
            start=_at({NEXT: begin}),
            line=_at({NEXT: line}),
            count=-(-(line - begin) // shortest_ms(interval)),
            fresh=kept is None,
        )

    # --- reading a block -----------------------------------------------------

    async def read_on(
        self, node_id: str, columns: list[str], at: Bookmark, line: Bookmark, limit: int
    ) -> ReadBlock:
        place = await self._place(node_id)
        shape = (
            trade_columns(place.market)
            if place.feed == "trades"
            else OKX_CANDLE_COLUMNS
        )
        picked = _picked(columns, [column.name for column in shape])
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
        place: OkxPlace,
        node_id: str,
        picked: list[int],
        at: Bookmark,
        begin: int,
        end: int,
        limit: int,
    ) -> ReadBlock:
        """The ids from the bookmark, at most `limit` of them, before the line."""
        assert place.symbol is not None
        market, symbol = place.market, place.symbol
        value = (await self._session.instrument(market, symbol, node_id)).contract_value
        last = min(end - 1, begin + max(limit, 1) - 1)
        found = await read_trades(self._session, market, symbol, begin, last, node_id)
        rows = [
            [full[index] for index in picked]
            for full in (trade_row(market, one, value) for one in found)
        ]
        after = dict(at.positions)
        after[NEXT] = last + 1
        return ReadBlock(rows=rows, after=_at(after), done=after[NEXT] >= end)

    async def _candles_block(
        self,
        place: OkxPlace,
        node_id: str,
        picked: list[int],
        at: Bookmark,
        begin: int,
        end: int,
        limit: int,
    ) -> ReadBlock:
        assert place.symbol is not None and place.interval is not None
        market, interval = place.market, place.interval
        count = max(1, min(limit, CANDLES_PER_REQUEST))
        found = [
            raw
            for raw in await candles_between(
                self._session,
                market,
                place.symbol,
                interval,
                begin,
                count,
                end - 1,
                node_id,
            )
            if begin <= (milliseconds(raw[0]) or -1) < end
        ]
        rows = [
            [full[index] for index in picked]
            for full in (candle_row(market, interval, raw) for raw in found)
        ]
        after = dict(at.positions)
        if len(found) == count:
            after[NEXT] = close_ms(interval, int(found[-1][0])) + 1
        else:
            # The span asked held fewer: nothing more opens inside it.
            after[NEXT] = min(end, begin + count * shortest_ms(interval))
        return ReadBlock(rows=rows, after=_at(after), done=after[NEXT] >= end)

    def row_key(self, node_id: str) -> list[str]:
        """A trade is named by its id, a candle of a series by its open time."""
        feed = place_in(BY_KEY, node_id).feed
        return ["id"] if feed == "trades" else ["open_time"]

    async def mark_read(self, node_id: str, reader: str, at: Bookmark) -> None:
        place_in(BY_KEY, node_id)
        await self._store().write(node_id, reader, at)
