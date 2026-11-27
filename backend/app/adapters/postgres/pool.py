"""Keeping PostgreSQL connections between requests.

Everything psycopg knows about pooling stays here, so the container that holds
the pool (`adapters/resources.py`) stays free of any driver, and the session
below asks for a pool without knowing where it is kept.
"""

import asyncio
import hashlib
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from app.adapters.resources import Pooling
from app.adapters.tls import TlsFiles, TlsSettings
from app.core.config import settings

# How long a caller waits for the pool to hand out a connection. Kept equal to
# the connection timeout of a direct attempt: from the outside the wait should
# not depend on whether a pool happens to exist.
ACQUIRE_TIMEOUT_SECONDS = 5.0


class PooledConnections:
    """A psycopg pool, configured the way this application wants one."""

    def __init__(
        self,
        conninfo: str,
        files: TlsFiles | None = None,
        credentials: Credentials | None = None,
    ) -> None:
        # libpq reads its key files at every connect, so they live as long as
        # the pool and go when it closes (D447).
        self._files = files
        self._pool: AsyncConnectionPool[AsyncConnection[Any]] = AsyncConnectionPool(
            conninfo,
            # Asked by psycopg_pool before every physical connection it opens,
            # so a token issued for fifteen minutes is never one the pool kept
            # since it was made (D450).
            kwargs=credentials,
            # Nothing is held for a connector nobody is looking at; the first
            # request pays for the connection, every later one does not.
            min_size=0,
            max_size=settings.POOL_MAX_SIZE,
            max_idle=settings.POOL_MAX_IDLE_SECONDS,
            timeout=ACQUIRE_TIMEOUT_SECONDS,
            # One round trip on checkout instead of a random failure after the
            # database has been restarted under a pool full of dead sockets.
            check=AsyncConnectionPool.check_connection,
            # Opening in the constructor is deprecated, and it would also make
            # construction do I/O inside the store's lock.
            open=False,
        )

    async def open(self) -> None:
        await self._pool.open()

    def connection(self) -> AbstractAsyncContextManager[AsyncConnection[Any]]:
        return self._pool.connection()

    async def close(self) -> None:
        try:
            await self._pool.close()
        finally:
            if self._files is not None:
                self._files.close()


# The user and password of the next connection, asked as it is opened.
type Credentials = Callable[[], Awaitable[dict[str, Any]]]


def key_for(connector_id: uuid.UUID, conninfo: str) -> str:
    """Where the pool of this connector, with these options, is kept.

    The connector is part of the key so that two users with the same
    credentials do not silently share connections. The options are part of it
    so that editing a password produces a different pool by itself: an
    invalidation step somewhere else is a step that can be forgotten.

    The options are hashed rather than kept: conninfo contains the password,
    and a key is the kind of value that ends up in a log eventually.
    """
    fingerprint = hashlib.sha256(conninfo.encode()).hexdigest()[:16]
    return f"postgres:{connector_id}:{fingerprint}"


async def pool_for(
    pooling: Pooling,
    conninfo: str,
    tls: TlsSettings,
    dial: Callable[[TlsFiles], str],
    credentials: Credentials | None = None,
) -> PooledConnections | None:
    """The connector's pool, or None where the store makes none to keep.

    A pool made for one search across many connections would be closed with
    it, and would hide a refused password behind its wait for a connection.
    Such a search uses the pool somebody already has, or connects on its own,
    as the metrics collector does (D127).

    `conninfo` is the key: the TLS files named by a digest of their PEMs, not
    by where a pool happens to write them, and never a password that is
    issued. `dial` is what the pool connects with once its files are
    written, and `credentials` what it signs in with at every connection.
    """
    key = key_for(pooling.connector_id, conninfo)
    if not pooling.store.keeps:
        return await pooling.store.existing(key, PooledConnections)

    async def create() -> PooledConnections:
        files = await asyncio.to_thread(TlsFiles, tls)
        pool = PooledConnections(dial(files), files, credentials)
        try:
            await pool.open()
        except BaseException:
            await pool.close()
            raise
        return pool

    return await pooling.store.get_or_create(key, PooledConnections, create)
