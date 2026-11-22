"""What a CDP key reads of its Coinbase account, as read-only rows (D443).

Advanced Trade answers the owner's Coinbase account: its balances, its
orders and its fills, a page of Coinbase's cursor at a time up to a ceiling,
sorted and filtered here as the market's lists are. Nothing is sent that
would change anything: every path is a read.
"""

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.adapters.catalog import FeedName
from app.adapters.coinbase.markets import Market
from app.adapters.coinbase.session import BROKERAGE, CoinbaseSession
from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult, Sort
from app.adapters.listed import listed_column, listed_page
from app.adapters.market.catalog import Place
from app.adapters.market.columns import paged
from app.adapters.market.values import decimal_text, moment
from app.core.translation import N_, say

ACCOUNTS = f"{BROKERAGE}/accounts"
ORDERS = f"{BROKERAGE}/orders/historical/batch"
FILLS = f"{BROKERAGE}/orders/historical/fills"
KEY_PERMISSIONS = f"{BROKERAGE}/key_permissions"

# Coinbase's largest page of accounts; orders and fills state none, so the
# fills' default is asked of both.
ACCOUNTS_PAGE = "250"
PAGE = "100"
# Pages of Coinbase's cursor read for one list at most.
MOST_PAGES = 20

BALANCE_COLUMNS = [
    listed_column("asset", "string"),
    listed_column("wallet_balance", "number"),
    listed_column("available", "number"),
    listed_column("locked", "number"),
]

# Coinbase's ids are text, as Bybit's and OKX's are (D427).
ORDER_COLUMNS = [
    listed_column("order_id", "string"),
    listed_column("symbol", "string"),
    listed_column("side", "string"),
    listed_column("type", "string"),
    listed_column("status", "string"),
    listed_column("price", "number", nullable=True),
    listed_column("quantity", "number", nullable=True),
    listed_column("executed", "number"),
    listed_column("average_price", "number", nullable=True),
    listed_column("time", "datetime"),
]

MY_TRADE_COLUMNS = [
    listed_column("id", "string"),
    listed_column("order_id", "string"),
    listed_column("side", "string"),
    listed_column("price", "number"),
    listed_column("quantity", "number", nullable=True),
    listed_column("quote_quantity", "number", nullable=True),
    listed_column("commission", "number"),
    listed_column("is_maker", "boolean"),
    listed_column("time", "datetime"),
]

_FRACTION = re.compile(r"\.(\d{6})\d+")


def account_feeds(market: Market) -> list[FeedName]:
    del market
    return ["balances", "open_orders"]


def rfc3339_ms(value: Any) -> int | None:
    """Coinbase's RFC 3339 time, to the nanosecond, as milliseconds."""
    if not isinstance(value, str) or not value:
        return None
    text = _FRACTION.sub(r".\1", value.replace("Z", "+00:00"))
    try:
        at = datetime.fromisoformat(text)
    except ValueError:
        return None
    return int(at.astimezone(UTC).timestamp() * 1000)


def rfc3339(milliseconds: int) -> str:
    at = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _amount(value: Any) -> str | None:
    """A `{value, currency}` amount's value."""
    return decimal_text(value.get("value")) if isinstance(value, dict) else None


def _word(value: Any) -> str | None:
    return (
        value.casefold().replace("_", " ") if isinstance(value, str) and value else None
    )


def _text(value: Any) -> str | None:
    return None if value is None or value == "" else str(value)


def _sum(*texts: str | None) -> str | None:
    if any(text is None for text in texts):
        return None
    return str(sum((Decimal(text) for text in texts if text is not None), Decimal(0)))


def _nonzero(text: str | None) -> bool:
    try:
        return text is not None and Decimal(text) != 0
    except InvalidOperation:
        return False


# --- rows ---------------------------------------------------------------------


def balance_rows(accounts: list[dict[str, Any]]) -> list[list[str | None]]:
    """Each currency's account; one holding nothing is left out."""
    rows: list[list[str | None]] = []
    for one in accounts:
        available, hold = (
            _amount(one.get("available_balance")),
            _amount(one.get("hold")),
        )
        total = _sum(available, hold)
        if _nonzero(total):
            rows.append([_text(one.get("currency")), total, available, hold])
    return rows


def _configuration(order: dict[str, Any]) -> dict[str, Any]:
    """The one kind of order configuration an order carries, whatever it is."""
    configuration = order.get("order_configuration")
    for value in (configuration if isinstance(configuration, dict) else {}).values():
        if isinstance(value, dict):
            return value
    return {}


def order_row(order: dict[str, Any]) -> list[str | None]:
    """An order. One sized in the quote asset leaves its quantity empty."""
    shape = _configuration(order)
    return [
        _text(order.get("order_id")),
        _text(order.get("product_id")),
        _word(order.get("side")),
        _word(order.get("order_type")),
        _word(order.get("status")),
        decimal_text(shape.get("limit_price")),
        decimal_text(shape.get("base_size")),
        decimal_text(order.get("filled_size")),
        decimal_text(order.get("average_filled_price"))
        if _nonzero(decimal_text(order.get("average_filled_price")))
        else None,
        moment(rfc3339_ms(order.get("created_time"))),
    ]


