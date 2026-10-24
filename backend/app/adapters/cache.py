"""The read-cache contract and its bounded process-local implementation."""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Annotated,
    Literal,
    Protocol,
    assert_never,
    cast,
    runtime_checkable,
)

from fastapi import Depends, Request, Response
from pydantic import BaseModel

from app.adapters.protocol import DataAdapter
from app.core.translation import say

if TYPE_CHECKING:
    from app.adapters.cache_serialization import CacheFormat

# What a source may be asked to cache. "metadata" is editor completion data;
# "relation" is a full description of one selected relation (D65, D246).
CacheArea = Literal["catalog", "fetch", "metadata", "relation"]
CacheStatus = Literal["hit", "miss", "coalesced", "refreshed", "bypass"]
CacheBackendName = Literal["memory", "redis"]
CacheHealthStatus = Literal["healthy", "degraded"]

# The longest window a connection's owner may ask for. A day is far past any
# staleness somebody browsing data would accept, and a ceiling means a typo of
# one extra zero cannot pin a page there for a week (D105).
MAX_CACHE_TTL_SECONDS = 86_400


class CacheMeasurements(BaseModel):
    hits: int
    misses: int
    coalesced: int
    refreshed: int
    bypasses: int
    invalidations: int
    failures: int


class CacheHealth(BaseModel):
    backend: CacheBackendName
    status: CacheHealthStatus
    shared: bool
    message: str
    measurements: CacheMeasurements


class CacheMeter:
    """Process-lifetime evidence for deciding whether more cache is justified."""

    def __init__(self) -> None:
        self._hits = 0
        self._misses = 0
        self._coalesced = 0
        self._refreshed = 0
        self._bypasses = 0
        self._invalidations = 0
        self._failures = 0

    def observe(self, status: CacheStatus) -> None:
        # Every member of the closed set is named. A sixth status added to
        # CacheStatus fails the type check here rather than being counted
        # silently as something it is not.
        match status:
            case "hit":
                self._hits += 1
            case "miss":
                self._misses += 1
            case "coalesced":
                self._coalesced += 1
            case "refreshed":
                self._refreshed += 1
            case "bypass":
                self._bypasses += 1
            case unreachable:
                assert_never(unreachable)

    def invalidated(self) -> None:
        self._invalidations += 1

    def failed(self) -> None:
        self._failures += 1

    def snapshot(self) -> CacheMeasurements:
        return CacheMeasurements(
            hits=self._hits,
            misses=self._misses,
            coalesced=self._coalesced,
            refreshed=self._refreshed,
            bypasses=self._bypasses,
            invalidations=self._invalidations,
            failures=self._failures,
        )


@runtime_checkable
class SupportsReadCache(Protocol):
    """Opt-in policy owned by the source whose answers would be cached.

    A classmethod, because the answer belongs to the kind of source rather
    than to one connection to it: the form that offers to re-time a
    connection has to say what it would be re-timing, and at that moment
    there is a chosen type and no adapter (D105).
    """

    @classmethod
    def cache_ttl(cls, area: CacheArea) -> float: ...


class SourceCacheWindows(BaseModel):
    """Seconds a source type keeps each kind of answer its owner may re-time.

    Only the areas a connection may speak for, because this exists to be shown
    beside the field that speaks for them. What an editor completes against is
    not offered and so is not described.
    """

    catalog: float
    fetch: float


@dataclass(frozen=True)
class CacheKey:
    """One owner's exact read against one stored connector."""

    owner_id: uuid.UUID
    connector_id: uuid.UUID
    area: CacheArea
    request: str
    # What a source writes is worded in the reader's language (D226), so a
    # Russian answer is not handed to somebody reading English.
    language: str = "en"


@dataclass(frozen=True)
class CacheResult[T]:
    value: T
    status: CacheStatus
    # How long ago the source was actually read, in seconds. Zero whenever
    # this call is the read, and the entry's age on a hit: what the caller
    # wants to say is how old the data is, not when the cache was asked.
    age_seconds: float = 0.0


@dataclass
class _Entry[T]:
    value: T
    stored_at: float
    expires_at: float
    used_at: float


