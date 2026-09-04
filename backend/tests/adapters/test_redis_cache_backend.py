import asyncio
import os
import uuid
from dataclasses import dataclass, field

import pytest

from app.adapters.cache import CacheKey, DataCache
from app.adapters.cache_serialization import CacheCipher, CacheFormat, CacheNamespace
from app.adapters.redis.cache import RedisDataCache
from app.adapters.redis.cache_connection import (
    CacheConnectionError,
    InvalidationSubscription,
    RedisCacheConnection,
)

TEXT_FORMAT: CacheFormat[str] = CacheFormat(str)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL")


@dataclass
class FakeRedis:
    values: dict[str, bytes] = field(default_factory=dict)
    subscribers: dict[str, list[asyncio.Queue[bytes]]] = field(default_factory=dict)
    publications: list[tuple[str, bytes]] = field(default_factory=list)
    failing: bool = False


class FakeSubscription:
    def __init__(self, queue: asyncio.Queue[bytes]) -> None:
        self._queue = queue

    async def next_message(self, *, timeout: float) -> bytes | None:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout)
        except TimeoutError:
            return None

    async def aclose(self) -> None:
        pass


class FakeConnection:
    def __init__(self, server: FakeRedis) -> None:
        self._server = server

    def _check(self) -> None:
        if self._server.failing:
            raise CacheConnectionError

    async def get(self, key: str) -> bytes | None:
        self._check()
        return self._server.values.get(key)

    async def set(self, key: str, value: bytes, *, ttl_ms: int) -> None:
        self._check()
        assert ttl_ms > 0
        self._server.values[key] = value

    async def delete(self, key: str) -> None:
        self._check()
        self._server.values.pop(key, None)

    async def increment(self, key: str) -> int:
        self._check()
        value = int(self._server.values.get(key, b"0")) + 1
        self._server.values[key] = str(value).encode()
        return value

    async def publish(self, channel: str, message: bytes) -> None:
        self._check()
        self._server.publications.append((channel, message))
        for queue in self._server.subscribers.get(channel, []):
            queue.put_nowait(message)

    async def subscribe(self, channel: str) -> InvalidationSubscription:
        self._check()
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._server.subscribers.setdefault(channel, []).append(queue)
        return FakeSubscription(queue)

    async def count(self, prefix: str) -> int:
        self._check()
        return sum(
            name.startswith(f"{prefix}:user:") for name in self._server.values
        )

    async def ping(self) -> None:
        self._check()

    async def aclose(self) -> None:
        pass


def make_cache(server: FakeRedis) -> RedisDataCache:
    return RedisDataCache(
        FakeConnection(server),
        namespace=CacheNamespace("test"),
        cipher=CacheCipher(b"k" * 32),
        listener_retry_seconds=0.01,
    )


def key(connector_id: uuid.UUID) -> CacheKey:
    return CacheKey(
        owner_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        connector_id=connector_id,
        area="fetch",
        request='{\"node_id\":\"public.people\"}',
    )


async def test_two_workers_share_values_and_connector_invalidation() -> None:
    server = FakeRedis()
    first = make_cache(server)
    second = make_cache(server)
    first.start()
    second.start()
    await asyncio.sleep(0)
    connector_id = uuid.uuid4()
    cache_key = key(connector_id)
    try:
        loaded = await first.get_or_load(
            cache_key,
            ttl_seconds=30,
            load=lambda: asyncio.sleep(0, result="Ada Lovelace"),
            cache_format=TEXT_FORMAT,
        )
        shared = await second.get_or_load(
            cache_key,
            ttl_seconds=30,
            load=lambda: asyncio.sleep(0, result="wrong"),
            cache_format=TEXT_FORMAT,
        )

        stored_values = [
            value for name, value in server.values.items() if ":user:" in name
        ]
        assert (loaded.value, loaded.status) == ("Ada Lovelace", "miss")
        assert (shared.value, shared.status) == ("Ada Lovelace", "hit")
        assert all(b"Ada Lovelace" not in value for value in stored_values)

        await second.invalidate_connector(connector_id)
        await asyncio.sleep(0)
        refreshed = await first.get_or_load(
            cache_key,
            ttl_seconds=30,
            load=lambda: asyncio.sleep(0, result="Grace Hopper"),
            cache_format=TEXT_FORMAT,
        )

        assert (refreshed.value, refreshed.status) == ("Grace Hopper", "miss")
        assert server.publications == [
            ("dataplayer:test:cache:v1:invalidate", str(connector_id).encode())
        ]
        assert isinstance(first, DataCache)
    finally:
        await first.aclose()
        await second.aclose()


