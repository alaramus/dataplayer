"""How this application talks to Binance's REST, and nothing about what for (D316).

The client, the budget and the lists are kept the shared way (D425); this
says Binance's hosts, its weights, the header that reports the weight used,
its codes of refusal and how a request of the account is signed (D322).

Binance weighs every request and bans an address that keeps asking past its
limit, so the weight it reports is read from every answer and a request that
would take a market past 80% of its limit is not sent. Nothing is retried by
itself.
"""

import hashlib
import hmac
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.adapters.binance.markets import BY_KEY, HOSTS, MARKETS, Market
from app.adapters.binance.options import HOSTS_OF, BinanceOptions, Hosts
from app.adapters.market import session as shared
from app.adapters.market.budget import CEILING_SHARE, Budget
from app.adapters.market.keys import key_of
from app.adapters.market.session import (
    Kept,
    MarketSession,
    Pinged,
    StaleTimestamp,
    Words,
)
from app.adapters.market.shape import Symbol
from app.adapters.market.values import decimal_text
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.resources import Pooling
from app.core.translation import N_, say

__all__ = [
    "CEILING_SHARE",
    "BinanceKept",
    "BinanceSession",
    "MarketState",
    "Pinged",
    "StaleTimestamp",
    "Symbol",
    "decimal_text",
    "make_client",
    "symbols_of",
]

logger = logging.getLogger(__name__)

UNKNOWN_SYMBOL = -1121
# Futures answer trades of the last two days only.
OUTSIDE_WINDOW = -4166
# A signed request's time was outside the window Binance accepts.
STALE_TIMESTAMP = -1021
# The key is malformed, unknown, not allowed from this address or for this.
REFUSED_KEY = {-2014, -2015, -1022, -2008}
# How long a signed request stays good after the time it carries.
RECV_WINDOW = "10000"

WORDS = Words(
    held=N_("Binance refuses requests from this address for {seconds} s more"),
    spent=N_("Binance's rate limit is nearly spent; try again in {seconds} s"),
    timeout=N_("Binance did not answer in time"),
    unreachable=N_("Could not reach Binance"),
    clock=N_("Binance's clock and this server's differ too much"),
)


@dataclass
class MarketState(shared.MarketState):
    """A market's state, its window a minute: Binance counts weight by the minute."""

    @property
    def minute(self) -> int:
        return self.window

    @minute.setter
    def minute(self, value: int) -> None:
        self.window = value


# Binance's kept state is the shared one; the name stays for what reads it.
BinanceKept = Kept


def make_client() -> httpx.AsyncClient:
    return shared.make_client()


