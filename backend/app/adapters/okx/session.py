"""How this application talks to OKX's v5 REST, and nothing about what for (D432).

The client and the lists are kept the shared way (D425). OKX limits each
path on its own — so many requests in two seconds from an address, the
instrument list for each instrument type — and sends no count, so a budget
is kept here for each path, its windows two seconds from their start and its
share 40%, so two windows side by side never pass 80% of any rolling two
seconds. A request over that waits for the next window rather than failing:
the windows are short and a page of candles may take several requests. OKX
answers HTTP 200 with a `code` for most refusals. Nothing is retried by
itself.
"""

import base64
import hashlib
import hmac
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

import httpx

from app.adapters.market import session as shared
from app.adapters.market.budget import Budget
from app.adapters.market.keys import key_of
from app.adapters.market.session import (
    Kept,
    MarketSession,
    MarketState,
    StaleTimestamp,
    Words,
)
from app.adapters.market.shape import Symbol
from app.adapters.market.values import decimal_text, milliseconds
from app.adapters.okx.markets import BY_KEY, HOSTS, MARKETS, Market
from app.adapters.okx.options import HOSTS_OF, OkxKeyed, OkxOptions
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.resources import Pooling
from app.core.translation import N_, say

logger = logging.getLogger(__name__)

TIME = "/api/v5/public/time"
INSTRUMENTS = "/api/v5/public/instruments"
STATUS = "/api/v5/system/status"
TICKERS = "/api/v5/market/tickers"
TICKER = "/api/v5/market/ticker"
BOOKS = "/api/v5/market/books"
CANDLES = "/api/v5/market/history-candles"
TRADES = "/api/v5/market/history-trades"

WINDOW_SECONDS = 2
SHARE = 0.4
# OKX's published limit of each path, in requests a window of its own:
# public paths by the address, a key's by its account.
LIMITS: dict[str, tuple[int, int]] = {
    TIME: (10, 2),
    INSTRUMENTS: (20, 2),
    STATUS: (1, 5),
    TICKERS: (20, 2),
    TICKER: (20, 2),
    BOOKS: (40, 2),
    CANDLES: (20, 2),
    TRADES: (20, 2),
    "/api/v5/account/config": (5, 2),
    "/api/v5/account/balance": (10, 2),
    "/api/v5/account/positions": (10, 2),
    "/api/v5/trade/orders-pending": (60, 2),
    "/api/v5/trade/orders-history": (40, 2),
    "/api/v5/trade/fills": (60, 2),
    "/api/v5/asset/deposit-history": (6, 1),
    "/api/v5/asset/withdrawal-history": (6, 1),
}
# A path OKX has not said a limit for is held to the strictest.
FALLBACK_LIMIT = (5, 2)

# A parameter OKX refuses, or an instrument it does not have: the symbols
# sent are the list's, so on a symbol this is one gone since it was read.
NO_INSTRUMENT = "51001"
PARAMETER_ERROR = "51000"
TOO_MANY = {"50011", "50013", "50040"}
NOT_ANSWERING = {"50001", "50004", "50026"}
# OKX does not serve this address or its region.
NOT_SERVED = {"50121", "51155"}
# A signed request's time was outside the thirty seconds OKX accepts.
STALE_TIMESTAMP = "50102"
# The key frozen, of another environment, a header missing or wrong, the
# address not the key's, the key unknown or without the permission.
REFUSED_KEY = {
    "50100",
    "50101",
    "50103",
    "50104",
    "50105",
    "50106",
    "50107",
    "50110",
    "50111",
    "50112",
    "50113",
    "50114",
    "50119",
    "50120",
}

WORDS = Words(
    held=N_("OKX refuses requests from this address for {seconds} s more"),
    spent=N_("OKX's rate limit is nearly spent; try again in {seconds} s"),
    timeout=N_("OKX did not answer in time"),
    unreachable=N_("Could not reach OKX"),
    clock=N_("OKX's clock and this server's differ too much"),
)
REFUSED_KEY_WORDS = N_(
    "OKX does not accept this API key here: check the key, its passphrase, "
    "its permissions and the addresses it is limited to"
)


@dataclass(frozen=True)
class OkxSymbol(Symbol):
    """A symbol, with what OKX says a contract of it is."""

    inst_type: str = "SPOT"
    # What one contract is worth, in `contract_currency`; none on spot.
    contract_value: str | None = None


