"""Coinbase's feeds as rows, in the shared columns (D439).

Decimals stay Coinbase's text and times leave in UTC (D425). Coinbase gives
volumes in the base asset only — the day's and a candle's — so `quote_volume`
is left out rather than computed from a price. A trade's `side` is the
maker's: a buy is a resting buyer a seller took.
"""

import time
from datetime import UTC, datetime
from typing import Any

from app.adapters.coinbase.markets import (
    CANDLES_PER_REQUEST,
    INTERVALS,
    TRADES_PER_REQUEST,
    Market,
)
from app.adapters.coinbase.session import CoinbaseSession
from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult, Filter
from app.adapters.listed import checked_filters, checked_sorts, column, milliseconds_of
from app.adapters.market.catalog import Place
from app.adapters.market.columns import (
    CANDLE_COLUMNS,
    DEPTH_CEILING,
    TICKER_COLUMNS,
    TRADE_COLUMNS,
    bounds_of,
    descending,
    only,
    paged,
    too_deep,
)
from app.adapters.market.values import (
    decimal_text,
    difference,
    moment,
    percent_change,
    whole_number,
    whole_of,
)
from app.core.translation import say

type CoinbasePlace = Place[Market]

# A span this many granularities long with no candle ends a read: Coinbase
# publishes nothing for an interval without a trade.
EMPTY_SPANS = 20

COINBASE_TICKER_COLUMNS = only(
    TICKER_COLUMNS,
    [
        "symbol",
        "last_price",
        "price_change",
        "price_change_percent",
        "open_price",
        "high_price",
        "low_price",
        "volume",
    ],
)

COINBASE_CANDLE_COLUMNS = only(
    CANDLE_COLUMNS,
    ["open_time", "close_time", "open", "high", "low", "close", "volume", "closed"],
)

# Found by id; Coinbase has nothing to find a trade by its time.
COINBASE_TRADE_COLUMNS: list[FetchColumn] = [
    *only(TRADE_COLUMNS, ["id", "price", "quantity"]),
    column("time", "datetime"),
    *only(TRADE_COLUMNS, ["buyer_is_maker"]),
]


def _now_ms() -> int:
    return int(time.time() * 1000)


def iso_ms(value: Any) -> int | None:
    """Coinbase's ISO time, to the microsecond, as milliseconds."""
    if not isinstance(value, str) or not value:
        return None
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(at.astimezone(UTC).timestamp() * 1000)


def ticker_row(item: dict[str, Any]) -> list[str | None]:
    last = decimal_text(item.get("last"))
    opened = decimal_text(item.get("open"))
    return [
        str(item.get("id")),
        last,
        difference(last, opened),
        percent_change(last, opened),
        opened,
        decimal_text(item.get("high")),
        decimal_text(item.get("low")),
        decimal_text(item.get("volume")),
    ]


async def ticker_rows(
    session: CoinbaseSession, market: Market
) -> list[list[str | None]]:
    names = {one.name for one in await session.symbols(market)}
    return [
        ticker_row(item)
        for item in await session.tickers(market)
        if item.get("id") in names
    ]


# --- candles --------------------------------------------------------------------


def candle_row(interval: str, raw: list[Any], now_ms: int) -> list[str | None]:
    """A candle — time in seconds, low, high, open, close, volume — as a row."""
    raw = list(raw) + [None] * max(0, 6 - len(raw))
    open_ms = (whole_of(raw[0]) or 0) * 1000
    closing = open_ms + INTERVALS[interval] * 1000 - 1
    return [
        moment(open_ms),
        moment(closing),
        decimal_text(raw[3]),
        decimal_text(raw[2]),
        decimal_text(raw[1]),
        decimal_text(raw[4]),
        decimal_text(raw[5]),
        "true" if closing < now_ms else "false",
    ]


def candles_of(answer: Any) -> list[list[Any]]:
    return [
        raw
        for raw in (answer if isinstance(answer, list) else [])
        if isinstance(raw, list) and raw and whole_of(raw[0]) is not None
    ]


async def candles_between(
    session: CoinbaseSession,
    market: Market,
    symbol: str,
    interval: str,
    first_s: int,
    last_s: int,
    node_id: str,
) -> list[list[Any]]:
    """The candles opening from `first_s` to `last_s`, both included, oldest
    first; at most 300, as Coinbase answers."""
    params = {
        "granularity": str(INTERVALS[interval]),
        "start": str(first_s),
        "end": str(last_s),
    }
    found = candles_of(
        await session.get(market, f"/products/{symbol}/candles", params, node_id)
    )
    return sorted(
        (raw for raw in found if first_s <= int(raw[0]) <= last_s),
        key=lambda raw: int(raw[0]),
    )