class BinanceSession(MarketSession[Market]):
    name = "binance"
    words = WORDS

    def __init__(self, options: BinanceOptions, pooling: Pooling | None) -> None:
        super().__init__(pooling)
        self._options = options

    @property
    def options(self) -> BinanceOptions:
        return self._options

    @property
    def markets(self) -> Sequence[Market]:
        return [BY_KEY[key] for key in MARKETS]

    def host(self, market: Market) -> str:
        return HOSTS[HOSTS_OF[self._options.endpoint]][market.key]

    @property
    def hosts(self) -> Hosts:
        return HOSTS_OF[self._options.endpoint]

    @property
    def main_hosts(self) -> bool:
        """Whether this is Binance itself rather than its testnet or data host."""
        return HOSTS_OF[self._options.endpoint] == "binance"

    @property
    def keyed(self) -> bool:
        return key_of(self._options) is not None

    def kept_key(self) -> str:
        return self._options.endpoint

    def new_kept(self) -> Kept:
        return Kept(
            make_client(),
            {key: MarketState(limit=BY_KEY[key].weight_limit) for key in MARKETS},
        )

    def url(self, market: Market, path: str) -> str:
        return self.host(market) + market.path(path)

    def weight(self, market: Market, path: str, params: dict[str, str]) -> int:
        return market.weight(path, params)

    def reported_used(self, response: httpx.Response) -> int | None:
        reported = response.headers.get("x-mbx-used-weight-1m")
        return int(reported) if reported is not None and reported.isdigit() else None

    def signed_request(
        self, state: shared.MarketState, path: str, params: dict[str, str]
    ) -> tuple[str, dict[str, str]]:
        """The signed query string, and the header naming the key."""
        del path
        key = key_of(self._options)
        if key is None:
            raise ValueError(say("This connection has no API key"))
        query = urlencode(
            {
                **params,
                "recvWindow": RECV_WINDOW,
                "timestamp": str(int(time.time() * 1000) + state.offset_ms),
            }
        )
        signature = hmac.new(
            key.api_secret.get_secret_value().encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{query}&signature={signature}", {
            "X-MBX-APIKEY": key.api_key.get_secret_value()
        }

    def answer(self, response: httpx.Response, budget: Budget, node_id: str) -> Any:
        if response.status_code == 200:
            return response.json()
        raise self._refusal(response, budget, node_id)

    def _refusal(
        self, response: httpx.Response, budget: Budget, node_id: str
    ) -> Exception:
        status = response.status_code
        if status in {418, 429}:
            retry = response.headers.get("retry-after", "")
            seconds = int(retry) if retry.isdigit() else 60
            budget.hold(time.time() + seconds)
            return AdapterError("unknown", say(WORDS.held, seconds=seconds))
        if status == 451:
            return AdapterError(
                "config",
                say("Binance does not serve this address; choose another endpoint"),
            )
        code = _code_of(response)
        if code == STALE_TIMESTAMP:
            return StaleTimestamp()
        if code in REFUSED_KEY or status == 401:
            return AdapterError(
                "auth",
                say(
                    "Binance does not accept this API key here: check the key, "
                    "its permissions and the addresses it is limited to"
                ),
            )
        if code == UNKNOWN_SYMBOL:
            return NodeNotFound(node_id)
        if code == OUTSIDE_WINDOW:
            return ValueError(
                say("Binance answers futures trades of the last two days only")
            )
        if 400 <= status < 500:
            logger.warning("Binance refused a request: %s, code %s", status, code)
            return AdapterError(
                "unknown",
                say("Binance refused the request (code {code})", code=code or status),
            )
        return AdapterError("network", say("Binance is not answering"))

    async def read_symbols(self, kept: Kept, market: Market) -> list[Symbol]:
        state = kept.markets[market.key]
        params = (
            {"symbolStatus": "TRADING", "showPermissionSets": "false"}
            if market.key == "spot"
            else {}
        )
        info = await self._get(kept, market, "exchangeInfo", params, "")
        for limit in info.get("rateLimits") or []:
            if (
                limit.get("rateLimitType") == "REQUEST_WEIGHT"
                and limit.get("interval") == "MINUTE"
                and limit.get("intervalNum") == 1
                and isinstance(limit.get("limit"), int)
            ):
                state.limit = limit["limit"]
        return symbols_of(info)

    async def read_tickers(self, kept: Kept, market: Market) -> list[dict[str, Any]]:
        answer = await self._get(kept, market, "ticker/24hr", {}, "")
        return [one for one in answer if isinstance(one, dict)]

    def server_ms_of(self, answer: Any) -> int | None:
        server = answer.get("serverTime") if isinstance(answer, dict) else None
        return server if isinstance(server, int) else None

    async def system_status(self) -> str | None:
        """Binance's own word for its state, or nothing where the host has none.

        Asked of the main host only: the market-data host and the testnet
        answer no such path.
        """
        if HOSTS_OF[self._options.endpoint] != "binance":
            return None
        answer = await self.get(BY_KEY["spot"], "/sapi/v1/system/status", {})
        status = answer.get("status") if isinstance(answer, dict) else None
        return (
            {0: "normal", 1: "maintenance"}.get(status)
            if isinstance(status, int)
            else None
        )


def _code_of(response: httpx.Response) -> int | None:
    try:
        body = response.json()
    except ValueError:
        return None
    code = body.get("code") if isinstance(body, dict) else None
    return code if isinstance(code, int) else None


def _filter(filters: list[dict[str, Any]], kind: str, key: str) -> str | None:
    for one in filters:
        if one.get("filterType") == kind:
            return decimal_text(one.get(key))
    return None


def symbols_of(info: dict[str, Any]) -> list[Symbol]:
    """`exchangeInfo` reduced to the symbols that trade."""
    found: list[Symbol] = []
    for item in info.get("symbols") or []:
        status = item.get("status") or item.get("contractStatus")
        name = item.get("symbol")
        if status != "TRADING" or not isinstance(name, str) or ":" in name:
            continue
        filters = item.get("filters") or []
        found.append(
            Symbol(
                name=name,
                base=str(item.get("baseAsset") or ""),
                quote=str(item.get("quoteAsset") or ""),
                status=status,
                contract_type=item.get("contractType") or None,
                delivery_ms=_whole(item.get("deliveryDate")),
                onboard_ms=_whole(item.get("onboardDate")),
                price_step=_filter(filters, "PRICE_FILTER", "tickSize"),
                quantity_step=_filter(filters, "LOT_SIZE", "stepSize"),
                min_notional=(
                    _filter(filters, "NOTIONAL", "minNotional")
                    or _filter(filters, "MIN_NOTIONAL", "minNotional")
                    or _filter(filters, "MIN_NOTIONAL", "notional")
                ),
                contract_size=_whole(item.get("contractSize")),
            )
        )
    return found


def _whole(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
