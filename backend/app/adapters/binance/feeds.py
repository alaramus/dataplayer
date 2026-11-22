"""A market's feeds as rows (D318).

Every decimal stays the text Binance wrote, checked to be a number and never
passed through a float; times arrive in milliseconds and leave as moments in
UTC. The lists and the book are read the shared way (D425); candles and
trades are read from Binance a request at a time, and only what Binance can
bound — a time, an id — narrows them.
"""

import time
from dataclasses import dataclass
from typing import Any

from app.adapters.binance.markets import Market
from app.adapters.binance.session import BinanceSession
from app.adapters.fetch import FetchRequest, FetchResult, Filter, Sort
from app.adapters.listed import checked_filters, checked_sorts, milliseconds_of
from app.adapters.market.catalog import Place
from app.adapters.market.columns import (
    CANDLE_COLUMNS,
    DEPTH_CEILING,
    TRADE_COLUMNS,
    Bounds,
    bounds_of,
    descending,
    paged,
    too_deep,
)
from app.adapters.market.values import (
    boolean_of,
    decimal_text,
    in_quote,
    moment,
    whole_number,
    whole_of,
)
from app.core.translation import say

HOUR_MS = 3_600_000

type BinancePlace = Place[Market]

_TICKER_FIELDS = (
    "lastPrice",
    "priceChange",
    "priceChangePercent",
    "weightedAvgPrice",
    "openPrice",
    "highPrice",
    "lowPrice",
)


def ticker_row(
    item: dict[str, Any], contract_size: int | None = None
) -> list[str | None]:
    """A symbol's last day. On COIN-M Binance counts `volume` in contracts and
    names the base asset's `baseVolume`; the columns keep one meaning across
    markets, so the base goes under volume and the contracts' worth under
    quote volume."""
    if contract_size is None:
        volumes = [
            decimal_text(item.get("volume")),
            decimal_text(item.get("quoteVolume")),
        ]
    else:
        volumes = [
            decimal_text(item.get("baseVolume")),
            in_quote(item.get("volume"), contract_size),
        ]
    return [
        str(item.get("symbol")),
        *(decimal_text(item.get(name)) for name in _TICKER_FIELDS),
        *volumes,
        None if whole_of(item.get("count")) is None else str(item.get("count")),
        moment(whole_of(item.get("openTime"))),
        moment(whole_of(item.get("closeTime"))),
    ]


# --- candles --------------------------------------------------------------------


@dataclass(frozen=True)
class Candle:
    open_ms: int
    raw: list[Any]

    def row(self, now_ms: int, contract_size: int | None = None) -> list[str | None]:
        """One candle. On COIN-M Binance's volume and taker volume are counts of
        contracts and the base asset's are beside them (D321): the base goes
        under volume and the contracts' worth under quote volume, as on the
        other markets."""
        raw = list(self.raw) + [None] * max(0, 11 - len(self.raw))
        close_ms = whole_of(raw[6])
        if contract_size is None:
            volume, quote, taker, taker_quote = (
                decimal_text(raw[5]),
                decimal_text(raw[7]),
                decimal_text(raw[9]),
                decimal_text(raw[10]),
            )
        else:
            volume, quote, taker, taker_quote = (
                decimal_text(raw[7]),
                in_quote(raw[5], contract_size),
                decimal_text(raw[10]),
                in_quote(raw[9], contract_size),
            )
        return [
            moment(self.open_ms),
            moment(close_ms),
            *(decimal_text(raw[index]) for index in range(1, 5)),
            volume,
            quote,
            str(raw[8]) if whole_of(raw[8]) is not None else None,
            taker,
            taker_quote,
            "true" if close_ms is not None and close_ms < now_ms else "false",
        ]


async def contract_size_of(
    session: BinanceSession, market: Market, symbol: str, node_id: str
) -> int | None:
    """What one of the symbol's contracts is worth, where volumes are counted in them."""
    if not market.in_contracts:
        return None
    return (await session.symbol(market, symbol, node_id)).contract_size


