"""The Redis driver boundary for the optional shared application cache."""

import inspect
from collections.abc import AsyncIterator, Awaitable
from typing import Any, NamedTuple, Protocol, cast

import redis.asyncio as redis
from redis.exceptions import RedisError


class CacheConnectionError(RuntimeError):
    """A Redis cache operation failed; driver details stay behind this boundary."""


class StoredEntry(NamedTuple):
    """A value the cache still holds, and how much of its life is left.

    The remaining life is read in the same round trip as the value, because
    the two are only comparable when nothing happened between them; how old
    the entry is follows from what it was stored for (D105).
    """

    payload: bytes
    expires_in_ms: int


class InvalidationSubscription(Protocol):
    # The waiting is the driver's, not this function's: `timeout` travels to
    # `pubsub.get_message`, which is what blocks and what returns None when
    # nothing arrived. `asyncio.timeout` around the call would cancel the read
    # instead of asking it to come back empty, which is a different thing - so
    # the rule that says an async function should not take a timeout does not
    # describe this one.
    async def next_message(self, *, timeout: float) -> bytes | None: ...  # noqa: ASYNC109

    async def aclose(self) -> None: ...


class SharedCacheConnection(Protocol):
    async def get(self, key: str) -> bytes | None: ...

    async def read_entry(self, key: str, *, lru_key: str) -> StoredEntry | None: ...

    async def write_entry(
        self,
        key: str,
        value: bytes,
        *,
        ttl_ms: int,
        lru_key: str,
        max_entries: int,
    ) -> None: ...

    async def delete_entry(self, key: str, *, lru_key: str) -> None: ...

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


# These scripts are fixed application code, not input. Entry value and LRU
# membership change atomically, so concurrent workers cannot exceed the hard
# bound or leave a deleted value live in the index (D31, D102).
_READ_ENTRY = """
local value = redis.call('GET', KEYS[1])
if value then
  local now = redis.call('TIME')
  local score = tonumber(now[1]) * 1000000 + tonumber(now[2])
  redis.call('ZADD', KEYS[2], score, KEYS[1])
  return {value, redis.call('PTTL', KEYS[1])}
end
redis.call('ZREM', KEYS[2], KEYS[1])
return nil
"""

_WRITE_ENTRY = """
redis.call('SET', KEYS[1], ARGV[1], 'PX', ARGV[2])
local now = redis.call('TIME')
local score = tonumber(now[1]) * 1000000 + tonumber(now[2])
redis.call('ZADD', KEYS[2], score, KEYS[1])
while redis.call('ZCARD', KEYS[2]) > tonumber(ARGV[3]) do
  local oldest = redis.call('ZPOPMIN', KEYS[2], 1)
  if oldest[1] then
    redis.call('DEL', oldest[1])
  end
end
return 1
"""

_DELETE_ENTRY = """
redis.call('DEL', KEYS[1])
redis.call('ZREM', KEYS[2], KEYS[1])
return 1
"""


class RedisInvalidationSubscription:
    def __init__(self, pubsub: redis.client.PubSub) -> None:
        self._pubsub = pubsub

    async def subscribe(self, channel: str) -> None:
        await _command(self._pubsub.subscribe(channel))

    async def next_message(self, *, timeout: float) -> bytes | None:  # noqa: ASYNC109
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
            # redis-py leaves PubSub.aclose unannotated, so a strict call site
            # sees an untyped function where there is an ordinary coroutine.
            await _command(self._pubsub.aclose())  # type: ignore[no-untyped-call]
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

    async def read_entry(self, key: str, *, lru_key: str) -> StoredEntry | None:
        found: Any = await _command(self._client.eval(_READ_ENTRY, 2, key, lru_key))
        if found is None:
            return None
        if not isinstance(found, list) or len(found) != 2:
            raise CacheConnectionError
        payload, remaining = found
        if not isinstance(payload, bytes) or not isinstance(remaining, int):
            raise CacheConnectionError
        # A key with no expiry answers -1 and one already gone answers -2.
        # Neither can be an age, so both are read as an entry stored just now.
        return StoredEntry(payload, max(remaining, 0))

    async def write_entry(
        self,
        key: str,
        value: bytes,
        *,
        ttl_ms: int,
        lru_key: str,
        max_entries: int,
    ) -> None:
        await _command(
            self._client.eval(
                _WRITE_ENTRY,
                2,
                key,
                lru_key,
                value,
                ttl_ms,
                max_entries,
            )
        )

    async def delete_entry(self, key: str, *, lru_key: str) -> None:
        await _command(self._client.eval(_DELETE_ENTRY, 2, key, lru_key))

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
