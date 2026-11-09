"""What a key reads of its account, as read-only rows (D322).

Every list here is short or is cut by Binance itself — balances, positions,
open orders, the newest thousand orders or trades of a symbol, ninety days
of deposits and withdrawals — so each is read whole and sorted and filtered
here, by any column, as the market's lists are. Nothing is sent that would
change anything: every path is a read.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.adapters.binance.catalog import Place
from app.adapters.binance.feeds import (
    boolean_of,
    contract_size_of,
    in_quote,
    listed_column,
    listed_page,
    moment,
    paged,
    whole_of,
)
from app.adapters.binance.markets import SPOT, Market
from app.adapters.binance.session import BinanceSession, decimal_text
from app.adapters.catalog import FeedName
from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult, Sort
from app.core.translation import N_, say

# How many orders or own trades of a symbol a page holds: one request's worth.
LISTED = "1000"

DEPOSIT = "/sapi/v1/capital/deposit/hisrec"
WITHDRAWAL = "/sapi/v1/capital/withdraw/history"
RESTRICTIONS = "/sapi/v1/account/apiRestrictions"

# Binance's numbers for where a transfer stands, in its own words.
DEPOSIT_STATUS = {
    0: "pending",
    1: "success",
    2: "rejected",
    6: "credited",
    7: "wrong deposit",
    8: "waiting for confirmation",
}
WITHDRAWAL_STATUS = {
    0: "email sent",
    1: "cancelled",
    2: "awaiting approval",
    3: "rejected",
    4: "processing",
    5: "failure",
    6: "completed",
}

SPOT_BALANCE_COLUMNS = [
    listed_column("asset", "string"),
    listed_column("free", "number"),
    listed_column("locked", "number"),
    listed_column("total", "number"),
]

FUTURES_BALANCE_COLUMNS = [
    listed_column("asset", "string"),
    listed_column("wallet_balance", "number"),
    listed_column("unrealized_pnl", "number"),
    listed_column("margin_balance", "number"),
    listed_column("available_balance", "number"),
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

ORDER_COLUMNS = [
    listed_column("order_id", "number"),
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
    listed_column("id", "number"),
    listed_column("order_id", "number"),
    listed_column("side", "string"),
    listed_column("price", "number"),
    listed_column("quantity", "number"),
    listed_column("quote_quantity", "number", nullable=True),
    listed_column("commission", "number"),
    listed_column("commission_asset", "string"),
    listed_column("realized_pnl", "number", nullable=True),
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


def account_feeds(market: Market, main_hosts: bool) -> list[FeedName]:
    """What a market's Account holds: no positions on spot, and the wallet's
    transfers on spot of the main hosts only, the testnet having none."""
    found: list[FeedName] = ["balances"]
    if market.positions_path is not None:
        found.append("positions")
    found.append("open_orders")
    if market.key == SPOT.key and main_hosts:
        found += ["deposits", "withdrawals"]
    return found


def _text(value: Any) -> str | None:
    return None if value is None or value == "" else str(value)


def _id(value: Any) -> str | None:
    whole = whole_of(value)
    return None if whole is None else str(whole)


def _side(value: Any) -> str | None:
    return value.casefold() if isinstance(value, str) else None


def _nonzero(*texts: str | None) -> bool:
    return any(text is not None and Decimal(text) != 0 for text in texts)


def _binance_time(text: Any) -> str | None:
    """A withdrawal's time, which Binance writes as UTC text, not milliseconds."""
    if not isinstance(text, str) or text == "":
        return None
    try:
        at = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None
    return moment(int(at.timestamp() * 1000))


# --- rows ---------------------------------------------------------------------


def spot_balance_rows(answer: Any) -> list[list[str | None]]:
    rows: list[list[str | None]] = []
    for one in answer.get("balances") or [] if isinstance(answer, dict) else []:
        free, locked = decimal_text(one.get("free")), decimal_text(one.get("locked"))
        if not _nonzero(free, locked):
            continue
        total = str(Decimal(free or "0") + Decimal(locked or "0"))
        rows.append([_text(one.get("asset")), free, locked, total])
    return rows


