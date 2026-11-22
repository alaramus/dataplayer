"""What a key reads of its OKX account, as read-only rows (D437).

OKX's trading account holds one balance for every market, so each market's
Account shows the same Balances; positions and open orders are each
market's, read by OKX's instrument types and kept to the market's symbols.
A list is read whole, a page of OKX's `after` at a time up to a ceiling, and
sorted and filtered here, as the market's lists are. Orders are OKX's last
seven days and own trades its last three. A contract's size is said as what
it is worth, as the public feeds say it (D433). Nothing is sent that would
change anything: every path is a read.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from app.adapters.catalog import FeedName
from app.adapters.fetch import FetchColumn, FetchRequest, FetchResult, Sort
from app.adapters.listed import listed_column, listed_page
from app.adapters.market.columns import paged
from app.adapters.market.values import decimal_text, milliseconds, moment
from app.adapters.okx.feeds import OkxPlace
from app.adapters.okx.markets import Market
from app.adapters.okx.session import OkxSession, OkxSymbol, contracts_worth
from app.core.translation import N_, say

CONFIG = "/api/v5/account/config"
BALANCE = "/api/v5/account/balance"
POSITIONS = "/api/v5/account/positions"
OPEN_ORDERS = "/api/v5/trade/orders-pending"
ORDER_HISTORY = "/api/v5/trade/orders-history"
FILLS = "/api/v5/trade/fills"
DEPOSITS = "/api/v5/asset/deposit-history"
WITHDRAWALS = "/api/v5/asset/withdrawal-history"

PAGE = "100"
# Pages of OKX's `after` read for one list at most.
MOST_PAGES = 20
DAY_MS = 86_400_000
# OKX answers own trades of the last three days on `fills`.
FILLS_MS = 3 * DAY_MS

# OKX's numbers for where a deposit or a withdrawal stands, in its words.
DEPOSIT_STATE = {
    "0": "waiting for confirmation",
    "1": "credited",
    "2": "successful",
    "8": "pending: deposits of this coin suspended",
    "11": "matches the address blacklist",
    "12": "account or deposit frozen",
    "13": "sub-account deposit interception",
    "14": "KYC limit",
    "17": "pending response from the Travel Rule vendor",
}
WITHDRAWAL_STATE = {
    "-3": "canceling",
    "-2": "canceled",
    "-1": "failed",
    "0": "waiting withdrawal",
    "1": "broadcasting to the chain",
    "2": "success",
    "7": "approved",
    "10": "waiting transfer",
    "4": "waiting manual review",
    "5": "waiting manual review",
    "6": "waiting manual review",
    "8": "waiting manual review",
    "9": "waiting manual review",
    "12": "waiting manual review",
    "15": "pending transaction validation",
    "16": "delayed up to 24 hours by local laws",
    "17": "pending response from the Travel Rule vendor",
    "19": "insufficient balance in the hot wallet",
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

# OKX's order and trade ids are numbers as text; kept as text, as Bybit's.
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
    listed_column("update_time", "datetime", nullable=True),
]

MY_TRADE_COLUMNS = [
    listed_column("id", "string"),
    listed_column("order_id", "string"),
    listed_column("side", "string"),
    listed_column("price", "number"),
    listed_column("quantity", "number"),
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
]


def account_feeds(market: Market) -> list[FeedName]:
    """The one balance in every market, positions on futures, and the
    funding account's transfers once, on spot."""
    if market.futures:
        return ["balances", "positions", "open_orders"]
    return ["balances", "open_orders", "deposits", "withdrawals"]


def _text(value: Any) -> str | None:
    return None if value is None or value == "" else str(value)


def _word(value: Any) -> str | None:
    return value.replace("_", " ") if isinstance(value, str) and value else None


def _nonzero(*texts: str | None) -> bool:
    for text in texts:
        try:
            if text is not None and Decimal(text) != 0:
                return True
        except InvalidOperation:
            continue
    return False


def _moment(value: Any) -> str | None:
    return moment(milliseconds(value))


def _worth(market: Market, size: Any, symbol: OkxSymbol | None) -> str | None:
    """A size as the feeds say it: the base on spot, a contract's worth else."""
    if not market.futures:
        return decimal_text(size)
    return contracts_worth(size, symbol.contract_value if symbol else None)


# --- rows ---------------------------------------------------------------------


