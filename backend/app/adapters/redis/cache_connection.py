"""The Redis driver boundary for the optional shared application cache."""

import inspect
from collections.abc import AsyncIterator, Awaitable
from typing import Any, Protocol, cast

import redis.asyncio as redis
from redis.exceptions import RedisError


class CacheConnectionError(RuntimeError):
    """A Redis cache operation failed; driver details stay behind this boundary."""


class InvalidationSubscription(Protocol):
    async def next_message(self, *, timeout: float) -> bytes | None: ...

    async def aclose(self) -> None: ...


class SharedCacheConnection(Protocol):
    async def get(self, key: str) -> bytes | None: ...

    async def set(self, key: str, value: bytes, *, ttl_ms: int) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def increment(self, key: str) -> int: ...

    async def publish(self, channel: str, message: bytes) -> None: ...

    async def subscribe(self, channel: str) -> InvalidationSubscription: ...

    async def count(self, prefix: str) -> int: ...

    async def ping(self) -> None: ...

    async def aclose(self) -> None: ...


async def _resolved[T](value: Awaitable[T] | T) -> T:
    if inspect.isawaitable(value):
        return await value
    return value


async def _command[T](value: Awaitable[T] | T) -> T:
    try:
        return await _resolved(value)
    except RedisError:
        # A driver message may include the configured address and password.
        raise CacheConnectionError from None


class RedisInvalidationSubscription:
    def __init__(self, pubsub: redis.client.PubSub) -> None:
        self._pubsub = pubsub

    async def subscribe(self, channel: str) -> None:
        await _command(self._pubsub.subscribe(channel))

    async def next_message(self, *, timeout: float) -> bytes | None:
        message: Any = await _command(
            self._pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=timeout,
            )
        )
        if not isinstance(message, dict):
            return None
        data: Any = message.get("data")
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            return data.encode()
        return None

    async def aclose(self) -> None:
        try:
            await _command(self._pubsub.aclose())
        except CacheConnectionError:
            pass


class RedisCacheConnection:
    """The commands the shared-cache algorithm is allowed to issue."""

    def __init__(self, url: str, *, timeout_seconds: float) -> None:
        self._client = redis.Redis.from_url(
            url,
            decode_responses=False,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
        )

    async def get(self, key: str) -> bytes | None:
        value: Any = await _command(self._client.get(key))
        if value is None:
            return None
        if not isinstance(value, bytes):
            raise CacheConnectionError
        return value

    async def set(self, key: str, value: bytes, *, ttl_ms: int) -> None:
        await _command(self._client.set(key, value, px=ttl_ms))

    async def delete(self, key: str) -> None:
        await _command(self._client.delete(key))

    async def increment(self, key: str) -> int:
        value: Any = await _command(self._client.incr(key))
        if not isinstance(value, int):
            raise CacheConnectionError
        return value

    async def publish(self, channel: str, message: bytes) -> None:
        await _command(self._client.publish(channel, message))

    async def subscribe(self, channel: str) -> InvalidationSubscription:
        subscription = RedisInvalidationSubscription(self._client.pubsub())
        await subscription.subscribe(channel)
        return subscription

    async def count(self, prefix: str) -> int:
        count = 0
        iterator = cast(
            AsyncIterator[bytes], self._client.scan_iter(match=f"{prefix}:user:*")
        )
        try:
            async for _key in iterator:
                count += 1
        except RedisError:
            raise CacheConnectionError from None
        return count

    async def ping(self) -> None:
        await _command(self._client.ping())

    async def aclose(self) -> None:
        try:
            await _command(self._client.aclose())
        except CacheConnectionError:
            pass
