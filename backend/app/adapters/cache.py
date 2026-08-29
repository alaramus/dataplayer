"""Bounded, process-local cache for reads from external data sources."""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Generic, Literal, Protocol, TypeVar, cast, runtime_checkable

from fastapi import Depends, Request

T = TypeVar("T")
_MISSING = object()
CacheArea = Literal["catalog", "fetch"]
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
class CacheResult(Generic[T]):
    value: T
    status: CacheStatus


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: float
    used_at: float


@dataclass(frozen=True)
class _Flight(Generic[T]):
    task: asyncio.Task[T]
    generation: int


class DataCache:
    """TTL cache with LRU bounds and one in-flight load per exact key.

    Invalidation advances a connector generation. A read that was already in
    flight may still answer its callers, but cannot put its now-stale value
    back after a successful mutation.
    """

    def __init__(
        self, *, max_entries: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._clock = clock
        self._entries: dict[CacheKey, _Entry[object]] = {}
        self._flights: dict[CacheKey, _Flight[object]] = {}
        self._tasks: set[asyncio.Task[object]] = set()
        self._generations: dict[uuid.UUID, int] = {}
        self._lock = asyncio.Lock()

    async def get_or_load(
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
                task = existing.task
                status: CacheStatus = "coalesced"
            else:
                generation = self._generations.get(key.connector_id, 0)
                task = cast(
                    asyncio.Task[object],
                    asyncio.create_task(
                        self._load_and_store(key, generation, ttl_seconds, load)
                    ),
                )
                self._tasks.add(task)
                task.add_done_callback(self._finish_task)
                self._flights[key] = _Flight(task=task, generation=generation)
                status = "refreshed" if refresh else "miss"

        value = await asyncio.shield(task)
        return CacheResult(cast(T, value), status)

    async def _load_and_store[T](
        self,
        key: CacheKey,
        generation: int,
        ttl_seconds: float,
        load: Callable[[], Awaitable[T]],
    ) -> T:
        value: object = _MISSING
        try:
            value = await load()
        finally:
            async with self._lock:
                flight = self._flights.get(key)
                if flight is not None and flight.task is asyncio.current_task():
                    self._flights.pop(key)
                    if (
                        value is not _MISSING
                        and self._generations.get(key.connector_id, 0) == generation
                    ):
                        used_at = self._clock()
                        self._entries[key] = _Entry(
                            value=value,
                            expires_at=used_at + ttl_seconds,
                            used_at=used_at,
                        )
                        self._drop_overflow()
        return cast(T, value)

    async def invalidate_connector(self, connector_id: uuid.UUID) -> None:
        """Forget all areas and prevent older in-flight reads being stored."""
        async with self._lock:
            self._generations[connector_id] = (
                self._generations.get(connector_id, 0) + 1
            )
            self._entries = {
                key: entry
                for key, entry in self._entries.items()
                if key.connector_id != connector_id
            }
            # Existing callers may still receive their older read, but a call
            # begun after this mutation must not coalesce with it.
            self._flights = {
                key: flight
                for key, flight in self._flights.items()
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


def get_data_cache(request: Request) -> DataCache:
    cache = request.app.state.data_cache
    if not isinstance(cache, DataCache):
        raise RuntimeError("The application was started without a data cache")
    return cache


DataCacheDep = Annotated[DataCache, Depends(get_data_cache)]
