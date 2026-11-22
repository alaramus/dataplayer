"""What a key reads of its Bybit account, as read-only rows (D431).

Bybit's unified account holds one wallet for every market, so each market's
Account shows the same Balances; positions and open orders are each
market's. A list is read whole, a page of Bybit's cursor at a time up to a
ceiling, and sorted and filtered here, as the market's lists are. Orders and
own trades are Bybit's last seven days, deposits and withdrawals its last
thirty. Nothing is sent that would change anything: every path is a read.
"""

from decimal import Decimal
from typing import Any

from app.adapters.bybit.feeds import BybitPlace, volumes
from app.adapters.bybit.markets import Market
from app.adapters.bybit.session import BybitSession
from app.adapters.catalog import FeedName
from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult, Sort
from app.adapters.listed import listed_column, listed_page
from app.adapters.market.columns import paged
from app.adapters.market.values import boolean_of, decimal_text, milliseconds, moment
from app.core.translation import N_, say

WALLET = "/v5/account/wallet-balance"
POSITIONS = "/v5/position/list"
OPEN_ORDERS = "/v5/order/realtime"
ORDER_HISTORY = "/v5/order/history"
EXECUTIONS = "/v5/execution/list"
DEPOSITS = "/v5/asset/deposit/query-record"
WITHDRAWALS = "/v5/asset/withdraw/query-record"
KEY_INFO = "/v5/user/query-api"

# Linear positions and orders are asked by the coin they settle in.
SETTLE_COINS = ("USDT", "USDC")
# Pages of Bybit's cursor read for one list at most.
MOST_PAGES = 20
# Bybit's largest page for each path.
PAGE_SIZES = {
    POSITIONS: 200,
    OPEN_ORDERS: 50,
    ORDER_HISTORY: 50,
    EXECUTIONS: 100,
    DEPOSITS: 50,
    WITHDRAWALS: 50,
}

# Bybit's numbers for where a deposit stands, in its own words.
DEPOSIT_STATUS = {
    0: "unknown",
    1: "to be confirmed",
    2: "processing",
    3: "success",
    4: "failed",
    7: "rollback processing",
    10011: "pending credit to the funding pool",
    10012: "credited to the funding pool",
    70011: "rolled back",
    70012: "successful after review",
    70013: "rollback failed",
}

BALANCE_COLUMNS = [
    listed_column("asset", "string"),
    listed_column("wallet_balance", "number"),
    listed_column("equity", "number", nullable=True),
    listed_column("locked", "number", nullable=True),
    listed_column("unrealized_pnl", "number", nullable=True),
    listed_column("usd_value", "number", nullable=True),
]

POSITION_COLUMNS = [
    listed_column("symbol", "string"),
    listed_column("side", "string"),
    listed_column("amount", "number"),
    listed_column("entry_price", "number"),
    listed_column("mark_price", "number"),
    listed_column("unrealized_pnl", "number"),
    listed_column("liquidation_price", "number", nullable=True),
    listed_column("notional", "number", nullable=True),
    listed_column("update_time", "datetime", nullable=True),
]

# Bybit's order and trade ids are text, as its public trades' are (D427).
ORDER_COLUMNS = [
    listed_column("order_id", "string"),
    listed_column("symbol", "string"),
    listed_column("side", "string"),
    listed_column("type", "string"),
    listed_column("status", "string"),
    listed_column("price", "number"),
    listed_column("quantity", "number"),
    listed_column("executed", "number"),
    listed_column("average_price", "number", nullable=True),
    listed_column("stop_price", "number", nullable=True),
    listed_column("time_in_force", "string", nullable=True),
    listed_column("time", "datetime"),
    listed_column("update_time", "datetime", nullable=True),
]

MY_TRADE_COLUMNS = [
    listed_column("id", "string"),
    listed_column("order_id", "string"),
    listed_column("side", "string"),
    listed_column("price", "number"),
    listed_column("quantity", "number"),
    listed_column("quote_quantity", "number", nullable=True),
    listed_column("commission", "number"),
    listed_column("commission_asset", "string", nullable=True),
    listed_column("is_maker", "boolean"),
    listed_column("time", "datetime"),
]

DEPOSIT_COLUMNS = [
    listed_column("id", "string"),
    listed_column("coin", "string"),
    listed_column("network", "string"),
    listed_column("amount", "number"),
    listed_column("status", "string"),
    listed_column("tx_id", "string", nullable=True),
    listed_column("address", "string", nullable=True),
    listed_column("time", "datetime"),
]

WITHDRAWAL_COLUMNS = [
    listed_column("id", "string"),
    listed_column("coin", "string"),
    listed_column("network", "string"),
    listed_column("amount", "number"),
    listed_column("fee", "number", nullable=True),
    listed_column("status", "string"),
    listed_column("tx_id", "string", nullable=True),
    listed_column("address", "string", nullable=True),
    listed_column("apply_time", "datetime"),
    listed_column("complete_time", "datetime", nullable=True),
]


