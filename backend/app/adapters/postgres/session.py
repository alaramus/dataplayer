import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import PoolTimeout

from app.adapters.postgres.options import PostgresOptions
from app.adapters.postgres.pool import pool_for
from app.adapters.protocol import AdapterError, ConnectionCheckResult, ErrorKind
from app.adapters.resources import Pooling

CHECK_TIMEOUT_SECONDS = 5.0

# How this application introduces itself to the server it connects to.
APPLICATION_NAME = "dataplayer"

# Order matters: `role "x" does not exist` matches both sets, and it is a
# credentials problem rather than a configuration one.
_AUTH_MARKERS = ("password", "authentication", "role", "permission denied")
_CONFIG_MARKERS = ("does not exist",)


def classify(
    exc: BaseException, *, fallback_message: str = "Connection failed"
) -> tuple[ErrorKind, str]:
    """Reduce a driver exception to a safe (kind, message) pair.

    The exception text never reaches the caller: psycopg includes the
    connection string, password and all, in it.

    fallback_message covers everything that is not a connection problem. It is
    a parameter because "Connection failed" is misleading when the connection
    was fine and the query was not.
    """
    # ConnectionTimeout subclasses OperationalError, so it is checked first.
    if isinstance(exc, TimeoutError | psycopg.errors.ConnectionTimeout):
        return "timeout", "Connection timed out"
    if isinstance(exc, psycopg.OperationalError):
        text = str(exc).lower()
        if any(marker in text for marker in _AUTH_MARKERS):
            return "auth", "Authentication failed"
        if any(marker in text for marker in _CONFIG_MARKERS):
            return "config", "Database does not exist"
        return "network", "Could not reach the database server"
    return "unknown", fallback_message


class PostgresSession:
    """How to talk to a PostgreSQL server.

    Knows about connections, queries and driver errors, and nothing about what
    the caller wants: catalogs, fetching and everything after are built on top
    of this rather than inside it. In the old application both lived in one
    class, which reached 1243 lines even though backups, monitoring and
    extensions had already been moved out of it.
    """

    def __init__(self, options: PostgresOptions, pooling: Pooling | None = None) -> None:
        self._options = options
        # Absent for a draft being checked, and for a session a test builds by
        # hand: then every query connects on its own, as everything did before
        # sub-project 4b.
        self._pooling = pooling

    def conninfo(self) -> str:
        options = self._options
        return psycopg.conninfo.make_conninfo(
            host=options.host,
            port=options.port,
            dbname=options.database,
            user=options.user,
            password=options.password.get_secret_value(),
            # Without this psycopg waits about two minutes on an unreachable
            # host. asyncio.wait_for below would drop the wait, but the
            # connection would keep hanging inside the driver, so the limit is
            # set on both sides.
            connect_timeout=int(CHECK_TIMEOUT_SECONDS),
            # Since connections now outlive a request, someone looking at
            # pg_stat_activity should be able to tell whose they are.
            application_name=APPLICATION_NAME,
        )

    def connection_string(self) -> str:
        """The same address as `conninfo`, as a URL and without the password.

        Built with `quote` rather than by formatting: a user named `ann@corp`
        or a database named `a/b` would otherwise move the host or invent a
        path, and this string is meant to be pasted into other tools.
        """
        options = self._options
        user = quote(options.user, safe="")
        database = quote(options.database, safe="")
        host = quote(options.host, safe="")
        return f"postgresql://{user}@{host}:{options.port}/{database}"

    async def check(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        try:
            connection = await asyncio.wait_for(
                psycopg.AsyncConnection.connect(self.conninfo()),
                CHECK_TIMEOUT_SECONDS,
            )
            async with connection:
                await connection.execute("SELECT 1")
        except Exception as exc:
            error_kind, message = classify(exc)
            return ConnectionCheckResult(
                ok=False, message=message, error_kind=error_kind
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message="Connection successful", latency_ms=latency_ms
        )

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator[psycopg.AsyncConnection[Any]]:
        """A connection to work on: from the pool when there is one."""
        if self._pooling is None:
            connection = await asyncio.wait_for(
                psycopg.AsyncConnection.connect(self.conninfo()),
                CHECK_TIMEOUT_SECONDS,
            )
            async with connection:
                yield connection
            return

        pool = await pool_for(self._pooling, self.conninfo())
        async with pool.connection() as connection:
            yield connection

    async def query(
        self, sql: str, params: tuple[object, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Run a read-only query.

        params stays None when there is nothing to bind: psycopg treats a
        supplied sequence, even an empty one, as a signal that the statement is
        parameterised, and then a literal % — as in LIKE 'pg_toast%' — is read
        as a placeholder.
        """
        try:
            async with self._connection() as connection:
                cursor = await connection.cursor(row_factory=dict_row).execute(
                    sql, params
                )
                return await cursor.fetchall()
        except PoolTimeout:
            error_kind, message = await self._why_no_connection()
            raise AdapterError(error_kind, message) from None
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message="Query failed")
            raise AdapterError(error_kind, message) from None

    async def _why_no_connection(self) -> tuple[ErrorKind, str]:
        """Ask the server once, on the failure path, what is actually wrong.

        A pool that cannot connect reports only that it had nothing to hand
        out; the reason the attempt failed stays inside it. Reporting a typo in
        a password as an unreachable host would send the user to check the
        wrong thing, so one direct attempt buys the real answer. Nothing on the
        successful path pays for this.
        """
        try:
            connection = await asyncio.wait_for(
                psycopg.AsyncConnection.connect(self.conninfo()),
                CHECK_TIMEOUT_SECONDS,
            )
            async with connection:
                pass
        except Exception as exc:
            return classify(exc, fallback_message="Query failed")
        # The server is reachable and the credentials work, so the wait was for
        # a free connection rather than for the server.
        return "unknown", "All connections to this source are busy"