async def read_candles(
    session: BinanceSession,
    market: Market,
    symbol: str,
    interval: str,
    filters: list[Filter],
    newest: bool,
    need: int,
    node_id: str,
) -> list[Candle]:
    """Up to `need` candles in the asked order, a request at a time."""
    bounds = bounds_of(
        filters, "open_time", lambda text: milliseconds_of("open_time", text)
    )
    found: list[Candle] = []
    if newest:
        cursor = bounds.high
        while len(found) < need:
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": str(min(market.candles_per_request, need - len(found))),
            }
            if cursor is not None:
                params["endTime"] = str(cursor)
            answer = await session.get(market, "klines", params, node_id)
            batch = [
                Candle(raw[0], raw)
                for raw in answer
                if raw and whole_of(raw[0]) is not None
            ]
            if not batch:
                break
            for candle in reversed(batch):
                if bounds.low is not None and candle.open_ms < bounds.low:
                    return found
                found.append(candle)
            if len(batch) < int(params["limit"]):
                break
            cursor = batch[0].open_ms - 1
        return found
    cursor = bounds.low if bounds.low is not None else 0
    while len(found) < need:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": str(cursor),
            "limit": str(min(market.candles_per_request, need - len(found))),
        }
        if bounds.high is not None:
            params["endTime"] = str(bounds.high)
        answer = await session.get(market, "klines", params, node_id)
        batch = [
            Candle(raw[0], raw)
            for raw in answer
            if raw and whole_of(raw[0]) is not None
        ]
        found.extend(batch)
        if len(batch) < int(params["limit"]):
            break
        cursor = batch[-1].open_ms + 1
    return found


def checked_candles(filters: list[Filter], sort: list[Sort]) -> None:
    checked_filters(filters, CANDLE_COLUMNS)
    checked_sorts(sort, CANDLE_COLUMNS)


async def candles_page(
    session: BinanceSession, place: BinancePlace, request: FetchRequest, now_ms: int
) -> FetchResult:
    checked_candles(request.filters, request.sort)
    if too_deep(request):
        raise ValueError(
            say(
                "A page reaches at most {n} candles deep; narrow it by open time",
                n=DEPTH_CEILING,
            )
        )
    assert place.symbol is not None and place.interval is not None
    need = request.offset + request.limit + 1
    candles = await read_candles(
        session,
        place.market,
        place.symbol,
        place.interval,
        request.filters,
        descending(request.sort, "open_time"),
        need,
        request.node_id,
    )
    size = await contract_size_of(session, place.market, place.symbol, request.node_id)
    rows = [candle.row(now_ms, size) for candle in candles]
    return paged(CANDLE_COLUMNS, rows, request, None)


# --- trades ------------------------------------------------------------------


def trade_row(item: dict[str, Any]) -> list[str | None]:
    return [
        str(item["a"]),
        decimal_text(item.get("p")),
        decimal_text(item.get("q")),
        None if whole_of(item.get("f")) is None else str(item["f"]),
        None if whole_of(item.get("l")) is None else str(item["l"]),
        moment(whole_of(item.get("T"))),
        boolean_of(item.get("m")),
    ]


def _trades(answer: Any) -> list[dict[str, Any]]:
    return [
        one
        for one in answer
        if isinstance(one, dict) and whole_of(one.get("a")) is not None
    ]


async def newest_trade_id(
    session: BinanceSession, market: Market, symbol: str, node_id: str
) -> int | None:
    answer = _trades(
        await session.get(
            market, "aggTrades", {"symbol": symbol, "limit": "1"}, node_id
        )
    )
    return int(answer[-1]["a"]) if answer else None


async def oldest_trade_id(
    session: BinanceSession, market: Market, symbol: str, node_id: str
) -> int | None:
    """The oldest aggregated trade Binance still answers.

    Spot answers from id 0 with the oldest it keeps; futures refuse anything
    older than their window, so the first trade inside it is asked by time.
    """
    params = {"symbol": symbol, "limit": "1"}
    if market.trades_window_ms is None:
        params["fromId"] = "0"
    else:
        # A minute inside the window, so the clocks' difference cannot put
        # the request outside it.
        start = int(time.time() * 1000) - market.trades_window_ms + 60_000
        params["startTime"] = str(start)
        params["endTime"] = str(start + HOUR_MS - 1)
    answer = _trades(await session.get(market, "aggTrades", params, node_id))
    return int(answer[0]["a"]) if answer else None


async def _id_at(
    session: BinanceSession,
    market: Market,
    symbol: str,
    milliseconds: int,
    after: bool,
    node_id: str,
) -> int:
    """The first trade at or after a time, or the last at or before it.

    Binance answers a time window of at most an hour, so the trade is looked
    for within the hour on that side of the time.
    """
    start, end = (
        (milliseconds, milliseconds + HOUR_MS - 1)
        if after
        else (milliseconds - HOUR_MS + 1, milliseconds)
    )
    params = {
        "symbol": symbol,
        "startTime": str(start),
        "endTime": str(end),
        "limit": "1" if after else "1000",
    }
    answer = _trades(await session.get(market, "aggTrades", params, node_id))
    if not answer:
        raise ValueError(
            say("No trade within an hour of that time; filter by id instead")
        )
    return int(answer[0]["a"] if after else answer[-1]["a"])


