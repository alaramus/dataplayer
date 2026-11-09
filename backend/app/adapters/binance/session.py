"""How this application talks to Binance's REST, and nothing about what for (D316).

One httpx client a connection, kept in the resource store with what must
outlive a request: the weight each market has used this minute, a ban a
market is under, the symbol list and the last tickers. A draft and a check
get a client of their own, closed after them.

Binance weighs every request and bans an address that keeps asking past its
limit, so the weight it reports is read from every answer and a request that
would take a market past 80% of its limit is not sent. Nothing is retried by
itself.
"""

import hashlib
import hmac
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

import httpx

from app.adapters.binance.markets import BY_KEY, HOSTS, MARKETS, Market, MarketKey
from app.adapters.binance.options import HOSTS_OF, BinanceOptions, key_of
from app.adapters.protocol import AdapterError, ConnectionCheckResult, NodeNotFound
from app.adapters.resources import Pooling
from app.core.logs import record_failure, with_ref
from app.core.translation import say

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
# Of a market's limit a minute, the share this application spends at most:
# the rest is left for whatever else asks from the same address.
CEILING_SHARE = 0.8
SYMBOLS_SECONDS = 3600.0
TICKERS_SECONDS = 10.0

UNKNOWN_SYMBOL = -1121
# Futures answer trades of the last two days only.
OUTSIDE_WINDOW = -4166
# A signed request's time was outside the window Binance accepts.
STALE_TIMESTAMP = -1021
# The key is malformed, unknown, not allowed from this address or for this.
REFUSED_KEY = {-2014, -2015, -1022, -2008}
# How long a signed request stays good after the time it carries.
RECV_WINDOW = "10000"
CLOCK_SECONDS = 3600.0


@dataclass(frozen=True)
class Symbol:
    """A pair that trades, with the rules an order on it obeys."""

    name: str
    base: str
    quote: str
    status: str
    contract_type: str | None = None
    delivery_ms: int | None = None
    onboard_ms: int | None = None
    price_step: str | None = None
    quantity_step: str | None = None
    min_notional: str | None = None
    # What one contract is worth in the quote asset, on COIN-M (D321).
    contract_size: int | None = None


@dataclass
class MarketState:
    limit: int
    used: int = 0
    # The minute `used` was read in, as whole minutes since the epoch; Binance
    # counts a minute from its start.
    minute: int = -1
    held_until: float = 0.0
    symbols: list[Symbol] | None = None
    symbols_at: float = 0.0
    # When the list was read, by the wall clock, for a report to say.
    symbols_read_at: float | None = None
    tickers: list[dict[str, Any]] | None = None
    tickers_at: float = 0.0
    # How far Binance's clock is ahead of this server's, for a signed
    # request's time (D322), and when that was measured.
    offset_ms: int = 0
    offset_at: float | None = None


@dataclass(frozen=True)
class Pinged:
    """A market after a ping: what it keeps, how long it took, or why not."""

    state: MarketState
    latency_ms: float | None
    failure: str | None


@dataclass
class BinanceKept:
    """What a connection keeps between requests."""

    client: httpx.AsyncClient
    markets: dict[MarketKey, MarketState] = field(
        default_factory=lambda: {
            key: MarketState(limit=BY_KEY[key].weight_limit) for key in MARKETS
        }
    )

    async def close(self) -> None:
        await self.client.aclose()


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(TIMEOUT_SECONDS),
        # A proxy named in the backend's environment is not one the user chose.
        trust_env=False,
        headers={"User-Agent": "DataPlayer"},
    )


def seconds_left_of_minute(now: float) -> int:
    return max(1, 60 - int(now % 60))


def decimal_text(value: Any) -> str | None:
    """A number as Binance wrote it, checked to be one; never through a float."""
    if value is None:
        return None
    text = str(value)
    try:
        Decimal(text)
    except InvalidOperation:
        return None
    return text


