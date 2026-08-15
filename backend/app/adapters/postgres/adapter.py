import asyncio
import time

import psycopg

from app.adapters.postgres.options import PostgresOptions
from app.adapters.protocol import ConnectionCheckResult, ErrorKind
from app.adapters.registry import register

CHECK_TIMEOUT_SECONDS = 5.0

# Order matters: `role "x" does not exist` matches both sets, and it is a
# credentials problem rather than a configuration one.
_AUTH_MARKERS = ("password", "authentication", "role", "permission denied")
_CONFIG_MARKERS = ("does not exist",)


def _classify(exc: BaseException) -> tuple[ErrorKind, str]:
    """Reduce a driver exception to a safe (kind, message) pair.

    The exception text never reaches the caller: psycopg includes the
    connection string, password and all, in it.
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
    return "unknown", "Connection failed"


class PostgresAdapter:
    def __init__(self, options: PostgresOptions) -> None:
        self._options = options

    def _conninfo(self) -> str:
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

    async def check_connection(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        try:
            connection = await asyncio.wait_for(
                psycopg.AsyncConnection.connect(self._conninfo()),
                CHECK_TIMEOUT_SECONDS,
            )
            async with connection:
                await connection.execute("SELECT 1")
        except Exception as exc:
            error_kind, message = _classify(exc)
            return ConnectionCheckResult(
                ok=False, message=message, error_kind=error_kind
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message="Connection successful", latency_ms=latency_ms
        )


@register(name="postgres", title="PostgreSQL", options_schema=PostgresOptions)
def _build(options: PostgresOptions) -> PostgresAdapter:
    return PostgresAdapter(options)
