"""A market's feeds as rows, in the shared columns (D433).

Decimals stay OKX's text and times leave in UTC (D425). A column keeps one
meaning across exchanges: `volume` is the base asset's and `quote_volume` the
quote asset's. OKX counts a contract's volume in contracts and gives the
base coin's beside it; its tickers have no quote volume for linear
contracts, so there the column is left out, and on inverse it is the
contracts times their worth in USD, exact. A trade's size on inverse is
USD, so there the trades say `quote_quantity` instead of `quantity`.
"""

import calendar
import time
from datetime import UTC, datetime
from typing import Any

from app.adapters.fetch import (
    FetchColumn,
    FetchRequest,
    FetchResult,
    Filter,
    Sort,
)
from app.adapters.listed import (
    checked_filters,
    checked_sorts,
    column,
    milliseconds_of,
)
from app.adapters.market.catalog import Place
from app.adapters.market.columns import (
    CANDLE_COLUMNS,
    DEPTH_CEILING,
    TICKER_COLUMNS,
    TRADE_COLUMNS,
    Bounds,
    bounds_of,
    descending,
    only,
    paged,
    too_deep,
)
from app.adapters.market.shape import INTERVAL_MS
from app.adapters.market.values import (
    decimal_text,
    difference,
    milliseconds,
    moment,
    percent_change,
    whole_number,
)
from app.adapters.okx.markets import (
    CANDLES_PER_REQUEST,
    INTERVALS,
    TRADES_PER_REQUEST,
    Market,
)
from app.adapters.okx.session import (
    BOOKS,
    CANDLES,
    TRADES,
    OkxSession,
    OkxSymbol,
    contracts_worth,
)
from app.core.translation import say

type OkxPlace = Place[Market]

DAY_MS = 86_400_000
# OKX answers trades of the last three months; a day inside them is asked
# for the oldest, so the clocks' difference cannot put it outside.
TRADES_KEPT_MS = 89 * DAY_MS
# The shortest a month's candle is, so a span of months never holds more
# candles than were asked.
_SHORTEST_MS = {"1M": 28 * DAY_MS}
EMPTY_SPANS = 20

_TICKER_NAMES = [
    "symbol",
    "last_price",
    "price_change",
    "price_change_percent",
    "open_price",
    "high_price",
    "low_price",
    "volume",
    "quote_volume",
]
OKX_TICKER_COLUMNS = only(TICKER_COLUMNS, _TICKER_NAMES)
LINEAR_TICKER_COLUMNS = only(TICKER_COLUMNS, _TICKER_NAMES[:-1])

OKX_CANDLE_COLUMNS = only(
    CANDLE_COLUMNS,
    [
        "open_time",
        "close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "closed",
    ],
)

OKX_TRADE_COLUMNS = only(
    TRADE_COLUMNS, ["id", "price", "quantity", "time", "buyer_is_maker"]
)
# On inverse a trade's size is USD: what it is worth, not how much coin.
INVERSE_TRADE_COLUMNS = [
    OKX_TRADE_COLUMNS[0],
    OKX_TRADE_COLUMNS[1],
    column("quote_quantity", "number"),
    *OKX_TRADE_COLUMNS[3:],
]


def ticker_columns(market: Market) -> list[FetchColumn]:
    if market.futures and not market.in_contracts:
        return LINEAR_TICKER_COLUMNS
    return OKX_TICKER_COLUMNS


def trade_columns(market: Market) -> list[FetchColumn]:
    return INVERSE_TRADE_COLUMNS if market.in_contracts else OKX_TRADE_COLUMNS


def _now_ms() -> int:
    return int(time.time() * 1000)


def ticker_row(
    market: Market, item: dict[str, Any], symbol: OkxSymbol | None
) -> list[str | None]:
    last = decimal_text(item.get("last"))
    opened = decimal_text(item.get("open24h"))
    row: list[str | None] = [
        str(item.get("instId")),
        last,
        difference(last, opened),
        percent_change(last, opened),
        opened,
        decimal_text(item.get("high24h")),
        decimal_text(item.get("low24h")),
    ]
    if not market.futures:
        return [
            *row,
            decimal_text(item.get("vol24h")),
            decimal_text(item.get("volCcy24h")),
        ]
    # A contract's volume is in contracts; OKX gives the base coin's beside.
    row.append(decimal_text(item.get("volCcy24h")))
    if market.in_contracts:
        value = symbol.contract_value if symbol is not None else None
        row.append(contracts_worth(item.get("vol24h"), value))
    return row


