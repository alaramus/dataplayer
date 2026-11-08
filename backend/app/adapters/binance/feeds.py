"""A market's feeds as rows (D318).

Every decimal stays the text Binance wrote, checked to be a number and never
passed through a float; times arrive in milliseconds and leave as moments in
UTC. Tickers and Symbols are a whole market read at once, so they sort and
filter here; candles and trades are read from Binance a request at a time,
and only what Binance can bound — a time, an id — narrows them.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.adapters.binance.catalog import Place
from app.adapters.binance.markets import Market
from app.adapters.binance.session import BinanceSession, Symbol, decimal_text
from app.adapters.fetch import (
    FetchColumn,
    FetchRequest,
    FetchResult,
    Filter,
    FilterOp,
    InFilter,
    NullFilter,
    ScalarFilter,
    Sort,
)
from app.adapters.relation import ColumnType, TypeCategory
from app.core.translation import say

# How deep a page may reach into candles or trades, read a request at a time.
DEPTH_CEILING = 10_000
DEFAULT_BOOK_LEVELS = 100
HOUR_MS = 3_600_000

_TEXT_OPS: list[FilterOp] = ["eq", "ne", "contains", "starts_with", "in"]
_ORDER_OPS: list[FilterOp] = ["eq", "ne", "gt", "gte", "lt", "lte"]
_RANGE_OPS: list[FilterOp] = ["gt", "gte", "lt", "lte"]
_NULL_OPS: list[FilterOp] = ["is_null", "is_not_null"]

_SQL: dict[TypeCategory, str] = {
    "string": "text",
    "number": "numeric",
    "datetime": "timestamptz",
    "boolean": "boolean",
}


def _column(
    name: str,
    category: TypeCategory,
    ops: list[FilterOp] | None = None,
    *,
    sql: str | None = None,
    sortable: bool = False,
    nullable: bool = False,
) -> FetchColumn:
    return FetchColumn(
        name=name,
        type=ColumnType(sql=sql or _SQL[category], category=category),
        sortable=sortable,
        filter_operators=ops or [],
        nullable=nullable,
    )


def _listed(
    name: str, category: TypeCategory, *, nullable: bool = False
) -> FetchColumn:
    """A column of a list read whole: sorted and filtered here, by anything."""
    ops = list(_TEXT_OPS if category == "string" else _ORDER_OPS)
    if nullable:
        ops += _NULL_OPS
    return _column(name, category, ops, sortable=True, nullable=nullable)


def moment(milliseconds: int | None) -> str | None:
    if milliseconds is None:
        return None
    at = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def milliseconds_of(column: str, text: str) -> int:
    try:
        at = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(say("{column} takes a date and time", column=column)) from None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return int(at.timestamp() * 1000)


def _whole_number(column: str, text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise ValueError(say("{column} takes a whole number", column=column)) from None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _bool(value: Any) -> str | None:
    return None if not isinstance(value, bool) else ("true" if value else "false")


def _checked(filters: list[Filter], columns: list[FetchColumn]) -> None:
    offered = {column.name: column.filter_operators for column in columns}
    for one in filters:
        ops = offered.get(one.column)
        if ops is None:
            raise ValueError(say("Unknown column: {column}", column=one.column))
        if one.op not in ops:
            raise ValueError(
                say("{column} cannot be filtered that way", column=one.column)
            )


def _sorts_checked(sort: list[Sort], columns: list[FetchColumn]) -> None:
    sortable = {column.name for column in columns if column.sortable}
    for one in sort:
        if one.column not in sortable:
            raise ValueError(say("{column} cannot be sorted", column=one.column))


# --- a list read whole: Tickers and Symbols ----------------------------------


def _key(category: TypeCategory, text: str | None) -> Any:
    """What a cell is compared by: a number by its value, a moment by its time."""
    if text is None:
        return None
    if category == "number":
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    if category == "datetime":
        return milliseconds_of("", text)
    return text.casefold()


def _matcher(
    one: Filter, index: int, category: TypeCategory
) -> Callable[[list[str | None]], bool]:
    if isinstance(one, NullFilter):
        wanted_null = one.op == "is_null"
        return lambda row: (row[index] is None) == wanted_null
    if isinstance(one, InFilter):
        wanted = {_key(category, value) for value in one.values}
        return lambda row: _key(category, row[index]) in wanted
    assert isinstance(one, ScalarFilter)
    if category == "number":
        try:
            Decimal(one.value)
        except InvalidOperation:
            raise ValueError(
                say("{column} takes a number", column=one.column)
            ) from None
    if category == "datetime":
        milliseconds_of(one.column, one.value)
    needle = _key(category, one.value)
    op = one.op

    def matches(row: list[str | None]) -> bool:
        value = _key(category, row[index])
        if value is None:
            return op == "ne"
        if op == "contains":
            return bool(needle in value)
        if op == "starts_with":
            return bool(value.startswith(needle))
        return bool(
            {
                "eq": value == needle,
                "ne": value != needle,
                "gt": value > needle,
                "gte": value >= needle,
                "lt": value < needle,
                "lte": value <= needle,
            }[op]
        )

    return matches


def listed_page(
    columns: list[FetchColumn],
    rows: list[list[str | None]],
    filters: list[Filter],
    sort: list[Sort],
) -> list[list[str | None]]:
    """Rows of a list read whole, filtered and sorted as asked."""
    _checked(filters, columns)
    _sorts_checked(sort, columns)
    names = [column.name for column in columns]
    categories = [column.type.category for column in columns]
    for one in filters:
        index = names.index(one.column)
        keep = _matcher(one, index, categories[index])
        rows = [row for row in rows if keep(row)]
    for order in reversed(sort):
        index = names.index(order.column)
        category = categories[index]
        present = [row for row in rows if _key(category, row[index]) is not None]
        absent = [row for row in rows if _key(category, row[index]) is None]
        present.sort(
            key=lambda row: _key(category, row[index]), reverse=order.descending
        )
        rows = present + absent
    return rows


TICKER_COLUMNS = [
    _listed("symbol", "string"),
    _listed("last_price", "number"),
    _listed("price_change", "number"),
    _listed("price_change_percent", "number"),
    _listed("weighted_avg_price", "number"),
    _listed("open_price", "number"),
    _listed("high_price", "number"),
    _listed("low_price", "number"),
    _listed("volume", "number"),
    _listed("quote_volume", "number"),
    _listed("trades", "number"),
    _listed("open_time", "datetime"),
    _listed("close_time", "datetime"),
]

_TICKER_FIELDS = (
    "lastPrice",
    "priceChange",
    "priceChangePercent",
    "weightedAvgPrice",
    "openPrice",
    "highPrice",
    "lowPrice",
    "volume",
    "quoteVolume",
)


def ticker_row(item: dict[str, Any]) -> list[str | None]:
    return [
        str(item.get("symbol")),
        *(decimal_text(item.get(name)) for name in _TICKER_FIELDS),
        None if _int(item.get("count")) is None else str(item.get("count")),
        moment(_int(item.get("openTime"))),
        moment(_int(item.get("closeTime"))),
    ]


SPOT_SYMBOL_COLUMNS = [
    _listed("symbol", "string"),
    _listed("base", "string"),
    _listed("quote", "string"),
    _listed("status", "string"),
    _listed("price_step", "number", nullable=True),
    _listed("quantity_step", "number", nullable=True),
    _listed("min_notional", "number", nullable=True),
]

FUTURES_SYMBOL_COLUMNS = [
    *SPOT_SYMBOL_COLUMNS,
    _listed("contract_type", "string", nullable=True),
    _listed("delivery_time", "datetime", nullable=True),
    _listed("listed_time", "datetime", nullable=True),
]

# Binance dates a perpetual contract's delivery in 2100; it has none.
_NEVER_MS = 4_000_000_000_000


def symbol_columns(market: Market) -> list[FetchColumn]:
    return SPOT_SYMBOL_COLUMNS if market.key == "spot" else FUTURES_SYMBOL_COLUMNS


def symbol_row(market: Market, one: Symbol) -> list[str | None]:
    row: list[str | None] = [
        one.name,
        one.base,
        one.quote,
        one.status,
        one.price_step,
        one.quantity_step,
        one.min_notional,
    ]
    if market.key != "spot":
        delivery = one.delivery_ms
        row += [
            one.contract_type,
            moment(delivery if delivery is not None and delivery < _NEVER_MS else None),
            moment(one.onboard_ms),
        ]
    return row


def _paged(
    columns: list[FetchColumn],
    rows: list[list[str | None]],
    request: FetchRequest,
    refresh_seconds: int | None,
) -> FetchResult:
    end = request.offset + request.limit
    return FetchResult(
        columns=columns,
        rows=rows[request.offset : end],
        has_more=len(rows) > end,
        page_commands=["download", "chart", "share"],
        refresh_seconds=refresh_seconds,
    )


# --- candles --------------------------------------------------------------------

CANDLE_COLUMNS = [
    _column("open_time", "datetime", _RANGE_OPS, sortable=True),
    _column("close_time", "datetime"),
    _column("open", "number"),
    _column("high", "number"),
    _column("low", "number"),
    _column("close", "number"),
    _column("volume", "number"),
    _column("quote_volume", "number"),
    _column("trades", "number", sql="bigint"),
    _column("taker_buy_volume", "number"),
    _column("taker_buy_quote_volume", "number"),
    _column("closed", "boolean"),
]


@dataclass(frozen=True)
class Candle:
    open_ms: int
    raw: list[Any]

    def row(self, now_ms: int) -> list[str | None]:
        raw = self.raw
        close_ms = _int(raw[6]) if len(raw) > 6 else None
        return [
            moment(self.open_ms),
            moment(close_ms),
            *(
                decimal_text(raw[index]) if len(raw) > index else None
                for index in range(1, 6)
            ),
            decimal_text(raw[7]) if len(raw) > 7 else None,
            str(raw[8]) if len(raw) > 8 and _int(raw[8]) is not None else None,
            decimal_text(raw[9]) if len(raw) > 9 else None,
            decimal_text(raw[10]) if len(raw) > 10 else None,
            "true" if close_ms is not None and close_ms < now_ms else "false",
        ]


@dataclass(frozen=True)
class Bounds:
    """Where reading starts and stops, both included; None is open."""

    low: int | None = None
    high: int | None = None


def bounds_of(filters: list[Filter], column: str, read: Callable[[str], int]) -> Bounds:
    low: int | None = None
    high: int | None = None
    for one in filters:
        if one.column != column or not isinstance(one, ScalarFilter):
            continue
        value = read(one.value)
        if one.op in {"gt", "gte", "eq"}:
            start = value + 1 if one.op == "gt" else value
            low = start if low is None else max(low, start)
        if one.op in {"lt", "lte", "eq"}:
            stop = value - 1 if one.op == "lt" else value
            high = stop if high is None else min(high, stop)
    return Bounds(low, high)


def descending(sort: list[Sort], column: str) -> bool:
    """Newest first unless the page asks for the column ascending."""
    for one in sort:
        if one.column == column:
            return one.descending
    return True


def _too_deep(request: FetchRequest) -> bool:
    return request.offset + request.limit > DEPTH_CEILING


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
                if raw and _int(raw[0]) is not None
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
            Candle(raw[0], raw) for raw in answer if raw and _int(raw[0]) is not None
        ]
        found.extend(batch)
        if len(batch) < int(params["limit"]):
            break
        cursor = batch[-1].open_ms + 1
    return found


def checked_candles(filters: list[Filter], sort: list[Sort]) -> None:
    _checked(filters, CANDLE_COLUMNS)
    _sorts_checked(sort, CANDLE_COLUMNS)


async def candles_page(
    session: BinanceSession, place: Place, request: FetchRequest, now_ms: int
) -> FetchResult:
    checked_candles(request.filters, request.sort)
    if _too_deep(request):
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
    rows = [candle.row(now_ms) for candle in candles]
    return _paged(CANDLE_COLUMNS, rows, request, None)


# --- trades ------------------------------------------------------------------

TRADE_COLUMNS = [
    _column("id", "number", ["eq", *_RANGE_OPS], sql="bigint", sortable=True),
    _column("price", "number"),
    _column("quantity", "number"),
    _column("first_trade_id", "number", sql="bigint"),
    _column("last_trade_id", "number", sql="bigint"),
    _column("time", "datetime", _RANGE_OPS),
    _column("buyer_is_maker", "boolean"),
]


def trade_row(item: dict[str, Any]) -> list[str | None]:
    return [
        str(item["a"]),
        decimal_text(item.get("p")),
        decimal_text(item.get("q")),
        None if _int(item.get("f")) is None else str(item["f"]),
        None if _int(item.get("l")) is None else str(item["l"]),
        moment(_int(item.get("T"))),
        _bool(item.get("m")),
    ]


def _trades(answer: Any) -> list[dict[str, Any]]:
    return [
        one
        for one in answer
        if isinstance(one, dict) and _int(one.get("a")) is not None
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
    ids = bounds_of(filters, "id", lambda text: _whole_number("id", text))
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
    session: BinanceSession, place: Place, request: FetchRequest
) -> FetchResult:
    _checked(request.filters, TRADE_COLUMNS)
    _sorts_checked(request.sort, TRADE_COLUMNS)
    if _too_deep(request):
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
        return _paged(TRADE_COLUMNS, [], request, None)
    bounds = await trade_bounds(session, market, symbol, request.filters, node_id)
    top = newest if bounds.high is None else min(newest, bounds.high)
    bottom = bounds.low
    if descending(request.sort, "id"):
        last = top - request.offset
        first = last - request.limit + 1
        if bottom is not None:
            first = max(first, bottom)
        if last < first:
            return _paged(TRADE_COLUMNS, [], request, None)
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
            return _paged(TRADE_COLUMNS, [], request, None)
        trades = await read_trades(session, market, symbol, first, last, node_id)
        rows = [trade_row(one) for one in trades]
        has_more = last < top
    return FetchResult(
        columns=TRADE_COLUMNS,
        rows=rows,
        has_more=has_more,
        page_commands=["download", "chart", "share"],
    )


# --- the order book ---------------------------------------------------------

BOOK_COLUMNS = [
    _column("side", "string", ["eq"]),
    _column("level", "number", ["lt", "lte"], sql="integer"),
    _column("price", "number"),
    _column("quantity", "number"),
    _column("cumulative_quantity", "number"),
]


def book_rows(answer: dict[str, Any], levels: int) -> list[list[str | None]]:
    rows: list[list[str | None]] = []
    for side, key in (("bid", "bids"), ("ask", "asks")):
        total = Decimal(0)
        for level, entry in enumerate(answer.get(key) or [], start=1):
            if level > levels:
                break
            price, quantity = decimal_text(entry[0]), decimal_text(entry[1])
            if quantity is not None:
                total += Decimal(quantity)
            rows.append([side, str(level), price, quantity, str(total)])
    return rows


async def book_page(
    session: BinanceSession, place: Place, request: FetchRequest
) -> FetchResult:
    _checked(request.filters, BOOK_COLUMNS)
    _sorts_checked(request.sort, BOOK_COLUMNS)
    assert place.symbol is not None
    levels = DEFAULT_BOOK_LEVELS
    sides = {"bid", "ask"}
    for one in request.filters:
        if not isinstance(one, ScalarFilter):
            continue
        if one.column == "level":
            wanted = _whole_number("level", one.value) - (1 if one.op == "lt" else 0)
            levels = max(1, wanted)
        if one.column == "side":
            sides &= {one.value.casefold()}
    market = place.market
    levels = min(levels, market.depths[-1])
    params = {"symbol": place.symbol, "limit": str(market.depth_for(levels))}
    answer = await session.get(market, "depth", params, request.node_id)
    rows = [row for row in book_rows(answer, levels) if row[0] in sides]
    # The book changes many times a second; a page of it is a moment.
    return _paged(BOOK_COLUMNS, rows, request, 5)


# --- the lists ------------------------------------------------------------------


async def ticker_rows(
    session: BinanceSession, market: Market
) -> list[list[str | None]]:
    trading = {one.name for one in await session.symbols(market)}
    return [
        ticker_row(item)
        for item in await session.tickers(market)
        if item.get("symbol") in trading
    ]


async def tickers_page(
    session: BinanceSession, place: Place, request: FetchRequest
) -> FetchResult:
    sort = request.sort or [Sort(column="quote_volume", descending=True)]
    rows = listed_page(
        TICKER_COLUMNS, await ticker_rows(session, place.market), request.filters, sort
    )
    return _paged(TICKER_COLUMNS, rows, request, 10)


async def symbol_rows(
    session: BinanceSession, market: Market
) -> list[list[str | None]]:
    return [symbol_row(market, one) for one in await session.symbols(market)]


async def symbols_page(
    session: BinanceSession, place: Place, request: FetchRequest
) -> FetchResult:
    columns = symbol_columns(place.market)
    sort = request.sort or [Sort(column="symbol")]
    rows = listed_page(
        columns, await symbol_rows(session, place.market), request.filters, sort
    )
    return _paged(columns, rows, request, None)