async def trade_bounds(
    session: BinanceSession,
    market: Market,
    symbol: str,
    filters: list[Filter],
    node_id: str,
) -> Bounds:
    ids = bounds_of(filters, "id", lambda text: whole_number("id", text))
    times = bounds_of(filters, "time", lambda text: milliseconds_of("time", text))
    low, high = ids.low, ids.high
    if times.low is not None:
        found = await _id_at(session, market, symbol, times.low, True, node_id)
        low = found if low is None else max(low, found)
    if times.high is not None:
        found = await _id_at(session, market, symbol, times.high, False, node_id)
        high = found if high is None else min(high, found)
    return Bounds(low, high)


async def read_trades(
    session: BinanceSession,
    market: Market,
    symbol: str,
    first: int,
    last: int,
    node_id: str,
) -> list[dict[str, Any]]:
    """Trades `first` to `last`, both included, oldest first."""
    found: list[dict[str, Any]] = []
    cursor = first
    while cursor <= last:
        count = min(market.trades_per_request, last - cursor + 1)
        params = {"symbol": symbol, "fromId": str(cursor), "limit": str(count)}
        batch = _trades(await session.get(market, "aggTrades", params, node_id))
        batch = [one for one in batch if int(one["a"]) <= last]
        if not batch:
            break
        found.extend(batch)
        cursor = int(batch[-1]["a"]) + 1
    return found


async def trades_page(
    session: BinanceSession, place: BinancePlace, request: FetchRequest
) -> FetchResult:
    checked_filters(request.filters, TRADE_COLUMNS)
    checked_sorts(request.sort, TRADE_COLUMNS)
    if too_deep(request):
        raise ValueError(
            say(
                "A page reaches at most {n} trades deep; narrow it by id or time",
                n=DEPTH_CEILING,
            )
        )
    assert place.symbol is not None
    market, symbol, node_id = place.market, place.symbol, request.node_id
    newest = await newest_trade_id(session, market, symbol, node_id)
    if newest is None:
        return paged(TRADE_COLUMNS, [], request, None)
    bounds = await trade_bounds(session, market, symbol, request.filters, node_id)
    top = newest if bounds.high is None else min(newest, bounds.high)
    bottom = bounds.low
    if descending(request.sort, "id"):
        last = top - request.offset
        first = last - request.limit + 1
        if bottom is not None:
            first = max(first, bottom)
        if last < first:
            return paged(TRADE_COLUMNS, [], request, None)
        trades = await read_trades(
            session, market, symbol, max(first, 0), last, node_id
        )
        rows = [trade_row(one) for one in reversed(trades)]
        floor = bottom if bottom is not None else 0
        has_more = first > floor
    else:
        if bottom is None:
            bottom = await oldest_trade_id(session, market, symbol, node_id) or 0
        first = bottom + request.offset
        last = min(top, first + request.limit - 1)
        if last < first:
            return paged(TRADE_COLUMNS, [], request, None)
        trades = await read_trades(session, market, symbol, first, last, node_id)
        rows = [trade_row(one) for one in trades]
        has_more = last < top
    return FetchResult(
        columns=TRADE_COLUMNS,
        rows=rows,
        has_more=has_more,
        page_commands=["download", "chart", "share"],
    )


# --- the lists ------------------------------------------------------------------


async def ticker_rows(
    session: BinanceSession, market: Market
) -> list[list[str | None]]:
    sizes = {one.name: one.contract_size for one in await session.symbols(market)}
    return [
        ticker_row(item, sizes[item["symbol"]] if market.in_contracts else None)
        for item in await session.tickers(market)
        if item.get("symbol") in sizes
    ]


# --- the order book ---------------------------------------------------------


async def book_answer(
    session: BinanceSession, market: Market, symbol: str, depth: int, node_id: str
) -> dict[str, Any]:
    """The book to a depth Binance accepts, its sides as `bids` and `asks`."""
    params = {"symbol": symbol, "limit": str(depth)}
    answer = await session.get(market, "depth", params, node_id)
    return answer if isinstance(answer, dict) else {}