async def read_candles(
    session: CoinbaseSession,
    market: Market,
    symbol: str,
    interval: str,
    filters: list[Filter],
    newest: bool,
    need: int,
    node_id: str,
) -> list[list[Any]]:
    """Up to `need` candles in the asked order, a span of 300 at a time."""
    step = INTERVALS[interval]
    bounds = bounds_of(
        filters, "open_time", lambda text: milliseconds_of("open_time", text)
    )
    low = None if bounds.low is None else -(-bounds.low // 1000)
    high = (bounds.high if bounds.high is not None else _now_ms()) // 1000
    found: list[list[Any]] = []
    empty = 0
    if newest:
        end = high - high % step
        while len(found) < need and empty < EMPTY_SPANS:
            start = end - (CANDLES_PER_REQUEST - 1) * step
            if low is not None:
                start = max(start, low)
            if start > end:
                break
            batch = await candles_between(
                session, market, symbol, interval, start, end, node_id
            )
            found += list(reversed(batch))
            empty = 0 if batch else empty + 1
            if low is not None and start <= low:
                break
            end = start - step
        return found[:need]
    start = low if low is not None else high - need * step
    start -= start % step
    while len(found) < need and start <= high and empty < EMPTY_SPANS:
        end = min(high, start + (CANDLES_PER_REQUEST - 1) * step)
        batch = await candles_between(
            session, market, symbol, interval, start, end, node_id
        )
        found += batch
        empty = 0 if batch else empty + 1
        start = end + step
    return found[:need]


async def candles_page(
    session: CoinbaseSession, place: CoinbasePlace, request: FetchRequest
) -> FetchResult:
    checked_filters(request.filters, COINBASE_CANDLE_COLUMNS)
    checked_sorts(request.sort, COINBASE_CANDLE_COLUMNS)
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
    now = _now_ms()
    rows = [candle_row(place.interval, raw, now) for raw in found]
    return paged(COINBASE_CANDLE_COLUMNS, rows, request, None)


# --- trades ---------------------------------------------------------------------


def trade_id(item: dict[str, Any]) -> int | None:
    return whole_of(item.get("trade_id"))


def trade_row(item: dict[str, Any]) -> list[str | None]:
    """A trade; Coinbase's side is the maker's, so `buy` is a buyer resting in
    the book that a seller took."""
    side = item.get("side")
    return [
        str(item.get("trade_id")),
        decimal_text(item.get("price")),
        decimal_text(item.get("size")),
        moment(iso_ms(item.get("time"))),
        None if side not in {"buy", "sell"} else ("true" if side == "buy" else "false"),
    ]


def _trades(answer: Any) -> list[dict[str, Any]]:
    return [
        one
        for one in (answer if isinstance(answer, list) else [])
        if isinstance(one, dict) and trade_id(one) is not None
    ]


async def newest_trade(
    session: CoinbaseSession, market: Market, symbol: str, node_id: str
) -> dict[str, Any] | None:
    found = _trades(
        await session.get(market, f"/products/{symbol}/trades", {"limit": "1"}, node_id)
    )
    return found[0] if found else None


async def read_trades(
    session: CoinbaseSession,
    market: Market,
    symbol: str,
    first: int,
    last: int,
    node_id: str,
) -> list[dict[str, Any]]:
    """Trades `first` to `last`, both included, oldest first.

    Coinbase numbers a product's trades one after another from one and keeps
    them all; `after` an id answers the ones before it, newest first.
    """
    found: list[dict[str, Any]] = []
    top = last
    while top >= first:
        count = min(TRADES_PER_REQUEST, top - first + 1)
        params = {"after": str(top + 1), "limit": str(count)}
        batch = _trades(
            await session.get(market, f"/products/{symbol}/trades", params, node_id)
        )
        found += [one for one in batch if first <= (trade_id(one) or 0) <= top]
        top -= count
    return sorted(found, key=lambda one: trade_id(one) or 0)


async def trades_page(
    session: CoinbaseSession, place: CoinbasePlace, request: FetchRequest
) -> FetchResult:
    columns = COINBASE_TRADE_COLUMNS
    checked_filters(request.filters, columns)
    checked_sorts(request.sort, columns)
    if too_deep(request):
        raise ValueError(
            say(
                "A page reaches at most {n} trades deep; narrow it by id",
                n=DEPTH_CEILING,
            )
        )
    assert place.symbol is not None
    market, symbol, node_id = place.market, place.symbol, request.node_id
    newest = await newest_trade(session, market, symbol, node_id)
    if newest is None:
        return paged(columns, [], request, None)
    ids = bounds_of(request.filters, "id", lambda text: whole_number("id", text))
    top = trade_id(newest) or 0
    top = top if ids.high is None else min(top, ids.high)
    bottom = max(1, ids.low if ids.low is not None else 1)
    if descending(request.sort, "id"):
        last = top - request.offset
        first = max(bottom, last - request.limit + 1)
        if last < first:
            return paged(columns, [], request, None)
        trades = await read_trades(session, market, symbol, first, last, node_id)
        rows = [trade_row(one) for one in reversed(trades)]
        has_more = first > bottom
    else:
        first = bottom + request.offset
        last = min(top, first + request.limit - 1)
        if last < first:
            return paged(columns, [], request, None)
        trades = await read_trades(session, market, symbol, first, last, node_id)
        rows = [trade_row(one) for one in trades]
        has_more = last < top
    return FetchResult(
        columns=columns,
        rows=rows,
        has_more=has_more,
        page_commands=["download", "chart", "share"],
    )


# --- the order book ---------------------------------------------------------


async def book_answer(
    session: CoinbaseSession, market: Market, symbol: str, depth: int, node_id: str
) -> dict[str, Any]:
    """The whole aggregated book, as Coinbase answers it, cut to the depth."""
    answer = await session.get(
        market, f"/products/{symbol}/book", {"level": "2"}, node_id
    )
    book = answer if isinstance(answer, dict) else {}
    return {
        "bids": list(book.get("bids") or [])[:depth],
        "asks": list(book.get("asks") or [])[:depth],
    }