def balance_rows(answer: Any) -> list[list[str | None]]:
    rows: list[list[str | None]] = []
    for account in answer if isinstance(answer, list) else []:
        for one in account.get("details") or [] if isinstance(account, dict) else []:
            if not isinstance(one, dict):
                continue
            row = [
                _text(one.get("ccy")),
                decimal_text(one.get("cashBal")),
                decimal_text(one.get("eq")),
                decimal_text(one.get("frozenBal")),
                decimal_text(one.get("upl")),
                decimal_text(one.get("eqUsd")),
            ]
            if _nonzero(row[1], row[2]):
                rows.append(row)
    return rows


def position_row(
    market: Market, one: dict[str, Any], symbol: OkxSymbol | None
) -> list[str | None] | None:
    size = decimal_text(one.get("pos"))
    if not _nonzero(size):
        return None
    assert size is not None
    side = str(one.get("posSide") or "")
    if side not in {"long", "short"}:
        side = "short" if Decimal(size) < 0 else "long"
    amount = _worth(market, str(abs(Decimal(size))), symbol)
    return [
        _text(one.get("instId")),
        side,
        amount,
        decimal_text(one.get("avgPx")),
        decimal_text(one.get("markPx")),
        decimal_text(one.get("upl")),
        decimal_text(one.get("liqPx")),
        decimal_text(one.get("notionalUsd")),
        _moment(one.get("uTime")),
    ]


def order_row(
    market: Market, one: dict[str, Any], symbol: OkxSymbol | None
) -> list[str | None]:
    """An order. A spot market order may be sized in the quote asset; then
    its quantity is not the base's and is left empty."""
    in_quote = one.get("tgtCcy") == "quote_ccy"
    return [
        _text(one.get("ordId")),
        _text(one.get("instId")),
        _word(one.get("side")),
        _word(one.get("ordType")),
        _word(one.get("state")),
        decimal_text(one.get("px")),
        None if in_quote else _worth(market, one.get("sz"), symbol),
        _worth(market, one.get("accFillSz"), symbol),
        decimal_text(one.get("avgPx")),
        _moment(one.get("cTime")),
        _moment(one.get("uTime")),
    ]


def my_trade_row(
    market: Market, one: dict[str, Any], symbol: OkxSymbol | None
) -> list[str | None]:
    """An own trade; its fee is OKX's, negative when paid."""
    maker = one.get("execType")
    return [
        _text(one.get("tradeId")),
        _text(one.get("ordId")),
        _word(one.get("side")),
        decimal_text(one.get("fillPx")),
        _worth(market, one.get("fillSz"), symbol),
        decimal_text(one.get("fee")),
        _text(one.get("feeCcy")),
        None if maker not in {"M", "T"} else ("true" if maker == "M" else "false"),
        _moment(one.get("fillTime") or one.get("ts")),
    ]


def deposit_row(one: dict[str, Any]) -> list[str | None]:
    state = _text(one.get("state"))
    return [
        _text(one.get("depId")),
        _text(one.get("ccy")),
        _text(one.get("chain")),
        decimal_text(one.get("amt")),
        DEPOSIT_STATE.get(state or "", state),
        _text(one.get("txId")),
        _text(one.get("to")),
        _moment(one.get("ts")),
    ]


def withdrawal_row(one: dict[str, Any]) -> list[str | None]:
    state = _text(one.get("state"))
    return [
        _text(one.get("wdId")),
        _text(one.get("ccy")),
        _text(one.get("chain")),
        decimal_text(one.get("amt")),
        decimal_text(one.get("fee")),
        WITHDRAWAL_STATE.get(state or "", state),
        _text(one.get("txId")),
        _text(one.get("to")),
        _moment(one.get("ts")),
    ]


# --- reading -----------------------------------------------------------------


async def pages(
    session: OkxSession,
    market: Market,
    path: str,
    params: dict[str, str],
    node_id: str,
    cursor_field: str,
    most: int = MOST_PAGES,
) -> list[dict[str, Any]]:
    """Every record of a signed list, newest first, a page of OKX's `after`
    — the last record's id or time — at a time."""
    found: list[dict[str, Any]] = []
    after = ""
    for _ in range(most):
        asked = {**params, "limit": PAGE}
        if after:
            asked["after"] = after
        answer = await session.signed(market, path, asked, node_id)
        batch = [one for one in answer or [] if isinstance(one, dict)]
        found += batch
        if len(batch) < int(PAGE):
            break
        after = str(batch[-1].get(cursor_field) or "")
        if not after:
            break
    return found