class BinanceSession:
    def __init__(self, options: BinanceOptions, pooling: Pooling | None) -> None:
        self._options = options
        self._pooling = pooling

    @property
    def options(self) -> BinanceOptions:
        return self._options

    def host(self, market: Market) -> str:
        return HOSTS[HOSTS_OF[self._options.endpoint]][market.key]

    @property
    def main_hosts(self) -> bool:
        """Whether this is Binance itself rather than its testnet or data host."""
        return HOSTS_OF[self._options.endpoint] == "binance"

    @property
    def keyed(self) -> bool:
        """Whether this connection reads an account as well as the market."""
        return key_of(self._options) is not None

    @asynccontextmanager
    async def kept(self) -> AsyncIterator[BinanceKept]:
        pooling = self._pooling
        if pooling is not None and pooling.store.keeps:
            key = f"binance:{pooling.connector_id}:{self._options.endpoint}"

            async def create() -> BinanceKept:
                return BinanceKept(make_client())

            yield await pooling.store.get_or_create(key, BinanceKept, create)
            return
        kept = BinanceKept(make_client())
        try:
            yield kept
        finally:
            await kept.close()

    async def get(
        self, market: Market, name: str, params: dict[str, str], node_id: str = ""
    ) -> Any:
        """One request, its weight counted, its failure reduced."""
        async with self.kept() as kept:
            return await self._get(kept, market, name, params, node_id)

    async def signed(
        self, market: Market, name: str, params: dict[str, str], node_id: str = ""
    ) -> Any:
        """A request of the account, signed with the connection's key (D322).

        A time Binance finds outside its window is measured again and the
        request sent once more: the clocks moved apart, nothing about the
        request was wrong.
        """
        async with self.kept() as kept:
            for fresh in (False, True):
                await self._clock(kept, market, fresh=fresh)
                try:
                    return await self._get(
                        kept, market, name, params, node_id, signed=True
                    )
                except StaleTimestamp:
                    continue
        raise AdapterError(
            "config", say("Binance's clock and this server's differ too much")
        )

    async def _clock(self, kept: BinanceKept, market: Market, fresh: bool) -> None:
        state = kept.markets[market.key]
        now = time.monotonic()
        if (
            not fresh
            and state.offset_at is not None
            and now - state.offset_at < CLOCK_SECONDS
        ):
            return
        before = time.time() * 1000
        answer = await self._get(kept, market, "time", {}, "")
        after = time.time() * 1000
        server = answer.get("serverTime") if isinstance(answer, dict) else None
        if isinstance(server, int):
            state.offset_ms = int(server - (before + after) / 2)
            state.offset_at = now

    def _stamped(
        self, state: MarketState, params: dict[str, str]
    ) -> tuple[str, dict[str, str]]:
        """The signed query string, and the header naming the key."""
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

    async def _get(
        self,
        kept: BinanceKept,
        market: Market,
        name: str,
        params: dict[str, str],
        node_id: str,
        signed: bool = False,
    ) -> Any:
        state = kept.markets[market.key]
        now = time.time()
        if state.held_until > now:
            raise AdapterError(
                "unknown",
                say(
                    "Binance refuses requests from this address for {seconds} s more",
                    seconds=int(state.held_until - now) + 1,
                ),
            )
        weight = market.weight(name, params)
        minute = int(now // 60)
        used = state.used if state.minute == minute else 0
        if used + weight > state.limit * CEILING_SHARE:
            raise AdapterError(
                "unknown",
                say(
                    "Binance's rate limit is nearly spent; try again in {seconds} s",
                    seconds=seconds_left_of_minute(now),
                ),
            )
        url = self.host(market) + market.path(name)
        try:
            if signed:
                query, headers = self._stamped(state, params)
                response = await kept.client.get(f"{url}?{query}", headers=headers)
            else:
                response = await kept.client.get(url, params=params)
        except httpx.TimeoutException:
            raise AdapterError(
                "timeout", say("Binance did not answer in time")
            ) from None
        except httpx.TransportError:
            raise AdapterError("network", say("Could not reach Binance")) from None
        reported = response.headers.get("x-mbx-used-weight-1m")
        if reported is not None and reported.isdigit():
            state.used = int(reported)
            state.minute = minute
        else:
            state.used = used + weight
            state.minute = minute
        if response.status_code == 200:
            return response.json()
        raise self._refusal(response, state, node_id)

    def _refusal(
        self, response: httpx.Response, state: MarketState, node_id: str
    ) -> Exception:
        status = response.status_code
        if status in {418, 429}:
            retry = response.headers.get("retry-after", "")
            seconds = int(retry) if retry.isdigit() else 60
            state.held_until = time.time() + seconds
            return AdapterError(
                "unknown",
                say(
                    "Binance refuses requests from this address for {seconds} s more",
                    seconds=seconds,
                ),
            )
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

    async def symbols(self, market: Market) -> list[Symbol]:
        """The market's trading symbols, read at most once an hour."""
        async with self.kept() as kept:
            state = kept.markets[market.key]
            now = time.monotonic()
            if state.symbols is not None and now - state.symbols_at < SYMBOLS_SECONDS:
                return state.symbols
            params = (
                {"symbolStatus": "TRADING", "showPermissionSets": "false"}
                if market.key == "spot"
                else {}
            )
            info = await self._get(kept, market, "exchangeInfo", params, "")
            state.symbols = symbols_of(info)
            state.symbols_at = now
            state.symbols_read_at = time.time()
            for limit in info.get("rateLimits") or []:
                if (
                    limit.get("rateLimitType") == "REQUEST_WEIGHT"
                    and limit.get("interval") == "MINUTE"
                    and limit.get("intervalNum") == 1
                    and isinstance(limit.get("limit"), int)
                ):
                    state.limit = limit["limit"]
            return state.symbols

    async def symbol(self, market: Market, name: str, node_id: str) -> Symbol:
        """A symbol named by a client, found among the market's or not at all."""
        for one in await self.symbols(market):
            if one.name == name:
                return one
        raise NodeNotFound(node_id)

    async def tickers(self, market: Market) -> list[dict[str, Any]]:
        """Every symbol's last day, read at most once in ten seconds."""
        async with self.kept() as kept:
            state = kept.markets[market.key]
            now = time.monotonic()
            if state.tickers is not None and now - state.tickers_at < TICKERS_SECONDS:
                return state.tickers
            answer = await self._get(kept, market, "ticker/24hr", {}, "")
            state.tickers = [one for one in answer if isinstance(one, dict)]
            state.tickers_at = now
            return state.tickers

    async def states(self) -> dict[MarketKey, MarketState]:
        """What each market has kept, as it stands: the weight, a ban, the lists."""
        async with self.kept() as kept:
            return {key: replace(state) for key, state in kept.markets.items()}

    async def pinged(self) -> dict[MarketKey, Pinged]:
        """Each market pinged, and what it kept just after.

        One client for all of it: Binance reports the weight its address used
        this minute on every answer, so a ping is what makes the count current
        even for a connection that asked nothing else lately.
        """
        found: dict[MarketKey, Pinged] = {}
        async with self.kept() as kept:
            for key in MARKETS:
                started = time.perf_counter()
                try:
                    await self._get(kept, BY_KEY[key], "ping", {}, "")
                except AdapterError as failure:
                    found[key] = Pinged(
                        replace(kept.markets[key]), None, failure.message
                    )
                    continue
                elapsed = (time.perf_counter() - started) * 1000
                found[key] = Pinged(replace(kept.markets[key]), elapsed, None)
        return found

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

    async def check(self) -> ConnectionCheckResult:
        """Each market's `ping`, in words that name no address."""
        started = time.perf_counter()
        try:
            async with self.kept() as kept:
                for key in MARKETS:
                    await self._get(kept, BY_KEY[key], "ping", {}, "")
        except AdapterError as failure:
            return ConnectionCheckResult(
                ok=False, message=failure.message, error_kind=failure.error_kind
            )
        except Exception as failure:  # noqa: BLE001 - a check answers, never raises
            ref = record_failure(logger, "Binance check", failure, private=True)
            return ConnectionCheckResult(
                ok=False,
                message=with_ref(say("Connection failed"), ref),
                error_kind="unknown",
            )
        elapsed = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=elapsed
        )


class StaleTimestamp(Exception):
    """A signed request carried a time Binance would not take; measured again."""


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
