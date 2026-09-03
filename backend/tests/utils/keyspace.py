"""Where the Redis tests find a server, and how they leave it.

A real server rather than a fake. What these tests are about is what the
driver does to a Redis — whether a scan groups by colons, whether an expiry
lands, whether a pipeline reads back what it wrote — and a fake would be this
repository's own idea of Redis being checked against itself.

Database 15 by default, and emptied around every test that uses it: the tests
are about a key space, so they need one nobody else is writing to.

Nothing here is named with pytest's prefix: a helper called
`test_redis_options` is a helper pytest calls as a test.
"""

import os
from collections.abc import AsyncGenerator
from urllib.parse import urlparse

import redis.asyncio as redis

from app.adapters.redis.options import RedisNoAuth, RedisOptions, RedisPassword

# Development runs it on the loopback through compose; CI reaches it by the
# service alias. The database is the last segment, deliberately not 0.
DEFAULT_URL = "redis://localhost:6379/15"


def redis_url() -> str:
    return os.environ.get("TEST_REDIS_URL", DEFAULT_URL)


def redis_options() -> RedisOptions:
    """The connection the tests use, as the source type's own options model."""
    parsed = urlparse(redis_url())
    database = int((parsed.path or "/15").lstrip("/") or 15)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    if parsed.password:
        return RedisPassword(
            auth_method="password",
            host=host,
            port=port,
            database=database,
            password=parsed.password,  # type: ignore[arg-type]
        )
    return RedisNoAuth(
        auth_method="no_auth", host=host, port=port, database=database
    )


def chosen_database() -> int:
    """The database the tests connect to, which their ids have to carry.

    Every id this source issues names its database (D91), so a test writing one
    out by hand would be writing a 15 that only happens to be 15 here.
    """
    return redis_options().database


async def empty_keyspace() -> AsyncGenerator[None]:
    """An empty database before the test and after it.

    Both ends: a test that fails half way through must not leave keys for the
    next one, and a test that starts on somebody's leftovers is a test about
    those.
    """
    await _flush()
    yield
    await _flush()


async def _flush() -> None:
    options = redis_options()
    password = (
        options.password.get_secret_value()
        if isinstance(options, RedisPassword)
        else None
    )
    client = redis.Redis(
        host=options.host,
        port=options.port,
        db=options.database,
        password=password,
    )
    try:
        await client.flushdb()
    finally:
        await client.aclose()

