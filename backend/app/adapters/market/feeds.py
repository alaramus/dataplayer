"""The feeds every exchange reads the same way: a list read whole, and the book (D318, D425).

Tickers and Symbols are a whole market read at once, so they sort and filter
here by any column; the book is one request, its depth from the page's
`level` filter and its sides from `side`.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.adapters.fetch import (
    FetchColumn,
    FetchRequest,
    FetchResult,
    ScalarFilter,
    Sort,
)
from app.adapters.listed import checked_filters, checked_sorts, listed_page
from app.adapters.market.catalog import Place
from app.adapters.market.columns import (
    BOOK_COLUMNS,
    DEFAULT_BOOK_LEVELS,
    book_rows,
    paged,
    symbol_columns,
    symbol_row,
)
from app.adapters.market.shape import Market, Symbol
from app.adapters.market.values import whole_number

# The book changes many times a second; a page of it is a moment.
BOOK_REFRESH_SECONDS = 5
TICKERS_REFRESH_SECONDS = 10


def tickers_page(
    columns: list[FetchColumn], rows: list[list[str | None]], request: FetchRequest
) -> FetchResult:
    """Every symbol's day, busiest by quote volume unless sorted otherwise;
    by volume where the exchange gives no quote volume (D433)."""
    busiest = (
        "quote_volume"
        if any(one.name == "quote_volume" for one in columns)
        else "volume"
    )
    sort = request.sort or [Sort(column=busiest, descending=True)]
    found = listed_page(columns, rows, request.filters, sort)
    return paged(columns, found, request, TICKERS_REFRESH_SECONDS)


def symbols_page(
    market: Market,
    symbols: list[Symbol],
    request: FetchRequest,
    left_out: frozenset[str] = frozenset(),
) -> FetchResult:
    """`left_out` names the columns the exchange has no value for (D433)."""
    every = symbol_columns(market)
    kept = [index for index, one in enumerate(every) if one.name not in left_out]
    columns = [every[index] for index in kept]
    sort = request.sort or [Sort(column="symbol")]
    rows = listed_page(
        columns,
        [
            [row[index] for index in kept]
            for row in (symbol_row(market, one) for one in symbols)
        ],
        request.filters,
        sort,
    )
    return paged(columns, rows, request, None)


async def book_page[M: Market](
    place: Place[M],
    request: FetchRequest,
    read: Callable[[M, str, int, str], Awaitable[dict[str, Any]]],
) -> FetchResult:
    """`read` answers the market's book of a symbol to a depth, as `bids` and
    `asks` of a price and a quantity each."""
    checked_filters(request.filters, BOOK_COLUMNS)
    checked_sorts(request.sort, BOOK_COLUMNS)
    assert place.symbol is not None
    levels = DEFAULT_BOOK_LEVELS
    sides = {"bid", "ask"}
    for one in request.filters:
        if not isinstance(one, ScalarFilter):
            continue
        if one.column == "level":
            wanted = whole_number("level", one.value) - (1 if one.op == "lt" else 0)
            levels = max(1, wanted)
        if one.column == "side":
            sides &= {one.value.casefold()}
    market = place.market
    levels = min(levels, market.max_depth)
    answer = await read(market, place.symbol, market.depth_for(levels), request.node_id)
    rows = [row for row in book_rows(answer, levels) if row[0] in sides]
    return paged(BOOK_COLUMNS, rows, request, BOOK_REFRESH_SECONDS)