async def ticker_rows(session: OkxSession, market: Market) -> list[list[str | None]]:
    """Every live symbol's day; one not live is left out."""
    symbols: dict[str, OkxSymbol] = {
        one.name: one
        for one in await session.symbols(market)
        if isinstance(one, OkxSymbol)
    }
    return [
        ticker_row(market, item, symbols[str(item.get("instId"))])
        for item in await session.tickers(market)
        if item.get("instId") in symbols
    ]


# --- candles --------------------------------------------------------------------


def close_ms(interval: str, open_ms: int) -> int:
    """The last millisecond of a candle: a month's by the calendar."""
    if interval != "1M":
        return open_ms + INTERVAL_MS[interval] - 1
    at = datetime.fromtimestamp(open_ms / 1000, tz=UTC)
    days = calendar.monthrange(at.year, at.month)[1]
    return open_ms + days * 86_400_000 - 1


def shortest_ms(interval: str) -> int:
    return _SHORTEST_MS.get(interval, INTERVAL_MS[interval])


def candle_row(market: Market, interval: str, raw: list[Any]) -> list[str | None]:
    """A candle — open time, open, high, low, close, volume in contracts or
    the base, volume in the coin or the quote, in the quote, confirmed — as
    a row."""
    raw = list(raw) + [None] * max(0, 9 - len(raw))
    open_ms = milliseconds(raw[0]) or 0
    base = raw[6] if market.futures else raw[5]
    return [
        moment(open_ms),
        moment(close_ms(interval, open_ms)),
        *(decimal_text(raw[index]) for index in range(1, 5)),
        decimal_text(base),
        decimal_text(raw[7]),
        "true" if str(raw[8]) == "1" else "false",
    ]


def klines(answer: Any) -> list[list[Any]]:
    return [
        raw
        for raw in (answer if isinstance(answer, list) else [])
        if isinstance(raw, list) and raw and milliseconds(raw[0]) is not None
    ]


async def candles_between(
    session: OkxSession,
    market: Market,
    symbol: str,
    interval: str,
    first: int,
    count: int,
    last: int | None,
    node_id: str,
) -> list[list[Any]]:
    """Up to `count` candles opening at `first` or after, oldest first.

    OKX answers the newest of a span between `before` and `after`, both
    left out, so the span is cut to hold no more than `count` candles.
    """
    end = first + count * shortest_ms(interval)
    if last is not None:
        end = min(end, last + 1)
    params = {
        "instId": symbol,
        "bar": INTERVALS[interval],
        "before": str(first - 1),
        "after": str(end),
        "limit": str(min(count, CANDLES_PER_REQUEST)),
    }
    return list(reversed(klines(await session.get(market, CANDLES, params, node_id))))


async def read_candles(
    session: OkxSession,
    market: Market,
    symbol: str,
    interval: str,
    filters: list[Filter],
    newest: bool,
    need: int,
    node_id: str,
) -> list[list[Any]]:
    """Up to `need` candles in the asked order, a request at a time."""
    bounds = bounds_of(
        filters, "open_time", lambda text: milliseconds_of("open_time", text)
    )
    found: list[list[Any]] = []
    if newest:
        cursor = None if bounds.high is None else bounds.high + 1
        while len(found) < need:
            count = min(CANDLES_PER_REQUEST, need - len(found))
            params = {"instId": symbol, "bar": INTERVALS[interval], "limit": str(count)}
            if cursor is not None:
                params["after"] = str(cursor)
            batch = klines(await session.get(market, CANDLES, params, node_id))
            for raw in batch:
                if bounds.low is not None and int(raw[0]) < bounds.low:
                    return found
                found.append(raw)
            if len(batch) < count:
                break
            cursor = int(batch[-1][0])
        return found
    if bounds.low is not None:
        cursor = bounds.low
    else:
        # OKX has no way to ask for its oldest candle; the symbol's listing
        # is where its own candles begin.
        listed = (await session.instrument(market, symbol, node_id)).onboard_ms
        cursor = listed or _now_ms() - need * shortest_ms(interval)
    stop = bounds.high if bounds.high is not None else _now_ms()
    # A span with no candles moves on; this many such spans end the read.
    empty = 0
    while len(found) < need and cursor <= stop and empty < EMPTY_SPANS:
        count = min(CANDLES_PER_REQUEST, need - len(found))
        batch = await candles_between(
            session, market, symbol, interval, cursor, count, bounds.high, node_id
        )
        found.extend(batch)
        empty = 0 if batch else empty + 1
        span_end = cursor + count * shortest_ms(interval)
        cursor = int(batch[-1][0]) + 1 if len(batch) == count else span_end
    return found[:need]


