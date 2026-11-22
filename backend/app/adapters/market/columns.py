"""The columns of a market's feeds, one meaning whichever exchange fills them (D318, D425).

Every exchange's tickers, symbols, candles, trades and book are told in these
names and types, so a pipeline, a chart or a person reads `quote_volume` the
same way on Binance and on Bybit. An exchange that has no value for a column
leaves the column out with `only`, rather than filling it with nothing.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.adapters.fetch import (
    FetchColumn,
    FetchRequest,
    FetchResult,
    Filter,
    ScalarFilter,
    Sort,
)
from app.adapters.listed import RANGE_OPS, column, listed_column
from app.adapters.market.shape import Market, Symbol
from app.adapters.market.values import decimal_text, moment

# How deep a page may reach into candles or trades, read a request at a time.
DEPTH_CEILING = 10_000
DEFAULT_BOOK_LEVELS = 100

TICKER_COLUMNS = [
    listed_column("symbol", "string"),
    listed_column("last_price", "number"),
    listed_column("price_change", "number"),
    listed_column("price_change_percent", "number"),
    listed_column("weighted_avg_price", "number"),
    listed_column("open_price", "number"),
    listed_column("high_price", "number"),
    listed_column("low_price", "number"),
    listed_column("volume", "number"),
    listed_column("quote_volume", "number"),
    listed_column("trades", "number"),
    listed_column("open_time", "datetime"),
    listed_column("close_time", "datetime"),
]

SPOT_SYMBOL_COLUMNS = [
    listed_column("symbol", "string"),
    listed_column("base", "string"),
    listed_column("quote", "string"),
    listed_column("status", "string"),
    listed_column("price_step", "number", nullable=True),
    listed_column("quantity_step", "number", nullable=True),
    listed_column("min_notional", "number", nullable=True),
]

FUTURES_SYMBOL_COLUMNS = [
    *SPOT_SYMBOL_COLUMNS,
    listed_column("contract_type", "string", nullable=True),
    listed_column("delivery_time", "datetime", nullable=True),
    listed_column("listed_time", "datetime", nullable=True),
]

CONTRACT_SYMBOL_COLUMNS = [
    *FUTURES_SYMBOL_COLUMNS,
    listed_column("contract_size", "number", nullable=True),
]

CANDLE_COLUMNS = [
    column("open_time", "datetime", RANGE_OPS, sortable=True),
    column("close_time", "datetime"),
    column("open", "number"),
    column("high", "number"),
    column("low", "number"),
    column("close", "number"),
    column("volume", "number"),
    column("quote_volume", "number"),
    column("trades", "number", sql="bigint"),
    column("taker_buy_volume", "number"),
    column("taker_buy_quote_volume", "number"),
    column("closed", "boolean"),
]

TRADE_COLUMNS = [
    column("id", "number", ["eq", *RANGE_OPS], sql="bigint", sortable=True),
    column("price", "number"),
    column("quantity", "number"),
    column("first_trade_id", "number", sql="bigint"),
    column("last_trade_id", "number", sql="bigint"),
    column("time", "datetime", RANGE_OPS),
    column("buyer_is_maker", "boolean"),
]

BOOK_COLUMNS = [
    column("side", "string", ["eq"]),
    column("level", "number", ["lt", "lte"], sql="integer"),
    column("price", "number"),
    column("quantity", "number"),
    column("cumulative_quantity", "number"),
]


def only(columns: list[FetchColumn], names: list[str]) -> list[FetchColumn]:
    """The columns an exchange fills, in the shared order."""
    return [one for one in columns if one.name in names]


def names(columns: list[FetchColumn]) -> list[str]:
    return [one.name for one in columns]


# --- symbols ---------------------------------------------------------------------

# Binance dates a perpetual contract's delivery in 2100; it has none.
_NEVER_MS = 4_000_000_000_000


def symbol_columns(market: Market) -> list[FetchColumn]:
    if not market.futures:
        return SPOT_SYMBOL_COLUMNS
    return CONTRACT_SYMBOL_COLUMNS if market.in_contracts else FUTURES_SYMBOL_COLUMNS


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
    if market.futures:
        delivery = one.delivery_ms
        row += [
            one.contract_type,
            moment(delivery if delivery is not None and delivery < _NEVER_MS else None),
            moment(one.onboard_ms),
        ]
    if market.in_contracts:
        row.append(None if one.contract_size is None else str(one.contract_size))
    return row


# --- a page --------------------------------------------------------------------------


def paged(
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


def too_deep(request: FetchRequest) -> bool:
    return request.offset + request.limit > DEPTH_CEILING


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


# --- the book -------------------------------------------------------------------------


def book_rows(answer: dict[str, Any], levels: int) -> list[list[str | None]]:
    """Bids best first, then asks, each with a running total; `answer` holds
    `bids` and `asks` as lists of a price and a quantity."""
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
