import asyncio
import time

import psycopg

from app.adapters.postgres.options import PostgresOptions
from app.adapters.protocol import ConnectionCheckResult, ErrorKind
from app.adapters.registry import register

CHECK_TIMEOUT_SECONDS = 5.0

# Порядок важен: role "x" does not exist содержит оба набора маркеров, и это
# ошибка учётных данных, а не конфигурации.
_AUTH_MARKERS = ("password", "authentication", "role", "permission denied")
_CONFIG_MARKERS = ("does not exist",)


def _classify(exc: BaseException) -> tuple[ErrorKind, str]:
    """Свести исключение драйвера к безопасной паре (вид, сообщение).

    Текст исключения наружу не передаётся: psycopg включает в него строку
    подключения вместе с паролем.
    """
    # ConnectionTimeout — подкласс OperationalError, поэтому проверяется раньше.
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
            # Без этого psycopg ждёт ответа недостижимого хоста около двух минут.
            # asyncio.wait_for ниже снял бы ожидание, но соединение продолжало бы
            # висеть в драйвере, поэтому предел задаётся с обеих сторон.
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