def account_feeds(market: Market) -> list[FeedName]:
    """The unified wallet in every market, positions on futures, and the
    wallet's transfers once, on spot."""
    if market.futures:
        return ["balances", "positions", "open_orders"]
    return ["balances", "open_orders", "deposits", "withdrawals"]


def _text(value: Any) -> str | None:
    return None if value is None or value == "" else str(value)


def _word(value: Any) -> str | None:
    return value.casefold() if isinstance(value, str) and value else None


def _nonzero(*texts: str | None) -> bool:
    return any(text is not None and Decimal(text) != 0 for text in texts)


def _positive(text: str | None) -> str | None:
    """A price Bybit writes as 0 or empty where there is none."""
    return None if text is None or Decimal(text) == 0 else text


def _moment(value: Any) -> str | None:
    return moment(milliseconds(value))


# --- rows ---------------------------------------------------------------------


def balance_rows(answer: Any) -> list[list[str | None]]:
    rows: list[list[str | None]] = []
    for account in answer.get("list") or [] if isinstance(answer, dict) else []:
        for one in account.get("coin") or [] if isinstance(account, dict) else []:
            row = [
                _text(one.get("coin")),
                decimal_text(one.get("walletBalance")),
                decimal_text(one.get("equity")),
                decimal_text(one.get("locked")),
                decimal_text(one.get("unrealisedPnl")),
                decimal_text(one.get("usdValue")),
            ]
            if _nonzero(row[1], row[2]):
                rows.append(row)
    return rows


def position_row(one: dict[str, Any]) -> list[str | None] | None:
    amount = decimal_text(one.get("size"))
    if not _nonzero(amount):
        return None
    side = {"Buy": "long", "Sell": "short"}.get(str(one.get("side")))
    return [
        _text(one.get("symbol")),
        side,
        amount,
        decimal_text(one.get("avgPrice")),
        decimal_text(one.get("markPrice")),
        decimal_text(one.get("unrealisedPnl")),
        _positive(decimal_text(one.get("liqPrice"))),
        decimal_text(one.get("positionValue")),
        _moment(one.get("updatedTime")),
    ]


def order_row(one: dict[str, Any]) -> list[str | None]:
    return [
        _text(one.get("orderId")),
        _text(one.get("symbol")),
        _word(one.get("side")),
        _word(one.get("orderType")),
        _word(one.get("orderStatus")),
        decimal_text(one.get("price")),
        decimal_text(one.get("qty")),
        decimal_text(one.get("cumExecQty")),
        _positive(decimal_text(one.get("avgPrice"))),
        _positive(decimal_text(one.get("triggerPrice"))),
        _text(one.get("timeInForce")),
        _moment(one.get("createdTime")),
        _moment(one.get("updatedTime")),
    ]


def my_trade_row(market: Market, one: dict[str, Any]) -> list[str | None]:
    """An own trade. On inverse Bybit's quantity is USD and its value the
    coin, so the two are swapped, as a candle's volumes are (D427)."""
    quantity, quote = volumes(market, one.get("execQty"), one.get("execValue"))
    return [
        _text(one.get("execId")),
        _text(one.get("orderId")),
        _word(one.get("side")),
        decimal_text(one.get("execPrice")),
        quantity,
        quote,
        decimal_text(one.get("execFee")),
        _text(one.get("feeCurrency")),
        boolean_of(one.get("isMaker")),
        _moment(one.get("execTime")),
    ]


def deposit_row(one: dict[str, Any]) -> list[str | None]:
    status = one.get("status")
    number = status if isinstance(status, int) else None
    return [
        _text(one.get("id")),
        _text(one.get("coin")),
        _text(one.get("chain")),
        decimal_text(one.get("amount")),
        DEPOSIT_STATUS.get(number, str(number)) if number is not None else None,
        _text(one.get("txID")),
        _text(one.get("toAddress")),
        _moment(one.get("successAt")),
    ]


def withdrawal_row(one: dict[str, Any]) -> list[str | None]:
    return [
        _text(one.get("withdrawId")),
        _text(one.get("coin")),
        _text(one.get("chain")),
        decimal_text(one.get("amount")),
        decimal_text(one.get("withdrawFee")),
        _text(one.get("status")),
        _text(one.get("txID")),
        _text(one.get("toAddress")),
        _moment(one.get("createTime")),
        _moment(one.get("updateTime")),
    ]


# --- reading -----------------------------------------------------------------


async def pages(
    session: BybitSession,
    market: Market,
    path: str,
    params: dict[str, str],
    node_id: str,
    rows_key: str = "list",
    most: int = MOST_PAGES,
) -> list[dict[str, Any]]:
    """Every record of a signed list, a page of Bybit's cursor at a time."""
    found: list[dict[str, Any]] = []
    cursor = ""
    for _ in range(most):
        asked = {**params, "limit": str(PAGE_SIZES[path])}
        if cursor:
            asked["cursor"] = cursor
        answer = await session.signed(market, path, asked, node_id)
        if not isinstance(answer, dict):
            break
        found += [one for one in answer.get(rows_key) or [] if isinstance(one, dict)]
        cursor = str(answer.get("nextPageCursor") or "")
        if not cursor:
            break
    return found


