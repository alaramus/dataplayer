"""Bounded, process-local cache for reads from external data sources."""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol, cast, runtime_checkable

from fastapi import Depends, Request, Response

from app.adapters.protocol import DataAdapter

# What a source may be asked to cache. "metadata" is what an editor
# completes against, which changes far less often than rows do (D65).
CacheArea = Literal["catalog", "fetch", "metadata"]
CacheStatus = Literal["hit", "miss", "coalesced", "refreshed"]


@runtime_checkable
class SupportsReadCache(Protocol):
    """Opt-in policy owned by the source whose answers would be cached."""

    def cache_ttl(self, area: CacheArea) -> float: ...


@dataclass(frozen=True)
class CacheKey:
    """One owner's exact read against one stored connector."""

    owner_id: uuid.UUID
    connector_id: uuid.UUID
    area: CacheArea
    request: str


@dataclass(frozen=True)
class CacheResult[T]:
    value: T
    status: CacheStatus


@dataclass
class _Entry[T]:
    value: T
    expires_at: float
    used_at: float


class DataCache:
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

    async def get_or_load[T](
        self,
        key: CacheKey,
        *,
        ttl_seconds: float,
        load: Callable[[], Awaitable[T]],
        refresh: bool = False,
    ) -> CacheResult[T]:
        """Return a live value, sharing an identical concurrent load."""
        if ttl_seconds <= 0:
            return CacheResult(await load(), "refreshed" if refresh else "miss")

        now = self._clock()
        async with self._lock:
            self._drop_expired(now)
            entry = self._entries.get(key)
            if entry is not None and not refresh:
                entry.used_at = now
                return CacheResult(cast(T, entry.value), "hit")

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
        return CacheResult(cast(T, value), status)

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
                    value=value, expires_at=used_at + ttl_seconds, used_at=used_at
                )
                self._drop_overflow()
        return value

    async def invalidate_connector(self, connector_id: uuid.UUID) -> None:
        """Forget all areas and prevent older in-flight reads being stored."""
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

    def _drop_expired(self, now: float) -> None:
        for key in [
            key for key, entry in self._entries.items() if entry.expires_at <= now
        ]:
            self._entries.pop(key)

    def _drop_overflow(self) -> None:
        while len(self._entries) > self._max_entries:
            oldest = min(self._entries, key=lambda key: self._entries[key].used_at)
            self._entries.pop(oldest)


async def cached_read[T](
    *,
    data_cache: DataCache,
    adapter: DataAdapter,
    key: CacheKey,
    refresh: bool,
    response: Response,
    load: Callable[[], Awaitable[T]],
) -> T:
    if not isinstance(adapter, SupportsReadCache):
        response.headers["X-Data-Cache"] = "bypass"
        return await load()
    ttl_seconds = adapter.cache_ttl(key.area)
    if ttl_seconds <= 0:
        response.headers["X-Data-Cache"] = "bypass"
        return await load()
    cached = await data_cache.get_or_load(
        key,
        ttl_seconds=ttl_seconds,
        load=load,
        refresh=refresh,
    )
    response.headers["X-Data-Cache"] = cached.status
    return cached.value

def get_data_cache(request: Request) -> DataCache:
    cache = request.app.state.data_cache
    if not isinstance(cache, DataCache):
        raise RuntimeError("The application was started without a data cache")
    return cache


DataCacheDep = Annotated[DataCache, Depends(get_data_cache)]