def futures_balance_rows(answer: Any) -> list[list[str | None]]:
    rows: list[list[str | None]] = []
    for one in answer.get("assets") or [] if isinstance(answer, dict) else []:
        row = [
            _text(one.get("asset")),
            decimal_text(one.get("walletBalance")),
            decimal_text(one.get("unrealizedProfit")),
            decimal_text(one.get("marginBalance")),
            decimal_text(one.get("availableBalance")),
        ]
        if _nonzero(row[1], row[3]):
            rows.append(row)
    return rows


def position_rows(answer: Any) -> list[list[str | None]]:
    rows: list[list[str | None]] = []
    for one in answer if isinstance(answer, list) else []:
        amount = decimal_text(one.get("positionAmt"))
        if not _nonzero(amount):
            continue
        liquidation = decimal_text(one.get("liquidationPrice"))
        rows.append(
            [
                _text(one.get("symbol")),
                _side(one.get("positionSide")),
                amount,
                decimal_text(one.get("entryPrice")),
                decimal_text(one.get("markPrice")),
                decimal_text(one.get("unRealizedProfit")),
                None if liquidation in {None, "0"} else liquidation,
                decimal_text(one.get("notional") or one.get("notionalValue")),
                moment(whole_of(one.get("updateTime"))),
            ]
        )
    return rows


def order_row(one: dict[str, Any]) -> list[str | None]:
    stop = decimal_text(one.get("stopPrice"))
    average = decimal_text(one.get("avgPrice"))
    return [
        _id(one.get("orderId")),
        _text(one.get("symbol")),
        _side(one.get("side")),
        _side(one.get("type")),
        _side(one.get("status")),
        decimal_text(one.get("price")),
        decimal_text(one.get("origQty")),
        decimal_text(one.get("executedQty")),
        None if average is None or Decimal(average) == 0 else average,
        None if stop is None or Decimal(stop) == 0 else stop,
        _text(one.get("timeInForce")),
        moment(whole_of(one.get("time"))),
        moment(whole_of(one.get("updateTime"))),
    ]


def my_trade_row(one: dict[str, Any], contract_size: int | None) -> list[str | None]:
    """An own trade. Spot says `isBuyer`, futures `buyer` and a `side`; on
    COIN-M the quantity is contracts and their worth is the quote (D321)."""
    buyer = one.get("isBuyer", one.get("buyer"))
    side = _side(one.get("side")) or (
        None if not isinstance(buyer, bool) else ("buy" if buyer else "sell")
    )
    maker = one.get("isMaker", one.get("maker"))
    quote = (
        in_quote(one.get("qty"), contract_size)
        if contract_size is not None
        else decimal_text(one.get("quoteQty"))
    )
    return [
        _id(one.get("id")),
        _id(one.get("orderId")),
        side,
        decimal_text(one.get("price")),
        decimal_text(one.get("qty")),
        quote,
        decimal_text(one.get("commission")),
        _text(one.get("commissionAsset")),
        decimal_text(one.get("realizedPnl")),
        boolean_of(maker),
        moment(whole_of(one.get("time"))),
    ]


def deposit_row(one: dict[str, Any]) -> list[str | None]:
    status = whole_of(one.get("status"))
    return [
        _text(one.get("id")),
        _text(one.get("coin")),
        _text(one.get("network")),
        decimal_text(one.get("amount")),
        DEPOSIT_STATUS.get(status, str(status)) if status is not None else None,
        _text(one.get("txId")),
        _text(one.get("address")),
        moment(whole_of(one.get("insertTime"))),
    ]


def withdrawal_row(one: dict[str, Any]) -> list[str | None]:
    status = whole_of(one.get("status"))
    return [
        _text(one.get("id")),
        _text(one.get("coin")),
        _text(one.get("network")),
        decimal_text(one.get("amount")),
        decimal_text(one.get("transactionFee")),
        WITHDRAWAL_STATUS.get(status, str(status)) if status is not None else None,
        _text(one.get("txId")),
        _text(one.get("address")),
        _binance_time(one.get("applyTime")),
        _binance_time(one.get("completeTime")),
    ]


