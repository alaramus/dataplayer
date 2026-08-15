import asyncio
import time
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.adapters.postgres.options import PostgresOptions
from app.adapters.protocol import AdapterError, ConnectionCheckResult, ErrorKind

CHECK_TIMEOUT_SECONDS = 5.0

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

    def __init__(self, options: PostgresOptions) -> None:
        self._options = options

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
        )

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
            connection = await asyncio.wait_for(
                psycopg.AsyncConnection.connect(self.conninfo()),
                CHECK_TIMEOUT_SECONDS,
            )
            async with connection:
                cursor = await connection.cursor(row_factory=dict_row).execute(
                    sql, params
                )
                return await cursor.fetchall()
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message="Query failed")
            raise AdapterError(error_kind, message) from None
