"""Optional encrypted Redis storage for application read caching (D102)."""

import asyncio
import logging
import math
import uuid
from collections.abc import Awaitable, Callable
from typing import cast

from cryptography.exceptions import InvalidTag

from app.adapters.cache import (
    CacheHealth,
    CacheKey,
    CacheMeter,
    CacheResult,
    CacheStatus,
)
from app.adapters.cache_serialization import (
    CacheCipher,
    CacheFormat,
    CacheNamespace,
    CacheSerializationError,
)
from app.adapters.redis.cache_connection import (
    CacheConnectionError,
    InvalidationSubscription,
    RedisCacheConnection,
    SharedCacheConnection,
)

logger = logging.getLogger(__name__)


class RedisDataCache:
    """D31 cache semantics over encrypted shared Redis values.

    Redis stores completed entries and connector generations. Flights remain
    local tasks because the result of a source read cannot be transferred
    until it exists. The generation in their key, plus Pub/Sub, prevents a
    mutation in another worker from accepting or storing an older answer.
    """

    def __init__(
        self,
        connection: SharedCacheConnection,
        *,
        namespace: CacheNamespace,
        cipher: CacheCipher,
        max_entries: int,
        listener_retry_seconds: float = 1.0,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        if listener_retry_seconds <= 0:
            raise ValueError("listener_retry_seconds must be positive")
        self._connection = connection
        self._namespace = namespace
        self._cipher = cipher
        self._max_entries = max_entries
        self._listener_retry_seconds = listener_retry_seconds
        self._flights: dict[tuple[CacheKey, int], asyncio.Task[object]] = {}
        self._tasks: set[asyncio.Task[object]] = set()
        self._invalidating: set[uuid.UUID] = set()
        self._lock = asyncio.Lock()
        self._listener: asyncio.Task[None] | None = None
        self._closing = False
        self._available: bool | None = None
        self._meter = CacheMeter()

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        deployment: str,
        encryption_key: bytes,
        timeout_seconds: float,
        max_entries: int,
    ) -> RedisDataCache:
        return cls(
            RedisCacheConnection(url, timeout_seconds=timeout_seconds),
            namespace=CacheNamespace(deployment),
            cipher=CacheCipher(encryption_key),
            max_entries=max_entries,
        )

    def start(self) -> None:
        if self._listener is not None:
            return
        self._listener = asyncio.create_task(self._listen_for_invalidations())

    async def get_or_load[T](
        self,
        key: CacheKey,
        *,
        ttl_seconds: float,
        load: Callable[[], Awaitable[T]],
        cache_format: CacheFormat[T],
        refresh: bool = False,
    ) -> CacheResult[T]:
        if ttl_seconds <= 0 or await self._is_invalidating(key.connector_id):
            return self._result(await load(), "bypass")

        try:
            generation = await self._generation(key.connector_id)
            if not refresh:
                cached = await self._read(key, generation, cache_format, ttl_seconds)
                if cached is not None:
                    self._available = True
                    stored, age = cached
                    return self._result(stored, "hit", age_seconds=age)
        except CacheConnectionError:
            self._failed()
            return self._result(await load(), "bypass")

        flight_key = (key, generation)
        async with self._lock:
            existing = self._flights.get(flight_key)
            if existing is not None:
                task = existing
                status: CacheStatus = "coalesced"
            else:
                task = cast(
                    asyncio.Task[object],
                    asyncio.create_task(
                        self._load_and_store(
                            flight_key,
                            ttl_seconds,
                            load,
                            cache_format,
                        )
                    ),
                )
                self._flights[flight_key] = task
                self._tasks.add(task)
                task.add_done_callback(self._finish_task)
                status = "refreshed" if refresh else "miss"

        value = await asyncio.shield(task)
        return self._result(cast(T, value), status)

    async def _read[T](
        self,
        key: CacheKey,
        generation: int,
        cache_format: CacheFormat[T],
        ttl_seconds: float,
    ) -> tuple[T, float] | None:
        value_key = self._namespace.value_key(key, generation)
        entry = await self._connection.read_entry(
            value_key, lru_key=self._namespace.lru_key
        )
        if entry is None:
            return None
        try:
            plaintext = self._cipher.decrypt(
                entry.payload,
                associated_data=self._namespace.associated_data(key, generation),
            )
            # What is left of the life it was stored for is what it has
            # already spent. Redis owns the clock, so no worker's own time of
            # day takes part in the answer.
            age = max(ttl_seconds - entry.expires_in_ms / 1000, 0.0)
            return cache_format.decode(plaintext), age
        except (CacheSerializationError, InvalidTag):
            self._meter.failed()
            logger.warning("Discarding an unreadable shared cache value")
            try:
                await self._connection.delete_entry(
                    value_key, lru_key=self._namespace.lru_key
                )
            except CacheConnectionError:
                self._failed()
            return None

    async def _load_and_store[T](
        self,
        flight_key: tuple[CacheKey, int],
        ttl_seconds: float,
        load: Callable[[], Awaitable[T]],
        cache_format: CacheFormat[T],
    ) -> T:
        key, generation = flight_key
        try:
            value = await load()
        except BaseException:
            await self._remove_flight(flight_key)
            raise

        if not await self._flight_is_current(flight_key):
            return value
        try:
            current_generation = await self._generation(key.connector_id)
            if current_generation == generation:
                plaintext = cache_format.encode(value)
                payload = self._cipher.encrypt(
                    plaintext,
                    associated_data=self._namespace.associated_data(key, generation),
                )
                await self._connection.write_entry(
                    self._namespace.value_key(key, generation),
                    payload,
                    ttl_ms=max(1, math.ceil(ttl_seconds * 1000)),
                    lru_key=self._namespace.lru_key,
                    max_entries=self._max_entries,
                )
                self._available = True
        except CacheConnectionError:
            self._failed()
        finally:
            await self._remove_flight(flight_key)
        return value

    async def invalidate_connector(self, connector_id: uuid.UUID) -> None:
        self._meter.invalidated()
        async with self._lock:
            self._invalidating.add(connector_id)
            self._forget_connector_unlocked(connector_id)
        try:
            await self._connection.increment(
                self._namespace.generation_key(connector_id)
            )
            await self._connection.publish(
                self._namespace.invalidation_channel,
                str(connector_id).encode(),
            )
            self._available = True
        except CacheConnectionError:
            # The mutation already succeeded. Cache failure is never allowed
            # to turn that success into a failed data request.
            self._failed()
        finally:
            async with self._lock:
                self._invalidating.discard(connector_id)

    async def size(self) -> int:
        try:
            size = await self._connection.count(self._namespace.values_prefix)
            self._available = True
            return size
        except CacheConnectionError:
            self._failed()
            return 0

    async def ping(self) -> bool:
        try:
            await self._connection.ping()
            self._available = True
            return True
        except CacheConnectionError:
            self._failed()
            return False

    async def health(self) -> CacheHealth:
        available = await self.ping()
        return CacheHealth(
            backend="redis",
            status="healthy" if available else "degraded",
            shared=True,
            message=(
                "Shared Redis cache is reachable"
                if available
                else "Shared Redis cache is unavailable; source reads are direct"
            ),
            measurements=self._meter.snapshot(),
        )

    def observe(self, status: CacheStatus) -> None:
        self._meter.observe(status)

    @property
    def available(self) -> bool | None:
        return self._available

    async def aclose(self) -> None:
        self._closing = True
        listener = self._listener
        if listener is not None:
            listener.cancel()
        async with self._lock:
            tasks = list(self._tasks)
            self._flights.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(
            *(task for task in (listener, *tasks) if task is not None),
            return_exceptions=True,
        )
        await self._connection.aclose()

    async def _generation(self, connector_id: uuid.UUID) -> int:
        raw = await self._connection.get(self._namespace.generation_key(connector_id))
        if raw is None:
            return 0
        try:
            generation = int(raw)
        except (TypeError, ValueError):
            raise CacheConnectionError from None
        if generation < 0:
            raise CacheConnectionError
        return generation

    async def _is_invalidating(self, connector_id: uuid.UUID) -> bool:
        async with self._lock:
            return connector_id in self._invalidating

    async def _flight_is_current(
        self, flight_key: tuple[CacheKey, int]
    ) -> bool:
        async with self._lock:
            return self._flights.get(flight_key) is asyncio.current_task()

    async def _remove_flight(self, flight_key: tuple[CacheKey, int]) -> None:
        async with self._lock:
            if self._flights.get(flight_key) is asyncio.current_task():
                self._flights.pop(flight_key)

    async def _forget_connector(self, connector_id: uuid.UUID) -> None:
        async with self._lock:
            self._forget_connector_unlocked(connector_id)

    def _forget_connector_unlocked(self, connector_id: uuid.UUID) -> None:
        self._flights = {
            flight_key: task
            for flight_key, task in self._flights.items()
            if flight_key[0].connector_id != connector_id
        }

    async def _listen_for_invalidations(self) -> None:
        while not self._closing:
            subscription: InvalidationSubscription | None = None
            try:
                subscription = await self._connection.subscribe(
                    self._namespace.invalidation_channel
                )
                self._available = True
                while not self._closing:
                    message = await subscription.next_message(timeout=1.0)
                    if message is None:
                        continue
                    try:
                        connector_id = uuid.UUID(message.decode())
                    except (UnicodeDecodeError, ValueError):
                        logger.warning("Ignoring an invalid cache invalidation message")
                        continue
                    await self._forget_connector(connector_id)
            except CacheConnectionError:
                self._failed()
            finally:
                if subscription is not None:
                    await subscription.aclose()
            if not self._closing:
                await asyncio.sleep(self._listener_retry_seconds)

    def _finish_task(self, task: asyncio.Task[object]) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            task.exception()

    def _result[T](
        self, value: T, status: CacheStatus, *, age_seconds: float = 0.0
    ) -> CacheResult[T]:
        self.observe(status)
        return CacheResult(value, status, age_seconds)

    def _failed(self) -> None:
        self._meter.failed()
        if self._available is not False:
            logger.warning("Shared cache unavailable; source reads will bypass it")
        self._available = False