def _records(answer: Any) -> list[dict[str, Any]]:
    return (
        [one for one in answer if isinstance(one, dict)]
        if isinstance(answer, list)
        else []
    )


# --- pages --------------------------------------------------------------------


def columns_of(market: Market, feed: FeedName) -> list[FetchColumn]:
    if feed == "balances":
        return (
            SPOT_BALANCE_COLUMNS if market.key == SPOT.key else FUTURES_BALANCE_COLUMNS
        )
    return {
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
    "my_trades": Sort(column="id", descending=True),
    "deposits": Sort(column="time", descending=True),
    "withdrawals": Sort(column="apply_time", descending=True),
}


async def account_rows(
    session: BinanceSession, place: Place, node_id: str
) -> list[list[str | None]]:
    """Every row of an account feed, as Binance answers it."""
    market, feed, symbol = place.market, place.feed, place.symbol
    if feed == "balances":
        if market.key == SPOT.key:
            answer = await session.signed(
                market, market.account_path, {"omitZeroBalances": "true"}, node_id
            )
            return spot_balance_rows(answer)
        return futures_balance_rows(
            await session.signed(market, market.account_path, {}, node_id)
        )
    if feed == "positions" and market.positions_path is not None:
        return position_rows(
            await session.signed(market, market.positions_path, {}, node_id)
        )
    if feed == "open_orders":
        answer = await session.signed(market, "openOrders", {}, node_id)
        return [order_row(one) for one in _records(answer)]
    if feed == "orders" and symbol is not None:
        params = {"symbol": symbol, "limit": LISTED}
        answer = await session.signed(market, "allOrders", params, node_id)
        return [order_row(one) for one in _records(answer)]
    if feed == "my_trades" and symbol is not None:
        size = await contract_size_of(session, market, symbol, node_id)
        params = {"symbol": symbol, "limit": LISTED}
        answer = await session.signed(market, market.my_trades_path, params, node_id)
        return [my_trade_row(one, size) for one in _records(answer)]
    if feed == "deposits":
        answer = await session.signed(market, DEPOSIT, {}, node_id)
        return [deposit_row(one) for one in _records(answer)]
    if feed == "withdrawals":
        answer = await session.signed(market, WITHDRAWAL, {}, node_id)
        return [withdrawal_row(one) for one in _records(answer)]
    raise ValueError(say("This node is not read as rows"))


async def account_page(
    session: BinanceSession, place: Place, request: FetchRequest
) -> FetchResult:
    assert place.feed is not None
    columns = columns_of(place.market, place.feed)
    sort = request.sort or [_FIRST[place.feed]]
    rows = listed_page(
        columns,
        await account_rows(session, place, request.node_id),
        request.filters,
        sort,
    )
    return paged(columns, rows, request, None)


# --- what the key may do --------------------------------------------------------

# Binance's flags for a key, in the order a report says them.
PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("enableReading", N_("read")),
    ("enableSpotAndMarginTrading", N_("trade spot and margin")),
    ("enableFutures", N_("trade futures")),
    ("enableMargin", N_("borrow on margin")),
    ("enableVanillaOptions", N_("trade options")),
    ("enableWithdrawals", N_("withdraw")),
    ("enableInternalTransfer", N_("transfer between accounts")),
    ("permitsUniversalTransfer", N_("transfer between wallets")),
)
# Any of these, and the key does more than read.
CHANGING = {
    "enableSpotAndMarginTrading",
    "enableFutures",
    "enableMargin",
    "enableVanillaOptions",
    "enableWithdrawals",
    "enableInternalTransfer",
    "permitsUniversalTransfer",
}


async def restrictions(session: BinanceSession) -> dict[str, Any] | None:
    """What Binance says the key may do, or nothing where it cannot be asked.

    The testnet answers no such path: its keys hold money of no worth.
    """
    if not session.main_hosts:
        return None
    answer = await session.signed(SPOT, RESTRICTIONS, {})
    return answer if isinstance(answer, dict) else None


def more_than_reading(answer: dict[str, Any]) -> bool:
    return any(answer.get(flag) is True for flag in CHANGING)
