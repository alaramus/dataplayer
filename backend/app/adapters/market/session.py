"""One client a connection, what it keeps between requests, and a request's way (D316, D425).

The shared part of every exchange's session: the client kept in the resource
store with each market's budget and lists, the request counted against the
budget and reduced to a kind when it fails, the symbol list read once an hour
and the tickers once in ten seconds, a ping of every market. What differs —
hosts, paths, weights, the shape of an answer, the codes of a refusal, how a
request is signed — each exchange's session says by overriding a method.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

import httpx

from app.adapters.market.budget import Budget, Held, OverBudget
from app.adapters.market.shape import Market, Symbol
from app.adapters.protocol import AdapterError, ConnectionCheckResult, NodeNotFound
from app.adapters.resources import Pooling
from app.core.logs import record_failure, with_ref
from app.core.translation import say

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
SYMBOLS_SECONDS = 3600.0
# How long a measured difference between the clocks is trusted.
CLOCK_SECONDS = 3600.0
TICKERS_SECONDS = 10.0


@dataclass
class MarketState(Budget):
    """A market's budget, and the lists and clock offset it keeps."""

    symbols: list[Symbol] | None = None
    symbols_at: float = 0.0
    # When the list was read, by the wall clock, for a report to say.
    symbols_read_at: float | None = None
    # The read under way, which every asker waits on rather than starting
    # another.
    symbols_reading: asyncio.Task[list[Symbol]] | None = None
    tickers: list[dict[str, Any]] | None = None
    tickers_at: float = 0.0
    # How far the exchange's clock is ahead of this server's, for a signed
    # request's time (D322), and when that was measured.
    offset_ms: int = 0
    offset_at: float | None = None


@dataclass(frozen=True)
class Pinged:
    """A market after a ping: what it keeps, how long it took, or why not."""

    # The budget the market spends from: its own, or the address's.
    state: Budget
    latency_ms: float | None
    failure: str | None


class Closable(Protocol):
    async def close(self) -> None: ...


@dataclass
class Kept:
    """What a connection keeps between requests, and its live streams (D323)."""

    client: httpx.AsyncClient
    markets: dict[str, MarketState]
    # One budget for every market, where the exchange limits the address as
    # a whole rather than each market (D426).
    address: Budget | None = None
    # By stream key; a stream is dropped here by its last watcher.
    streams: dict[str, Closable] = field(default_factory=dict)

    def forget_stream(self, stream: Closable) -> None:
        for key, kept in list(self.streams.items()):
            if kept is stream:
                del self.streams[key]

    async def close(self) -> None:
        for stream in list(self.streams.values()):
            await stream.close()
        self.streams.clear()
        await self.client.aclose()


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(TIMEOUT_SECONDS),
        # A proxy named in the backend's environment is not one the user chose.
        trust_env=False,
        headers={"User-Agent": "DataPlayer"},
    )


@dataclass(frozen=True)
class Words:
    """What an exchange's session says when a request does not go through."""

    held: str
    spent: str
    timeout: str
    unreachable: str
    # A signed request still refused for its time after the clock was
    # measured again (D322).
    clock: str = ""


class StaleTimestamp(Exception):
    """A signed request carried a time the exchange would not take."""