@runtime_checkable
class DataCache(Protocol):
    """The cache behaviour application code may rely on (D100)."""

    async def get_or_load[T](
        self,
        key: CacheKey,
        *,
        ttl_seconds: float,
        load: Callable[[], Awaitable[T]],
        cache_format: CacheFormat[T],
        refresh: bool = False,
    ) -> CacheResult[T]: ...

    async def invalidate_connector(self, connector_id: uuid.UUID) -> None: ...

    def observe(self, status: CacheStatus) -> None: ...

    async def health(self) -> CacheHealth: ...

    async def aclose(self) -> None: ...


class MemoryDataCache:
    """TTL cache with LRU bounds and one in-flight load per exact key.

    Invalidation drops the connector's entries and forgets its loads in
    flight. A load only stores its answer while the flight table still names
    it, so a read begun before a mutation may still answer the callers that
    started it, and cannot put its now-stale value back afterwards.
    """

    def __init__(
        self, *, max_entries: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._clock = clock
        self._entries: dict[CacheKey, _Entry[object]] = {}
        self._flights: dict[CacheKey, asyncio.Task[object]] = {}
        self._tasks: set[asyncio.Task[object]] = set()
        self._lock = asyncio.Lock()
        self._meter = CacheMeter()

    async def get_or_load[T](
        self,
        key: CacheKey,
        *,
        ttl_seconds: float,
        load: Callable[[], Awaitable[T]],
        cache_format: CacheFormat[T],
        refresh: bool = False,
    ) -> CacheResult[T]:
        """Return a live value, sharing an identical concurrent load."""
        # Memory retains the typed object. The explicit format belongs to the
        # protocol because a remote backend must never guess what to rebuild.
        _ = cache_format
        if ttl_seconds <= 0:
            return self._result(await load(), "refreshed" if refresh else "miss")

        now = self._clock()
        async with self._lock:
            self._drop_expired(now)
            entry = self._entries.get(key)
            if entry is not None and not refresh:
                entry.used_at = now
                return self._result(
                    cast(T, entry.value), "hit", age_seconds=now - entry.stored_at
                )

            existing = self._flights.get(key)
            if existing is not None:
                task = existing
                status: CacheStatus = "coalesced"
            else:
                task = cast(
                    asyncio.Task[object],
                    asyncio.create_task(
                        self._load_and_store(key, ttl_seconds, load)
                    ),
                )
                self._tasks.add(task)
                task.add_done_callback(self._finish_task)
                self._flights[key] = task
                status = "refreshed" if refresh else "miss"

        value = await asyncio.shield(task)
        return self._result(cast(T, value), status)

    async def _load_and_store[T](
        self, key: CacheKey, ttl_seconds: float, load: Callable[[], Awaitable[T]]
    ) -> T:
        try:
            value = await load()
        except BaseException:
            async with self._lock:
                if self._flights.get(key) is asyncio.current_task():
                    self._flights.pop(key)
            raise

        async with self._lock:
            # Storing is conditional on this load still being the one the
            # flight table names. Invalidation removes it from there, and that
            # alone is what stops a read begun before a mutation from putting
            # its stale answer back after it.
            if self._flights.get(key) is asyncio.current_task():
                self._flights.pop(key)
                used_at = self._clock()
                self._entries[key] = _Entry(
                    value=value,
                    stored_at=used_at,
                    expires_at=used_at + ttl_seconds,
                    used_at=used_at,
                )
                self._drop_overflow()
        return value

    async def invalidate_connector(self, connector_id: uuid.UUID) -> None:
        """Forget all areas and prevent older in-flight reads being stored."""
        self._meter.invalidated()
        async with self._lock:
            self._entries = {
                key: entry
                for key, entry in self._entries.items()
                if key.connector_id != connector_id
            }
            # Forgetting the flight does two things at once, and both matter: a
            # call begun after this mutation cannot coalesce with an older read,
            # and that older read can no longer store what it returns, because
            # storing requires still being named here.
            self._flights = {
                key: task
                for key, task in self._flights.items()
                if key.connector_id != connector_id
            }

    async def size(self) -> int:
        async with self._lock:
            self._drop_expired(self._clock())
            return len(self._entries)

    async def health(self) -> CacheHealth:
        return CacheHealth(
            backend="memory",
            status="healthy",
            shared=False,
            message=say("Process-local cache is ready"),
            measurements=self._meter.snapshot(),
        )

    def observe(self, status: CacheStatus) -> None:
        self._meter.observe(status)

    async def aclose(self) -> None:
        async with self._lock:
            tasks = list(self._tasks)
            self._entries.clear()
            self._flights.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _finish_task(self, task: asyncio.Task[object]) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            # A caller cancelled while shielded may leave nobody awaiting the
            # loader. Retrieving the exception avoids an unhandled-task warning;
            # ordinary awaiters still receive the same exception.
            task.exception()

    def _result[T](
        self, value: T, status: CacheStatus, *, age_seconds: float = 0.0
    ) -> CacheResult[T]:
        self.observe(status)
        return CacheResult(value, status, age_seconds)

    def _drop_expired(self, now: float) -> None:
        for key in [
            key for key, entry in self._entries.items() if entry.expires_at <= now
        ]:
            self._entries.pop(key)

    def _drop_overflow(self) -> None:
        while len(self._entries) > self._max_entries:
            oldest = min(self._entries, key=lambda key: self._entries[key].used_at)
            self._entries.pop(oldest)


def connector_may_choose(area: CacheArea) -> bool:
    """Whether a connection's own window replaces the source's for this area.

    Catalog levels and pages of rows are what somebody is looking at, and how
    stale that may be is a judgement about their data rather than about the
    driver. Editor metadata and relation descriptions instead use their source's
    own windows (D105, D246).
    """
    match area:
        case "catalog" | "fetch":
            return True
        case "metadata" | "relation":
            return False
        case unreachable:
            assert_never(unreachable)


def read_ttl(
    adapter: DataAdapter, area: CacheArea, cache_ttl_seconds: int | None
) -> float:
    """How long an answer to this read may be kept, in seconds.

    Two parties, and only one of them may say yes. The source decides whether
    its answers may be cached at all, because it is the only one that knows
    what its freshness rules are (D31); a connection whose source never opted
    in is not made cacheable by a number typed into a form. Where the source
    did opt in, its owner decides how long — zero for never (D105).
    """
    if not isinstance(adapter, SupportsReadCache):
        return 0.0
    if cache_ttl_seconds is not None and connector_may_choose(area):
        return float(cache_ttl_seconds)
    return adapter.cache_ttl(area)


async def cached_read[T](
    *,
    data_cache: DataCache,
    adapter: DataAdapter,
    key: CacheKey,
    refresh: bool,
    response: Response,
    load: Callable[[], Awaitable[T]],
    cache_format: CacheFormat[T],
    cache_ttl_seconds: int | None = None,
) -> T:
    ttl_seconds = read_ttl(adapter, key.area, cache_ttl_seconds)
    if ttl_seconds <= 0:
        data_cache.observe("bypass")
        _report(response, "bypass", 0.0)
        return await load()
    cached = await data_cache.get_or_load(
        key,
        ttl_seconds=ttl_seconds,
        load=load,
        cache_format=cache_format,
        refresh=refresh,
    )
    _report(response, cached.status, cached.age_seconds)
    return cached.value


def _report(response: Response, status: CacheStatus, age_seconds: float) -> None:
    """Say where the answer came from and how old it is.

    Age travels beside the outcome rather than being worked out by whoever
    reads it: a screen knows when the answer reached it, and only the cache
    knows how long it had been sitting there before that (D105).
    """
    response.headers["X-Data-Cache"] = status
    response.headers["X-Data-Cache-Age"] = f"{max(age_seconds, 0.0):.3f}"


def get_data_cache(request: Request) -> DataCache:
    cache = request.app.state.data_cache
    if not isinstance(cache, DataCache):
        raise RuntimeError("The application was started without a data cache")
    return cache


DataCacheDep = Annotated[DataCache, Depends(get_data_cache)]
