"""How this application talks to Coinbase Exchange's REST, and nothing about what for (D438).

The client and the lists are kept the shared way (D425). Coinbase limits an
address — ten public requests a second, bursts to fifteen — and sends no
count, so one budget is kept here for the address, its windows a second from
their start and its share 40%, so two windows side by side never pass 80% of
any rolling second; a request over that waits for the next second (D432).
Numbers in candles and the clock arrive as JSON numbers and are read as their
text, never as floats. Nothing is retried by itself.
"""

import json
import logging
import time
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.adapters.coinbase.markets import BY_KEY, HOSTS, MARKETS, Market
from app.adapters.coinbase.options import CoinbaseOptions
from app.adapters.market import session as shared
from app.adapters.market.budget import Budget
from app.adapters.market.session import Kept, MarketSession, MarketState, Words
from app.adapters.market.shape import Symbol
from app.adapters.market.values import decimal_text
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.resources import Pooling
from app.core.translation import N_, say

logger = logging.getLogger(__name__)

TIME = "/time"
PRODUCTS = "/products"
STATS = "/products/stats"

LIMIT = 10
WINDOW_SECONDS = 1
SHARE = 0.4

WORDS = Words(
    held=N_("Coinbase refuses requests from this address for {seconds} s more"),
    spent=N_("Coinbase's rate limit is nearly spent; try again in {seconds} s"),
    timeout=N_("Coinbase did not answer in time"),
    unreachable=N_("Could not reach Coinbase"),
)


def make_client() -> httpx.AsyncClient:
    return shared.make_client()


def parsed(response: httpx.Response) -> Any:
    """The body with every JSON number that is not whole kept as its text."""
    return json.loads(response.text, parse_float=str)


class CoinbaseSession(MarketSession[Market]):
    name = "coinbase"
    words = WORDS
    ping_path = TIME
    clock_path = TIME
    paces = True

    def __init__(self, options: CoinbaseOptions, pooling: Pooling | None) -> None:
        super().__init__(pooling)
        self._options = options

    @property
    def endpoint(self) -> str:
        return self._options.endpoint

    @property
    def hosts(self) -> str:
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
        return HOSTS[self.hosts] + path

    def answer(self, response: httpx.Response, budget: Budget, node_id: str) -> Any:
        status = response.status_code
        if status == 429:
            budget.hold(time.time() + WINDOW_SECONDS)
            raise AdapterError("unknown", say(WORDS.held, seconds=WINDOW_SECONDS))
        if status == 403:
            raise AdapterError(
                "config",
                say(
                    "Coinbase refuses this address: a region it does not serve, "
                    "or a block"
                ),
            )
        if status >= 500:
            raise AdapterError("network", say("Coinbase is not answering"))
        if status == 404 and node_id:
            raise NodeNotFound(node_id)
        if status != 200:
            logger.warning("Coinbase refused a request: %s", status)
            raise AdapterError(
                "unknown",
                say("Coinbase refused the request (HTTP {status})", status=status),
            )
        try:
            return parsed(response)
        except ValueError:
            raise AdapterError("network", say("Coinbase is not answering")) from None

    async def read_symbols(self, kept: Kept, market: Market) -> list[Symbol]:
        """The products that trade now; Coinbase answers them all at once."""
        return symbols_of(await self._get(kept, market, PRODUCTS, {}, ""))

    async def read_tickers(self, kept: Kept, market: Market) -> list[dict[str, Any]]:
        """Every product's day, one answer keyed by product."""
        answer = await self._get(kept, market, STATS, {}, "")
        found: list[dict[str, Any]] = []
        for name, stats in (answer if isinstance(answer, dict) else {}).items():
            day = stats.get("stats_24hour") if isinstance(stats, dict) else None
            if isinstance(day, dict):
                found.append({"id": name, **day})
        return found

    def server_ms_of(self, answer: Any) -> int | None:
        epoch = answer.get("epoch") if isinstance(answer, dict) else None
        try:
            return int(Decimal(str(epoch)) * 1000) if epoch is not None else None
        except InvalidOperation:
            return None


def symbols_of(answer: Any) -> list[Symbol]:
    found: list[Symbol] = []
    for item in answer if isinstance(answer, list) else []:
        if not isinstance(item, dict):
            continue
        name = item.get("id")
        if (
            item.get("status") != "online"
            or item.get("trading_disabled")
            or not isinstance(name, str)
            or not name
            or ":" in name
        ):
            continue
        found.append(
            Symbol(
                name=name,
                base=str(item.get("base_currency") or ""),
                quote=str(item.get("quote_currency") or ""),
                status="online",
                price_step=decimal_text(item.get("quote_increment")),
                quantity_step=decimal_text(item.get("base_increment")),
                min_notional=decimal_text(item.get("min_market_funds")),
            )
        )
    return found