def make_client() -> httpx.AsyncClient:
    return shared.make_client()


def budget_key(path: str, params: dict[str, str]) -> str:
    """What a path's budget is kept under: the instrument list's by type too."""
    if path == INSTRUMENTS:
        return f"{path}?{params.get('instType', '')}"
    return path


def contracts_worth(contracts: Any, value: str | None) -> str | None:
    """A count of contracts as what they are worth: exact, never a float."""
    text = decimal_text(contracts)
    if text is None or value is None:
        return None
    try:
        return str(Decimal(text) * Decimal(value))
    except InvalidOperation:
        return None


class OkxSession(MarketSession[Market]):
    name = "okx"
    words = WORDS
    ping_path = TIME
    clock_path = TIME
    paces = True

    def __init__(self, options: OkxOptions, pooling: Pooling | None) -> None:
        super().__init__(pooling)
        self._options = options

    @property
    def options(self) -> OkxOptions:
        return self._options

    @property
    def endpoint(self) -> str:
        return self._options.endpoint

    @property
    def hosts(self) -> str:
        """The set of hosts the endpoint speaks to, a key or not."""
        return HOSTS_OF[self._options.endpoint]

    @property
    def keyed(self) -> bool:
        return key_of(self._options) is not None

    @property
    def markets(self) -> Sequence[Market]:
        return [BY_KEY[key] for key in MARKETS]

    def kept_key(self) -> str:
        return self._options.endpoint

    def new_kept(self) -> Kept:
        # Each market keeps its lists; the budgets are the paths'.
        return Kept(make_client(), {key: MarketState(limit=0) for key in MARKETS})

    def budget(
        self, kept: Kept, market: Market, path: str, params: dict[str, str]
    ) -> Budget:
        del market
        key = budget_key(path, params)
        found = kept.budgets.get(key)
        if found is None:
            limit, window = LIMITS.get(path, FALLBACK_LIMIT)
            found = Budget(limit=limit, window_seconds=window, share=SHARE)
            # A limit of a request or two a window would leave nothing.
            if found.ceiling < 1:
                found.share = 1.0
            kept.budgets[key] = found
        return found

    def headers(self) -> dict[str, str]:
        return {"x-simulated-trading": "1"} if self.hosts == "demo" else {}

    def url(self, market: Market, path: str) -> str:
        del market
        return HOSTS[self.hosts] + path

    def signed_request(
        self, state: MarketState, path: str, params: dict[str, str]
    ) -> tuple[str, dict[str, str]]:
        """The query as sent, and the headers that sign it.

        OKX signs the time, the method, the path with its query and the body,
        one after another, with HMAC-SHA256 of the secret, in Base64; the
        time is ISO 8601 to the millisecond in UTC.
        """
        key = key_of(self._options)
        if not isinstance(key, OkxKeyed):
            raise ValueError(say("This connection has no API key"))
        query = urlencode(params)
        at = datetime.fromtimestamp(
            (time.time() * 1000 + state.offset_ms) / 1000, tz=UTC
        )
        stamp = at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        target = f"{path}?{query}" if query else path
        signature = base64.b64encode(
            hmac.new(
                key.api_secret.get_secret_value().encode(),
                f"{stamp}GET{target}".encode(),
                hashlib.sha256,
            ).digest()
        ).decode()
        return query, {
            "OK-ACCESS-KEY": key.api_key.get_secret_value(),
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": stamp,
            "OK-ACCESS-PASSPHRASE": key.api_passphrase.get_secret_value(),
        }

    def answer(self, response: httpx.Response, budget: Budget, node_id: str) -> Any:
        status = response.status_code
        try:
            body = response.json()
        except ValueError:
            body = None
        code = str(body.get("code")) if isinstance(body, dict) else None
        if status == 429 or code in TOO_MANY:
            budget.hold(time.time() + budget.window_seconds)
            raise AdapterError(
                "unknown", say(WORDS.held, seconds=budget.window_seconds)
            )
        if status == 403 or code in NOT_SERVED:
            raise AdapterError(
                "config",
                say(
                    "OKX does not serve this address or region; choose another endpoint"
                ),
            )
        if code == STALE_TIMESTAMP:
            raise StaleTimestamp()
        if status == 401 or code in REFUSED_KEY:
            raise AdapterError("auth", say(REFUSED_KEY_WORDS))
        if status >= 500 or code in NOT_ANSWERING or not isinstance(body, dict):
            raise AdapterError("network", say("OKX is not answering"))
        if code == "0":
            return body.get("data") or []
        if code in {NO_INSTRUMENT, PARAMETER_ERROR} and node_id:
            raise NodeNotFound(node_id)
        logger.warning("OKX refused a request: %s, code %s", status, code)
        raise AdapterError(
            "unknown", say("OKX refused the request (code {code})", code=code or status)
        )

    async def read_symbols(self, kept: Kept, market: Market) -> list[Symbol]:
        """The market's live instruments, a type at a time; OKX answers each
        type whole."""
        found: list[Symbol] = []
        for inst_type in market.inst_types:
            params = {"instType": inst_type}
            answer = await self._get(kept, market, INSTRUMENTS, params, "")
            found += symbols_of(market, answer)
        return found

    async def read_tickers(self, kept: Kept, market: Market) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for inst_type in market.inst_types:
            answer = await self._get(kept, market, TICKERS, {"instType": inst_type}, "")
            found += [one for one in answer if isinstance(one, dict)]
        return found

    def server_ms_of(self, answer: Any) -> int | None:
        first = answer[0] if isinstance(answer, list) and answer else None
        return milliseconds(first.get("ts")) if isinstance(first, dict) else None

    async def system_status(self) -> str | None:
        """Maintenance when OKX says trading or its sockets are stopped now."""
        answer = await self.get(self.markets[0], STATUS, {})
        stopped = any(
            isinstance(one, dict)
            and one.get("state") == "ongoing"
            and one.get("serviceType") in {"0", "5"}
            for one in answer or []
        )
        return "maintenance" if stopped else "normal"

    async def instrument(self, market: Market, name: str, node_id: str) -> OkxSymbol:
        """A symbol named by a client, with its contract, or not at all."""
        found = await self.symbol(market, name, node_id)
        assert isinstance(found, OkxSymbol)
        return found