def my_trade_row(fill: dict[str, Any]) -> list[str | None]:
    """An own trade; a fill sized in the quote asset says its quote quantity
    and leaves the base's empty, nothing divided."""
    price, size = decimal_text(fill.get("price")), decimal_text(fill.get("size"))
    in_quote = fill.get("size_in_quote") is True
    if in_quote:
        quantity, quote = None, size
    else:
        quantity = size
        quote = (
            None
            if price is None or size is None
            else str(Decimal(price) * Decimal(size))
        )
    maker = fill.get("liquidity_indicator")
    return [
        _text(fill.get("trade_id")),
        _text(fill.get("order_id")),
        _word(fill.get("side")),
        price,
        quantity,
        quote,
        decimal_text(fill.get("commission")),
        None
        if maker not in {"MAKER", "TAKER"}
        else ("true" if maker == "MAKER" else "false"),
        moment(rfc3339_ms(fill.get("trade_time"))),
    ]


# --- reading -----------------------------------------------------------------


async def pages(
    session: CoinbaseSession,
    market: Market,
    path: str,
    params: dict[str, str],
    node_id: str,
    rows_key: str,
    page: str = PAGE,
    most: int = MOST_PAGES,
) -> list[dict[str, Any]]:
    """Every record of a signed list, a page of Coinbase's cursor at a time."""
    found: list[dict[str, Any]] = []
    cursor = ""
    for _ in range(most):
        asked = {**params, "limit": page}
        if cursor:
            asked["cursor"] = cursor
        answer = await session.signed(market, path, asked, node_id)
        if not isinstance(answer, dict):
            break
        found += [one for one in answer.get(rows_key) or [] if isinstance(one, dict)]
        cursor = str(answer.get("cursor") or "")
        if not cursor or answer.get("has_next") is False:
            break
    return found


async def own_trades(
    session: CoinbaseSession,
    market: Market,
    symbol: str,
    node_id: str,
    since_ms: int | None = None,
    before_ms: int | None = None,
) -> list[dict[str, Any]]:
    """The key's fills of a product, oldest first, between two times if asked."""
    params = {"product_ids": symbol}
    if since_ms is not None:
        params["start_sequence_timestamp"] = rfc3339(since_ms)
    if before_ms is not None:
        params["end_sequence_timestamp"] = rfc3339(before_ms)
    found = await pages(session, market, FILLS, params, node_id, "fills")
    return sorted(
        found,
        key=lambda one: (
            rfc3339_ms(one.get("trade_time")) or 0,
            str(one.get("trade_id")),
        ),
    )


def fill_time(fill: dict[str, Any]) -> int:
    return rfc3339_ms(fill.get("trade_time")) or 0


async def account_rows(
    session: CoinbaseSession, place: Place[Market], node_id: str
) -> list[list[str | None]]:
    market, feed, symbol = place.market, place.feed, place.symbol
    if feed == "balances":
        found = await pages(
            session, market, ACCOUNTS, {}, node_id, "accounts", page=ACCOUNTS_PAGE
        )
        return balance_rows(found)
    if feed == "open_orders":
        found = await pages(
            session, market, ORDERS, {"order_status": "OPEN"}, node_id, "orders"
        )
        return [order_row(one) for one in found]
    if feed == "orders" and symbol is not None:
        found = await pages(
            session, market, ORDERS, {"product_ids": symbol}, node_id, "orders"
        )
        return [order_row(one) for one in found]
    if feed == "my_trades" and symbol is not None:
        return [
            my_trade_row(one)
            for one in await own_trades(session, market, symbol, node_id)
        ]
    raise ValueError(say("This node is not read as rows"))


def columns_of(feed: FeedName) -> list[FetchColumn]:
    return {
        "balances": BALANCE_COLUMNS,
        "open_orders": ORDER_COLUMNS,
        "orders": ORDER_COLUMNS,
        "my_trades": MY_TRADE_COLUMNS,
    }[feed]


_FIRST: dict[FeedName, Sort] = {
    "balances": Sort(column="asset"),
    "open_orders": Sort(column="time", descending=True),
    "orders": Sort(column="time", descending=True),
    "my_trades": Sort(column="time", descending=True),
}


async def account_page(
    session: CoinbaseSession, place: Place[Market], request: FetchRequest
) -> FetchResult:
    assert place.feed is not None
    columns = columns_of(place.feed)
    sort = request.sort or [_FIRST[place.feed]]
    rows = listed_page(
        columns,
        await account_rows(session, place, request.node_id),
        request.filters,
        sort,
    )
    return paged(columns, rows, request, None)


# --- what the key may do --------------------------------------------------------

PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("can_view", N_("view")),
    ("can_trade", N_("trade")),
    ("can_transfer", N_("move money in or out")),
)


async def key_info(session: CoinbaseSession) -> dict[str, Any]:
    answer = await session.signed(session.markets[0], KEY_PERMISSIONS, {})
    return answer if isinstance(answer, dict) else {}


def more_than_reading(info: dict[str, Any]) -> bool:
    return info.get("can_trade") is True or info.get("can_transfer") is True