async def test_cross_worker_invalidation_does_not_restore_an_old_flight() -> None:
    server = FakeRedis()
    first = make_cache(server)
    second = make_cache(server)
    first.start()
    second.start()
    await asyncio.sleep(0)
    connector_id = uuid.uuid4()
    cache_key = key(connector_id)
    started = asyncio.Event()
    release = asyncio.Event()

    async def old_read() -> str:
        started.set()
        await release.wait()
        return "old"

    try:
        loading = asyncio.create_task(
            first.get_or_load(
                cache_key,
                ttl_seconds=30,
                load=old_read,
                cache_format=TEXT_FORMAT,
            )
        )
        await started.wait()
        await second.invalidate_connector(connector_id)
        await asyncio.sleep(0)
        fresh = await second.get_or_load(
            cache_key,
            ttl_seconds=30,
            load=lambda: asyncio.sleep(0, result="fresh"),
            cache_format=TEXT_FORMAT,
        )
        release.set()

        assert (await loading).value == "old"
        assert fresh.value == "fresh"
        reused = await first.get_or_load(
            cache_key,
            ttl_seconds=30,
            load=lambda: asyncio.sleep(0, result="wrong"),
            cache_format=TEXT_FORMAT,
        )
        assert (reused.value, reused.status) == ("fresh", "hit")
    finally:
        release.set()
        await first.aclose()
        await second.aclose()


async def test_redis_failure_bypasses_cache_and_never_fails_data_access() -> None:
    server = FakeRedis(failing=True)
    cache = make_cache(server)
    connector_id = uuid.uuid4()
    cache_key = key(connector_id)
    try:
        result = await cache.get_or_load(
            cache_key,
            ttl_seconds=30,
            load=lambda: asyncio.sleep(0, result="direct"),
            cache_format=TEXT_FORMAT,
        )
        await cache.invalidate_connector(connector_id)
        health = await cache.health()

        assert (result.value, result.status) == ("direct", "bypass")
        assert cache.available is False
        assert health.status == "degraded"
        assert health.shared is True
    finally:
        await cache.aclose()


@pytest.mark.skipif(TEST_REDIS_URL is None, reason="TEST_REDIS_URL not configured")
async def test_two_cache_instances_observe_real_redis_invalidation() -> None:
    """The phase exit condition against the Redis service used by CI."""
    assert TEST_REDIS_URL is not None
    deployment = f"phase5-{uuid.uuid4().hex}"
    namespace = CacheNamespace(deployment)
    connector_id = uuid.uuid4()
    cache_key = key(connector_id)
    first = RedisDataCache.from_url(
        TEST_REDIS_URL,
        deployment=deployment,
        encryption_key=b"r" * 32,
        timeout_seconds=1,
    )
    second = RedisDataCache.from_url(
        TEST_REDIS_URL,
        deployment=deployment,
        encryption_key=b"r" * 32,
        timeout_seconds=1,
    )
    first.start()
    second.start()
    try:
        await first.get_or_load(
            cache_key,
            ttl_seconds=2,
            load=lambda: asyncio.sleep(0, result="before"),
            cache_format=TEXT_FORMAT,
        )
        shared = await second.get_or_load(
            cache_key,
            ttl_seconds=2,
            load=lambda: asyncio.sleep(0, result="wrong"),
            cache_format=TEXT_FORMAT,
        )
        await second.invalidate_connector(connector_id)
        after = await first.get_or_load(
            cache_key,
            ttl_seconds=2,
            load=lambda: asyncio.sleep(0, result="after"),
            cache_format=TEXT_FORMAT,
        )

        assert (shared.value, shared.status) == ("before", "hit")
        assert (after.value, after.status) == ("after", "miss")
    finally:
        await first.aclose()
        await second.aclose()
        cleanup = RedisCacheConnection(TEST_REDIS_URL, timeout_seconds=1)
        try:
            await cleanup.delete(namespace.generation_key(connector_id))
        except CacheConnectionError:
            pass
        finally:
            await cleanup.aclose()