def _halves(family: Any) -> tuple[str, str]:
    """An instrument family's base and quote: `BTC-USDT` is BTC and USDT."""
    parts = str(family or "").split("-")
    return (parts[0], parts[1]) if len(parts) >= 2 else ("", "")


def _whole(text: str | None) -> int | None:
    try:
        value = Decimal(text) if text is not None else None
    except InvalidOperation:
        return None
    return int(value) if value is not None and value == value.to_integral() else None


def symbols_of(market: Market, answer: Any) -> list[Symbol]:
    """An instrument list reduced to the market's live symbols.

    A contract's quantity step is in contracts; on linear it is said in the
    base coin, as a contract is a fixed part of one, and on inverse in
    contracts, with what one is worth beside it (D433).
    """
    found: list[Symbol] = []
    wanted = (
        "" if not market.futures else ("inverse" if market.in_contracts else "linear")
    )
    for item in answer if isinstance(answer, list) else []:
        if not isinstance(item, dict) or item.get("state") != "live":
            continue
        name = item.get("instId")
        if not isinstance(name, str) or ":" in name or not name:
            continue
        if str(item.get("ctType") or "") != wanted:
            continue
        inst_type = str(item.get("instType") or "")
        value = decimal_text(item.get("ctVal")) if market.futures else None
        lot = decimal_text(item.get("lotSz"))
        if market.futures:
            base, quote = _halves(item.get("instFamily") or item.get("uly"))
        else:
            base, quote = (
                str(item.get("baseCcy") or ""),
                str(item.get("quoteCcy") or ""),
            )
        found.append(
            OkxSymbol(
                name=name,
                base=base,
                quote=quote,
                status="live",
                contract_type=inst_type if market.futures else None,
                delivery_ms=milliseconds(item.get("expTime")),
                onboard_ms=milliseconds(item.get("listTime")),
                price_step=decimal_text(item.get("tickSz")),
                quantity_step=(
                    contracts_worth(lot, value)
                    if market.futures and not market.in_contracts
                    else lot
                ),
                contract_size=_whole(value) if market.in_contracts else None,
                inst_type=inst_type,
                contract_value=value,
            )
        )
    return found