async def _symbols(session: OkxSession, market: Market) -> dict[str, OkxSymbol]:
    return {
        one.name: one
        for one in await session.symbols(market)
        if isinstance(one, OkxSymbol)
    }


async def _by_type(
    session: OkxSession,
    market: Market,
    path: str,
    node_id: str,
    cursor_field: str,
    extra: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """A list asked once for each of the market's instrument types, kept to
    the market's own symbols: a linear and an inverse swap share a type."""
    names = await _symbols(session, market)
    found: list[dict[str, Any]] = []
    for inst_type in market.inst_types:
        params = {"instType": inst_type, **(extra or {})}
        found += await pages(session, market, path, params, node_id, cursor_field)
    return [one for one in found if one.get("instId") in names]


async def own_trades(
    session: OkxSession,
    market: Market,
    symbol: OkxSymbol,
    node_id: str,
    params: dict[str, str] | None = None,
    most: int = MOST_PAGES,
) -> list[dict[str, Any]]:
    """The key's trades of a symbol, OKX's last three days unless a time is
    asked; oldest first."""
    asked = {"instType": symbol.inst_type, "instId": symbol.name, **(params or {})}
    found = await pages(session, market, FILLS, asked, node_id, "billId", most=most)
    return sorted(
        found,
        key=lambda one: (
            milliseconds(one.get("fillTime") or one.get("ts")) or 0,
            str(one.get("tradeId")),
        ),
    )


def fill_time(one: dict[str, Any]) -> int:
    return milliseconds(one.get("fillTime") or one.get("ts")) or 0


async def account_rows(
    session: OkxSession, place: OkxPlace, node_id: str
) -> list[list[str | None]]:
    """Every row of an account feed, as OKX answers it."""
    market, feed, name = place.market, place.feed, place.symbol
    if feed == "balances":
        return balance_rows(await session.signed(market, BALANCE, {}, node_id))
    symbols = await _symbols(session, market)
    if feed == "positions" and market.futures:
        found: list[dict[str, Any]] = []
        for inst_type in market.inst_types:
            answer = await session.signed(
                market, POSITIONS, {"instType": inst_type}, node_id
            )
            found += [one for one in answer or [] if isinstance(one, dict)]
        rows = [
            position_row(market, one, symbols.get(str(one.get("instId"))))
            for one in found
            if one.get("instId") in symbols
        ]
        return [row for row in rows if row is not None]
    if feed == "open_orders":
        found = await _by_type(session, market, OPEN_ORDERS, node_id, "ordId")
        return [
            order_row(market, one, symbols.get(str(one.get("instId")))) for one in found
        ]
    if feed in {"orders", "my_trades"} and name is not None:
        symbol = symbols.get(name)
        if symbol is None:
            raise ValueError(say("This node is not read as rows"))
        if feed == "orders":
            params = {"instType": symbol.inst_type, "instId": name}
            found = await pages(
                session, market, ORDER_HISTORY, params, node_id, "ordId"
            )
            return [order_row(market, one, symbol) for one in found]
        return [
            my_trade_row(market, one, symbol)
            for one in await own_trades(session, market, symbol, node_id)
        ]
    if feed == "deposits":
        found = await pages(session, market, DEPOSITS, {}, node_id, "ts")
        return [deposit_row(one) for one in found]
    if feed == "withdrawals":
        found = await pages(session, market, WITHDRAWALS, {}, node_id, "ts")
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
    session: OkxSession, place: OkxPlace, request: FetchRequest
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

# OKX's permissions beside reading, in the order a report says them.
PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("trade", N_("trade")),
    ("withdraw", N_("withdraw")),
)


async def key_info(session: OkxSession) -> dict[str, Any]:
    """What OKX says of the connection's key and account; any key may ask."""
    answer = await session.signed(session.markets[0], CONFIG, {})
    first = answer[0] if isinstance(answer, list) and answer else None
    return first if isinstance(first, dict) else {}


def permissions_of(info: dict[str, Any]) -> set[str]:
    return {one.strip() for one in str(info.get("perm") or "").split(",") if one}


def more_than_reading(info: dict[str, Any]) -> bool:
    """A key that may trade or withdraw may do more than read."""
    return bool(permissions_of(info) - {"read_only"})