def checked_candles(filters: list[Filter], sort: list[Sort]) -> None:
    checked_filters(filters, OKX_CANDLE_COLUMNS)
    checked_sorts(sort, OKX_CANDLE_COLUMNS)


async def candles_page(
    session: OkxSession, place: OkxPlace, request: FetchRequest
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
    found = await read_candles(
        session,
        place.market,
        place.symbol,
        place.interval,
        request.filters,
        descending(request.sort, "open_time"),
        request.offset + request.limit + 1,
        request.node_id,
    )
    rows = [candle_row(place.market, place.interval, raw) for raw in found]
    return paged(OKX_CANDLE_COLUMNS, rows, request, None)


# --- trades ---------------------------------------------------------------------


def trade_row(
    market: Market, item: dict[str, Any], value: str | None
) -> list[str | None]:
    """A trade; the side OKX names is the taker's, so a seller took a buyer
    resting in the book. A contract's size is said as what it is worth."""
    side = item.get("side")
    size = (
        decimal_text(item.get("sz"))
        if not market.futures
        else contracts_worth(item.get("sz"), value)
    )
    return [
        str(item.get("tradeId")),
        decimal_text(item.get("px")),
        size,
        moment(milliseconds(item.get("ts"))),
        None
        if side not in {"buy", "sell"}
        else ("true" if side == "sell" else "false"),
    ]


def trade_id(item: dict[str, Any]) -> int | None:
    return milliseconds(item.get("tradeId"))


def _trades(answer: Any) -> list[dict[str, Any]]:
    return [
        one
        for one in (answer if isinstance(answer, list) else [])
        if isinstance(one, dict) and trade_id(one) is not None
    ]


async def newest_trade(
    session: OkxSession, market: Market, symbol: str, node_id: str
) -> dict[str, Any] | None:
    params = {"instId": symbol, "limit": "1"}
    found = _trades(await session.get(market, TRADES, params, node_id))
    return found[0] if found else None


async def trade_before(
    session: OkxSession, market: Market, symbol: str, at_ms: int, node_id: str
) -> int | None:
    """The id of the last trade before a time, if OKX still has one."""
    params = {"instId": symbol, "type": "2", "after": str(at_ms), "limit": "1"}
    found = _trades(await session.get(market, TRADES, params, node_id))
    return trade_id(found[0]) if found else None


async def oldest_trade_id(
    session: OkxSession, market: Market, symbol: str, node_id: str
) -> int | None:
    """About the oldest trade OKX answers: the first a day inside its three
    months, or for a symbol younger than that its first, as OKX numbers an
    instrument's trades from one."""
    before = await trade_before(
        session, market, symbol, _now_ms() - TRADES_KEPT_MS, node_id
    )
    return 1 if before is None else before + 1


async def read_trades(
    session: OkxSession,
    market: Market,
    symbol: str,
    first: int,
    last: int,
    node_id: str,
) -> list[dict[str, Any]]:
    """Trades `first` to `last`, both included, oldest first.

    OKX numbers a symbol's trades one after another, so a span of ids is a
    request; it answers the newest of the span between `before` and
    `after`, both left out.
    """
    found: list[dict[str, Any]] = []
    cursor = first
    while cursor <= last:
        end = min(last, cursor + TRADES_PER_REQUEST - 1)
        params = {
            "instId": symbol,
            "type": "1",
            "before": str(cursor - 1),
            "after": str(end + 1),
            "limit": str(TRADES_PER_REQUEST),
        }
        batch = _trades(await session.get(market, TRADES, params, node_id))
        found += sorted(batch, key=lambda one: trade_id(one) or 0)
        cursor = end + 1
    return found


async def trade_bounds(
    session: OkxSession,
    market: Market,
    symbol: str,
    filters: list[Filter],
    node_id: str,
) -> Bounds:
    """The ids a page's id and time filters keep, a time found by OKX."""
    ids = bounds_of(filters, "id", lambda text: whole_number("id", text))
    times = bounds_of(filters, "time", lambda text: milliseconds_of("time", text))
    low, high = ids.low, ids.high
    if times.low is not None:
        before = await trade_before(session, market, symbol, times.low, node_id)
        found = 0 if before is None else before + 1
        low = found if low is None else max(low, found)
    if times.high is not None:
        last = await trade_before(session, market, symbol, times.high + 1, node_id)
        high = (last or 0) if high is None else min(high, last or 0)
    return Bounds(low, high)


async def trades_page(
    session: OkxSession, place: OkxPlace, request: FetchRequest
) -> FetchResult:
    columns = trade_columns(place.market)
    checked_filters(request.filters, columns)
    checked_sorts(request.sort, columns)
    if too_deep(request):
        raise ValueError(
            say(
                "A page reaches at most {n} trades deep; narrow it by id or time",
                n=DEPTH_CEILING,
            )
        )
    assert place.symbol is not None
    market, symbol, node_id = place.market, place.symbol, request.node_id
    instrument = await session.instrument(market, symbol, node_id)
    value = instrument.contract_value
    newest = await newest_trade(session, market, symbol, node_id)
    if newest is None:
        return paged(columns, [], request, None)
    bounds = await trade_bounds(session, market, symbol, request.filters, node_id)
    top = trade_id(newest) or 0
    top = top if bounds.high is None else min(top, bounds.high)
    bottom = bounds.low
    if descending(request.sort, "id"):
        last = top - request.offset
        first = last - request.limit + 1
        if bottom is not None:
            first = max(first, bottom)
        if last < first:
            return paged(columns, [], request, None)
        trades = await read_trades(
            session, market, symbol, max(first, 0), last, node_id
        )
        rows = [trade_row(market, one, value) for one in reversed(trades)]
        has_more = first > (bottom if bottom is not None else 0) and bool(trades)
    else:
        if bottom is None:
            bottom = await oldest_trade_id(session, market, symbol, node_id) or top
        first = bottom + request.offset
        last = min(top, first + request.limit - 1)
        if last < first:
            return paged(columns, [], request, None)
        trades = await read_trades(session, market, symbol, first, last, node_id)
        rows = [trade_row(market, one, value) for one in trades]
        has_more = last < top
    return FetchResult(
        columns=columns,
        rows=rows,
        has_more=has_more,
        page_commands=["download", "chart", "share"],
    )


# --- the order book ---------------------------------------------------------


async def book_answer(
    session: OkxSession, market: Market, symbol: str, depth: int, node_id: str
) -> dict[str, Any]:
    """The book to a depth; a contract's size said as what it is worth."""
    params = {"instId": symbol, "sz": str(depth)}
    answer = await session.get(market, BOOKS, params, node_id)
    book = answer[0] if isinstance(answer, list) and answer else {}
    value = (
        (await session.instrument(market, symbol, node_id)).contract_value
        if market.futures
        else None
    )
    return {
        "bids": sized(market, book.get("bids"), value),
        "asks": sized(market, book.get("asks"), value),
    }


def sized(market: Market, levels: Any, value: str | None) -> list[list[Any]]:
    """Levels of a price and a size, a contract's size as what it is worth."""
    found: list[list[Any]] = []
    for entry in levels if isinstance(levels, list) else []:
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        size = entry[1] if not market.futures else contracts_worth(entry[1], value)
        found.append([entry[0], size])
    return found