class MarketSession[M: Market]:
    """The shared way of a request; an exchange overrides what is its own."""

    # Logged and keyed by; never shown.
    name = "exchange"
    words: Words
    # What every market's ping asks, as `get` names a path.
    ping_path = "ping"
    # What answers the exchange's clock.
    clock_path = "time"

    def __init__(self, pooling: Pooling | None) -> None:
        self._pooling = pooling

    # --- what an exchange says ---------------------------------------------------

    @property
    def markets(self) -> Sequence[M]:
        raise NotImplementedError

    @property
    def keyed(self) -> bool:
        """Whether this connection reads an account as well as the market."""
        return False

    def kept_key(self) -> str:
        """What the client is kept under, beside the connection's id."""
        raise NotImplementedError

    def new_kept(self) -> Kept:
        raise NotImplementedError

    @property
    def per_address(self) -> bool:
        """Whether one budget is spent by every market (`Kept.address`)."""
        return False

    def url(self, market: M, path: str) -> str:
        raise NotImplementedError

    def weight(self, market: M, path: str, params: dict[str, str]) -> int:
        del market, path, params
        return 1

    def reported_used(self, response: httpx.Response) -> int | None:
        """What the exchange says this address used of the window, if it says."""
        del response
        return None

    def signed_request(
        self, state: MarketState, params: dict[str, str]
    ) -> tuple[str, dict[str, str]]:
        """The signed query string and the headers naming the key (D322).

        An exchange with no key reads nothing that needs one.
        """
        del state, params
        raise ValueError(say("This connection has no API key"))

    def answer(self, response: httpx.Response, budget: Budget, node_id: str) -> Any:
        """What the answer holds, or its refusal raised in words of a kind."""
        raise NotImplementedError

    async def read_symbols(self, kept: Kept, market: M) -> list[Symbol]:
        raise NotImplementedError

    async def read_tickers(self, kept: Kept, market: M) -> list[dict[str, Any]]:
        raise NotImplementedError

    def server_ms_of(self, answer: Any) -> int | None:
        """The exchange's clock in what `clock_path` answered."""
        raise NotImplementedError

    async def system_status(self) -> str | None:
        """The exchange's own word for its state, where it has one."""
        return None

    # --- the shared way --------------------------------------------------------------

    @asynccontextmanager
    async def kept(self) -> AsyncIterator[Kept]:
        pooling = self._pooling
        if pooling is not None and pooling.store.keeps:
            key = f"{self.name}:{pooling.connector_id}:{self.kept_key()}"

            async def create() -> Kept:
                return self.new_kept()

            yield await pooling.store.get_or_create(key, Kept, create)
            return
        kept = self.new_kept()
        try:
            yield kept
        finally:
            await kept.close()

    async def get(
        self, market: M, name: str, params: dict[str, str], node_id: str = ""
    ) -> Any:
        """One request, its weight counted, its failure reduced."""
        async with self.kept() as kept:
            return await self._get(kept, market, name, params, node_id)

    async def _get(
        self,
        kept: Kept,
        market: M,
        name: str,
        params: dict[str, str],
        node_id: str,
        signed: bool = False,
    ) -> Any:
        state = kept.markets[market.key]
        budget = budget_of(kept, market.key)
        now = time.time()
        weight = self.weight(market, name, params)
        try:
            before = budget.admit(weight, now)
        except Held as held:
            raise AdapterError(
                "unknown", say(self.words.held, seconds=held.seconds)
            ) from None
        except OverBudget as over:
            raise AdapterError(
                "unknown", say(self.words.spent, seconds=over.seconds)
            ) from None
        url = self.url(market, name)
        try:
            if signed:
                query, headers = self.signed_request(state, params)
                target = f"{url}?{query}" if query else url
                response = await kept.client.get(target, headers=headers)
            else:
                response = await kept.client.get(url, params=params)
        except httpx.TimeoutException:
            raise AdapterError("timeout", say(self.words.timeout)) from None
        except httpx.TransportError:
            raise AdapterError("network", say(self.words.unreachable)) from None
        budget.count(before, weight, now, self.reported_used(response))
        return self.answer(response, budget, node_id)

    async def server_time_ms(self, market: M) -> int | None:
        """The exchange's clock as one market answers it, or nothing."""
        return self.server_ms_of(await self.get(market, self.clock_path, {}))

    async def signed(
        self, market: M, name: str, params: dict[str, str], node_id: str = ""
    ) -> Any:
        """A request of the account, signed with the connection's key (D322).

        A time the exchange finds outside its window is measured again and
        the request sent once more: the clocks moved apart, nothing about the
        request was wrong. The only request ever sent twice.
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
        raise AdapterError("config", say(self.words.clock))

    async def _clock(self, kept: Kept, market: M, fresh: bool) -> None:
        """How far the exchange's clock is ahead, measured at most once an hour."""
        state = kept.markets[market.key]
        now = time.monotonic()
        if (
            not fresh
            and state.offset_at is not None
            and now - state.offset_at < CLOCK_SECONDS
        ):
            return
        before = time.time() * 1000
        answer = await self._get(kept, market, self.clock_path, {}, "")
        after = time.time() * 1000
        server = self.server_ms_of(answer)
        if server is not None:
            state.offset_ms = int(server - (before + after) / 2)
            state.offset_at = now

    async def symbols(self, market: M) -> list[Symbol]:
        """The market's trading symbols, read at most once an hour.

        The read is a task of its own that a caller only waits on: a search
        is cut off after two seconds (D200), and a read cancelled with it
        would leave the list unread, so the next search would start from
        nothing and be cut off again.
        """
        async with self.kept() as kept:
            state = kept.markets[market.key]
            now = time.monotonic()
            if state.symbols is not None and now - state.symbols_at < SYMBOLS_SECONDS:
                return state.symbols
            reading = state.symbols_reading
            if reading is None or reading.done():
                reading = asyncio.create_task(self._symbols(kept, market))
                reading.add_done_callback(_forget_failure)
                state.symbols_reading = reading
            return await asyncio.shield(reading)

    async def _symbols(self, kept: Kept, market: M) -> list[Symbol]:
        state = kept.markets[market.key]
        found = await self.read_symbols(kept, market)
        state.symbols = found
        state.symbols_at = time.monotonic()
        state.symbols_read_at = time.time()
        return found

    async def symbol(self, market: M, name: str, node_id: str) -> Symbol:
        """A symbol named by a client, found among the market's or not at all."""
        for one in await self.symbols(market):
            if one.name == name:
                return one
        raise NodeNotFound(node_id)

    async def tickers(self, market: M) -> list[dict[str, Any]]:
        """Every symbol's last day, read at most once in ten seconds."""
        async with self.kept() as kept:
            state = kept.markets[market.key]
            now = time.monotonic()
            if state.tickers is not None and now - state.tickers_at < TICKERS_SECONDS:
                return state.tickers
            state.tickers = await self.read_tickers(kept, market)
            state.tickers_at = now
            return state.tickers

    async def states(self) -> dict[str, MarketState]:
        """What each market has kept, as it stands: the budget, a ban, the lists."""
        async with self.kept() as kept:
            return {key: replace(state) for key, state in kept.markets.items()}

    async def pinged(self) -> dict[str, Pinged]:
        """Each market pinged, and what it kept just after.

        One client for all of it, so an exchange that reports the address's
        use on every answer makes the count current even for a connection
        that asked nothing else lately.
        """
        found: dict[str, Pinged] = {}
        async with self.kept() as kept:
            for market in self.markets:
                started = time.perf_counter()
                try:
                    await self._get(kept, market, self.ping_path, {}, "")
                except AdapterError as failure:
                    found[market.key] = Pinged(
                        replace(budget_of(kept, market.key)), None, failure.message
                    )
                    continue
                elapsed = (time.perf_counter() - started) * 1000
                found[market.key] = Pinged(
                    replace(budget_of(kept, market.key)), elapsed, None
                )
        return found

    async def check(self) -> ConnectionCheckResult:
        """Each market's ping, in words that name no address."""
        started = time.perf_counter()
        try:
            async with self.kept() as kept:
                for market in self.markets:
                    await self._get(kept, market, self.ping_path, {}, "")
        except AdapterError as failure:
            return ConnectionCheckResult(
                ok=False, message=failure.message, error_kind=failure.error_kind
            )
        except Exception as failure:  # noqa: BLE001 - a check answers, never raises
            ref = record_failure(logger, f"{self.name} check", failure, private=True)
            return ConnectionCheckResult(
                ok=False,
                message=with_ref(say("Connection failed"), ref),
                error_kind="unknown",
            )
        elapsed = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=elapsed
        )


def budget_of(kept: Kept, key: str) -> Budget:
    """What a request of a market spends from."""
    return kept.address if kept.address is not None else kept.markets[key]


def _forget_failure(task: asyncio.Task[list[Symbol]]) -> None:
    """A read nobody waited for to the end fails quietly; the next asks again."""
    if not task.cancelled():
        task.exception()
