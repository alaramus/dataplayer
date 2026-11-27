"""Keeping MySQL connections between requests.

Everything aiomysql knows about pooling stays here, as psycopg's pooling stays
in the PostgreSQL adapter; the container that holds a pool knows no driver.
"""

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any

import aiomysql

from app.adapters.resources import Pooling
from app.core.config import settings

# Equal to the timeout of a direct attempt, for the reason PostgreSQL's is.
ACQUIRE_TIMEOUT_SECONDS = 5.0


class PoolExhausted(Exception):
    """Every connection of the pool stayed in use for the whole wait."""


class PooledConnections:
    """An aiomysql pool, configured the way this application wants one."""

    def __init__(self, pool: aiomysql.Pool, credentials: Credentials | None = None) -> None:
        self._pool = pool
        self._credentials = credentials

    @classmethod
    async def create(
        cls, connect: Mapping[str, Any], credentials: Credentials | None = None
    ) -> PooledConnections:
        signed = {} if credentials is None else await credentials()
        pool = await aiomysql.create_pool(
            minsize=0,
            maxsize=settings.POOL_MAX_SIZE,
            # A connection idle past this is closed on the next checkout
            # rather than found dead by the query that gets it.
            pool_recycle=int(settings.POOL_MAX_IDLE_SECONDS),
            **connect,
            **signed,
        )
        return cls(pool, credentials)

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiomysql.Connection]:
        # aiomysql opens a connection with the arguments it was made with,
        # read again at every connection it opens: a token issued for fifteen
        # minutes is put there before every checkout, so whatever it opens
        # next signs in with one that is still good (D450). A private
        # attribute, because aiomysql takes no callable for them.
        if self._credentials is not None:
            self._pool._conn_kwargs.update(await self._credentials())
        # aiomysql waits for a free connection without a limit of its own.
        try:
            connection = await asyncio.wait_for(
                self._pool.acquire(), ACQUIRE_TIMEOUT_SECONDS
            )
        except TimeoutError:
            raise PoolExhausted from None
        try:
            yield connection
        finally:
            self._pool.release(connection)

    async def close(self) -> None:
        self._pool.close()
        await self._pool.wait_closed()


# The user and password of the next connection, asked as it is opened.
type Credentials = Callable[[], Awaitable[dict[str, Any]]]


def key_for(connector_id: uuid.UUID, fingerprint_source: str) -> str:
    """Where the pool of this connector, with these options, is kept.

    The options are hashed, as PostgreSQL's are: the source of the fingerprint
    carries the password, and a key ends up in a log eventually.
    """
    fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()[:16]
    return f"mysql:{connector_id}:{fingerprint}"


async def pool_for(
    pooling: Pooling,
    fingerprint_source: str,
    connect: Mapping[str, Any],
    credentials: Credentials | None = None,
) -> PooledConnections | None:
    """The connector's pool, or None where the store makes none to keep (D127)."""
    key = key_for(pooling.connector_id, fingerprint_source)
    if not pooling.store.keeps:
        return await pooling.store.existing(key, PooledConnections)

    async def create() -> PooledConnections:
        return await PooledConnections.create(connect, credentials)

    return await pooling.store.get_or_create(key, PooledConnections, create)
