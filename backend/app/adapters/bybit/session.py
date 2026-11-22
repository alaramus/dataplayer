"""How this application talks to Bybit's v5 REST, and nothing about what for (D426).

The client, the budget and the lists are kept the shared way (D425). Bybit
answers HTTP 200 with a `retCode` for most refusals, sends no count of
requests on public paths, and limits the address as a whole — 600 requests
in five seconds — so the budget is one for every market, counted here, its
windows five seconds from their start and its share 40%: two windows side by
side never pass 80% of any rolling five seconds. Nothing is retried by
itself.
"""

import logging
import time
from collections.abc import Sequence
from typing import Any

import httpx

from app.adapters.bybit.markets import BY_KEY, HOSTS, MARKETS, Market
from app.adapters.bybit.options import BybitOptions
from app.adapters.market import session as shared
from app.adapters.market.budget import Budget
from app.adapters.market.session import Kept, MarketSession, MarketState, Words
from app.adapters.market.shape import Symbol
from app.adapters.market.values import decimal_text, milliseconds
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.resources import Pooling
from app.core.translation import N_, say

logger = logging.getLogger(__name__)

LIMIT = 600
WINDOW_SECONDS = 5
SHARE = 0.4
# An address Bybit bans for asking too much waits at least this long.
BAN_SECONDS = 600
PAGE = "1000"

# A parameter Bybit refuses; the symbols sent are the list's, so on a symbol
# this is one gone since the list was read.
PARAMETER_ERROR = 10001
INVALID_SYMBOL = 10029
TOO_MANY = {10006, 10018}
NOT_SERVED = 10009
SERVER_ERROR = 10016

WORDS = Words(
    held=N_("Bybit refuses requests from this address for {seconds} s more"),
    spent=N_("Bybit's rate limit is nearly spent; try again in {seconds} s"),
    timeout=N_("Bybit did not answer in time"),
    unreachable=N_("Could not reach Bybit"),
)


def make_client() -> httpx.AsyncClient:
    return shared.make_client()


class BybitSession(MarketSession[Market]):
    name = "bybit"
    words = WORDS
    ping_path = "time"

    def __init__(self, options: BybitOptions, pooling: Pooling | None) -> None:
        super().__init__(pooling)
        self._options = options

    @property
    def options(self) -> BybitOptions:
        return self._options

    @property
    def endpoint(self) -> str:
        return self._options.endpoint

    @property
    def markets(self) -> Sequence[Market]:
        return [BY_KEY[key] for key in MARKETS]

    @property
    def per_address(self) -> bool:
        return True

    def kept_key(self) -> str:
        return self._options.endpoint

    def new_kept(self) -> Kept:
        return Kept(
            make_client(),
            {key: MarketState(limit=LIMIT) for key in MARKETS},
            address=Budget(limit=LIMIT, window_seconds=WINDOW_SECONDS, share=SHARE),
        )

    def url(self, market: Market, path: str) -> str:
        del market
        return f"{HOSTS[self._options.endpoint]}/v5/market/{path}"

    async def ask(
        self, market: Market, path: str, params: dict[str, str], node_id: str = ""
    ) -> Any:
        """A path of the market's category."""
        return await self.get(market, path, {"category": market.key, **params}, node_id)

    def answer(self, response: httpx.Response, budget: Budget, node_id: str) -> Any:
        status = response.status_code
        if status == 403:
            # A ban for asking too much, or an address in a country Bybit
            # does not serve: it says nothing to tell the two apart.
            budget.hold(time.time() + BAN_SECONDS)
            raise AdapterError(
                "unknown",
                say(
                    "Bybit refuses this address: too many requests, or a "
                    "region it does not serve"
                ),
            )
        if status >= 500 or status == 429:
            if status == 429:
                budget.hold(time.time() + WINDOW_SECONDS)
            raise AdapterError("network", say("Bybit is not answering"))
        try:
            body = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise AdapterError("network", say("Bybit is not answering"))
        code = body.get("retCode")
        if code == 0:
            return body.get("result") or {}
        if code in TOO_MANY:
            budget.hold(time.time() + WINDOW_SECONDS)
            raise AdapterError("unknown", say(WORDS.held, seconds=WINDOW_SECONDS))
        if code == NOT_SERVED:
            raise AdapterError(
                "config",
                say("Bybit does not serve this region; choose another endpoint"),
            )
        if code in {PARAMETER_ERROR, INVALID_SYMBOL} and node_id:
            raise NodeNotFound(node_id)
        if code == SERVER_ERROR:
            raise AdapterError("network", say("Bybit is not answering"))
        logger.warning("Bybit refused a request: %s, code %s", status, code)
        raise AdapterError(
            "unknown",
            say("Bybit refused the request (code {code})", code=code or status),
        )

    async def read_symbols(self, kept: Kept, market: Market) -> list[Symbol]:
        """The category's trading symbols; spot in one answer, the rest a page
        of a thousand at a time by Bybit's cursor."""
        found: list[Symbol] = []
        cursor = ""
        while True:
            params: dict[str, str] = {"category": market.key}
            if market.futures:
                params["limit"] = PAGE
                if cursor:
                    params["cursor"] = cursor
            answer = await self._get(kept, market, "instruments-info", params, "")
            found += symbols_of(answer)
            cursor = str(answer.get("nextPageCursor") or "")
            if not market.futures or not cursor:
                return found

    async def read_tickers(self, kept: Kept, market: Market) -> list[dict[str, Any]]:
        answer = await self._get(kept, market, "tickers", {"category": market.key}, "")
        return [one for one in answer.get("list") or [] if isinstance(one, dict)]

    async def server_time_ms(self, market: Market) -> int | None:
        answer = await self.get(market, "time", {})
        nano = milliseconds(answer.get("timeNano"))
        return None if nano is None else nano // 1_000_000


def symbols_of(answer: dict[str, Any]) -> list[Symbol]:
    """A page of `instruments-info` reduced to the symbols that trade."""
    found: list[Symbol] = []
    for item in answer.get("list") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("symbol")
        if item.get("status") != "Trading" or not isinstance(name, str) or ":" in name:
            continue
        prices = item.get("priceFilter") or {}
        lots = item.get("lotSizeFilter") or {}
        delivery = milliseconds(item.get("deliveryTime"))
        found.append(
            Symbol(
                name=name,
                base=str(item.get("baseCoin") or ""),
                quote=str(item.get("quoteCoin") or ""),
                status="Trading",
                contract_type=item.get("contractType") or None,
                # A perpetual's delivery time is 0, or the day it is delisted.
                delivery_ms=delivery or None,
                onboard_ms=milliseconds(item.get("launchTime")),
                price_step=decimal_text(prices.get("tickSize")),
                quantity_step=decimal_text(
                    lots.get("qtyStep") or lots.get("basePrecision")
                ),
                min_notional=decimal_text(
                    lots.get("minNotionalValue") or lots.get("minOrderAmt")
                ),
            )
        )
    return found