async def _by_settle_coin(
    session: BybitSession, market: Market, path: str, node_id: str
) -> list[dict[str, Any]]:
    """A linear list asked once for each coin it settles in, as Bybit wants."""
    base: dict[str, str] = {"category": market.key}
    if market.key != "linear":
        return await pages(session, market, path, base, node_id)
    found: list[dict[str, Any]] = []
    for coin in SETTLE_COINS:
        found += await pages(
            session, market, path, {**base, "settleCoin": coin}, node_id
        )
    return found


async def own_trades(
    session: BybitSession,
    market: Market,
    symbol: str,
    node_id: str,
    params: dict[str, str] | None = None,
    most: int = MOST_PAGES,
) -> list[dict[str, Any]]:
    """The key's trades of a symbol, Bybit's last seven days unless a time is
    asked; oldest first."""
    asked = {"category": market.key, "symbol": symbol, **(params or {})}
    found = await pages(session, market, EXECUTIONS, asked, node_id, most=most)
    return sorted(
        found,
        key=lambda one: (
            milliseconds(one.get("execTime")) or 0,
            str(one.get("execId")),
        ),
    )


async def account_rows(
    session: BybitSession, place: BybitPlace, node_id: str
) -> list[list[str | None]]:
    """Every row of an account feed, as Bybit answers it."""
    market, feed, symbol = place.market, place.feed, place.symbol
    if feed == "balances":
        answer = await session.signed(
            market, WALLET, {"accountType": "UNIFIED"}, node_id
        )
        return balance_rows(answer)
    if feed == "positions" and market.futures:
        found = await _by_settle_coin(session, market, POSITIONS, node_id)
        return [row for row in map(position_row, found) if row is not None]
    if feed == "open_orders":
        found = await _by_settle_coin(session, market, OPEN_ORDERS, node_id)
        return [order_row(one) for one in found]
    if feed == "orders" and symbol is not None:
        params = {"category": market.key, "symbol": symbol}
        found = await pages(session, market, ORDER_HISTORY, params, node_id)
        return [order_row(one) for one in found]
    if feed == "my_trades" and symbol is not None:
        found = await own_trades(session, market, symbol, node_id)
        return [my_trade_row(market, one) for one in found]
    if feed == "deposits":
        found = await pages(session, market, DEPOSITS, {}, node_id, rows_key="rows")
        return [deposit_row(one) for one in found]
    if feed == "withdrawals":
        found = await pages(session, market, WITHDRAWALS, {}, node_id, rows_key="rows")
        return [withdrawal_row(one) for one in found]
    raise ValueError(say("This node is not read as rows"))


def columns_of(feed: FeedName) -> list[FetchColumn]:
    return {
        "balances": BALANCE_COLUMNS,
        "positions": POSITION_COLUMNS,
        "open_orders": ORDER_COLUMNS,
        "orders": ORDER_COLUMNS,
        "my_trades": MY_TRADE_COLUMNS,
        "deposits": DEPOSIT_COLUMNS,
        "withdrawals": WITHDRAWAL_COLUMNS,
    }[feed]


_FIRST: dict[FeedName, Sort] = {
    "balances": Sort(column="asset"),
    "positions": Sort(column="symbol"),
    "open_orders": Sort(column="time", descending=True),
    "orders": Sort(column="time", descending=True),
    "my_trades": Sort(column="time", descending=True),
    "deposits": Sort(column="time", descending=True),
    "withdrawals": Sort(column="apply_time", descending=True),
}


async def account_page(
    session: BybitSession, place: BybitPlace, request: FetchRequest
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

# Bybit's groups of permissions, in the order a report says them.
PERMISSION_GROUPS: tuple[tuple[str, str], ...] = (
    ("ContractTrade", N_("trade contracts")),
    ("Spot", N_("trade spot")),
    ("Derivatives", N_("trade derivatives")),
    ("Options", N_("trade options")),
    ("Wallet", N_("move money between wallets or out")),
    ("Exchange", N_("convert coins")),
    ("Earn", N_("use Earn")),
)


async def key_info(session: BybitSession) -> dict[str, Any]:
    """What Bybit says of the connection's key; any key may ask."""
    answer = await session.signed(session.markets[0], KEY_INFO, {})
    return answer if isinstance(answer, dict) else {}


def more_than_reading(info: dict[str, Any]) -> bool:
    """A key that is not read-only may trade or move money."""
    return info.get("readOnly") != 1


def granted(info: dict[str, Any], group: str) -> bool:
    permissions = info.get("permissions")
    rights = permissions.get(group) if isinstance(permissions, dict) else None
    return bool(rights) and isinstance(rights, list)
