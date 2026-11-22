"""A category's feeds as rows, in the shared columns (D427).

Decimals stay Bybit's text and times leave in UTC (D425). A column keeps one
meaning across exchanges: `volume` is the base asset's and `quote_volume` the
quote asset's, which on inverse is Bybit's turnover and volume the other way
round. What Bybit has no value for — a ticker's weighted price or trade
count, a candle's taker volumes — is left out of the columns.
"""

import calendar
import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.adapters.bybit.markets import CANDLES_PER_REQUEST, INTERVALS, Market
from app.adapters.bybit.session import BybitSession
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
    listed_column,
    listed_page,
    milliseconds_of,
)
from app.adapters.market.catalog import Place
from app.adapters.market.columns import (
    CANDLE_COLUMNS,
    DEPTH_CEILING,
    TICKER_COLUMNS,
    bounds_of,
    descending,
    only,
    paged,
    too_deep,
)
from app.adapters.market.shape import INTERVAL_MS
from app.adapters.market.values import decimal_text, milliseconds, moment
from app.core.translation import say

type BybitPlace = Place[Market]

BYBIT_TICKER_COLUMNS = only(
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
        "quote_volume",
    ],
)

BYBIT_CANDLE_COLUMNS = only(
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

# The newest trades Bybit answers, read whole: sorted and filtered here.
BYBIT_TRADE_COLUMNS: list[FetchColumn] = [
    listed_column("id", "string"),
    listed_column("price", "number"),
    listed_column("quantity", "number"),
    listed_column("time", "datetime"),
    listed_column("buyer_is_maker", "boolean"),
]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _difference(last: str | None, before: str | None) -> str | None:
    if last is None or before is None:
        return None
    return str(Decimal(last) - Decimal(before))


def percent_of(fraction: Any) -> str | None:
    """Bybit's change as a fraction, as a percent: exact, the point moved."""
    text = decimal_text(fraction)
    if text is None:
        return None
    try:
        shifted = Decimal(text).scaleb(2)
    except InvalidOperation:
        return None
    # `0.1` moved two places is `1E+1`; a whole number is written whole.
    exponent = shifted.as_tuple().exponent
    if isinstance(exponent, int) and exponent > 0:
        shifted = shifted.quantize(Decimal(1))
    return str(shifted)


def volumes(market: Market, volume: Any, turnover: Any) -> list[str | None]:
    """Base then quote: Bybit's volume and turnover, swapped on inverse (D427)."""
    if market.volume_in_quote:
        return [decimal_text(turnover), decimal_text(volume)]
    return [decimal_text(volume), decimal_text(turnover)]


def ticker_row(market: Market, item: dict[str, Any]) -> list[str | None]:
    last = decimal_text(item.get("lastPrice"))
    before = decimal_text(item.get("prevPrice24h"))
    return [
        str(item.get("symbol")),
        last,
        _difference(last, before),
        percent_of(item.get("price24hPcnt")),
        before,
        decimal_text(item.get("highPrice24h")),
        decimal_text(item.get("lowPrice24h")),
        *volumes(market, item.get("volume24h"), item.get("turnover24h")),
    ]


async def ticker_rows(session: BybitSession, market: Market) -> list[list[str | None]]:
    """Every trading symbol's day; a symbol not trading is left out."""
    names = {one.name for one in await session.symbols(market)}
    return [
        ticker_row(market, item)
        for item in await session.tickers(market)
        if item.get("symbol") in names
    ]


# --- candles --------------------------------------------------------------------


def close_ms(interval: str, open_ms: int) -> int:
    """The last millisecond of a candle: a month's by the calendar."""
    if interval != "1M":
        return open_ms + INTERVAL_MS[interval] - 1
    at = datetime.fromtimestamp(open_ms / 1000, tz=UTC)
    days = calendar.monthrange(at.year, at.month)[1]
    return open_ms + days * 86_400_000 - 1


def candle_row(
    market: Market, interval: str, raw: list[Any], now_ms: int
) -> list[str | None]:
    """A kline — start, open, high, low, close, volume, turnover — as a row."""
    raw = list(raw) + [None] * max(0, 7 - len(raw))
    open_ms = milliseconds(raw[0]) or 0
    closing = close_ms(interval, open_ms)
    return [
        moment(open_ms),
        moment(closing),
        *(decimal_text(raw[index]) for index in range(1, 5)),
        *volumes(market, raw[5], raw[6]),
        "true" if closing < now_ms else "false",
    ]


def _klines(answer: Any) -> list[list[Any]]:
    rows = answer.get("list") if isinstance(answer, dict) else None
    return [
        raw
        for raw in rows or []
        if isinstance(raw, list) and raw and milliseconds(raw[0]) is not None
    ]


async def read_candles(
    session: BybitSession,
    market: Market,
    symbol: str,
    interval: str,
    filters: list[Filter],
    newest: bool,
    need: int,
    node_id: str,
) -> list[list[Any]]:
    """Up to `need` klines in the asked order, a request at a time.

    Bybit answers newest first: from an end, the newest before it; from a
    start, the oldest after it, still newest first.
    """
    bounds = bounds_of(
        filters, "open_time", lambda text: milliseconds_of("open_time", text)
    )
    found: list[list[Any]] = []
    base = {"symbol": symbol, "interval": INTERVALS[interval]}
    if newest:
        cursor = bounds.high
        while len(found) < need:
            count = min(CANDLES_PER_REQUEST, need - len(found))
            params = {**base, "limit": str(count)}
            if cursor is not None:
                params["end"] = str(cursor)
            batch = _klines(await session.ask(market, "kline", params, node_id))
            for raw in batch:
                if bounds.low is not None and int(raw[0]) < bounds.low:
                    return found
                found.append(raw)
            if len(batch) < count:
                break
            cursor = int(batch[-1][0]) - 1
        return found
    cursor = bounds.low if bounds.low is not None else 0
    while len(found) < need:
        count = min(CANDLES_PER_REQUEST, need - len(found))
        params = {**base, "start": str(cursor), "limit": str(count)}
        if bounds.high is not None:
            params["end"] = str(bounds.high)
        batch = list(
            reversed(_klines(await session.ask(market, "kline", params, node_id)))
        )
        found.extend(batch)
        if len(batch) < count:
            break
        cursor = int(batch[-1][0]) + 1
    return found


def checked_candles(filters: list[Filter], sort: list[Sort]) -> None:
    checked_filters(filters, BYBIT_CANDLE_COLUMNS)
    checked_sorts(sort, BYBIT_CANDLE_COLUMNS)


async def candles_page(
    session: BybitSession, place: BybitPlace, request: FetchRequest
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
    klines = await read_candles(
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
    rows = [candle_row(place.market, place.interval, raw, now) for raw in klines]
    return paged(BYBIT_CANDLE_COLUMNS, rows, request, None)


# --- trades ---------------------------------------------------------------------


def trade_row(item: dict[str, Any]) -> list[str | None]:
    """A trade; the side Bybit names is the taker's, so a seller took a buyer
    resting in the book."""
    side = item.get("side", item.get("S"))
    return [
        str(item.get("execId", item.get("i"))),
        decimal_text(item.get("price", item.get("p"))),
        decimal_text(item.get("size", item.get("v"))),
        moment(milliseconds(item.get("time", item.get("T")))),
        None
        if side not in {"Buy", "Sell"}
        else ("true" if side == "Sell" else "false"),
    ]


def trade_time(item: dict[str, Any]) -> int | None:
    return milliseconds(item.get("time", item.get("T")))


async def recent_trades(
    session: BybitSession, market: Market, symbol: str, node_id: str
) -> list[dict[str, Any]]:
    """The newest trades Bybit answers, oldest first; it pages nothing."""
    params = {"symbol": symbol, "limit": str(market.trades_per_request)}
    answer = await session.ask(market, "recent-trade", params, node_id)
    found = [
        one
        for one in (answer.get("list") or [])
        if isinstance(one, dict) and trade_time(one) is not None
    ]
    # The newest first as Bybit sends them; by time, and within a millisecond
    # by its sequence, which only grows.
    return sorted(
        found,
        key=lambda one: (trade_time(one) or 0, milliseconds(one.get("seq")) or 0),
    )


async def trades_page(
    session: BybitSession, place: BybitPlace, request: FetchRequest
) -> FetchResult:
    assert place.symbol is not None
    trades = await recent_trades(session, place.market, place.symbol, request.node_id)
    sort = request.sort or [Sort(column="time", descending=True)]
    rows = listed_page(
        BYBIT_TRADE_COLUMNS, [trade_row(one) for one in trades], request.filters, sort
    )
    return paged(BYBIT_TRADE_COLUMNS, rows, request, None)


# --- the order book ---------------------------------------------------------


async def book_answer(
    session: BybitSession, market: Market, symbol: str, depth: int, node_id: str
) -> dict[str, Any]:
    params = {"symbol": symbol, "limit": str(depth)}
    answer = await session.ask(market, "orderbook", params, node_id)
    return {"bids": answer.get("b") or [], "asks": answer.get("a") or []}
