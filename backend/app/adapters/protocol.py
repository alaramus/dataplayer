from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

ErrorKind = Literal["auth", "network", "timeout", "config", "unknown"]


class ConnectionCheckResult(BaseModel):
    """Итог проверки соединения.

    Драйверы никогда не выпускают наружу собственные исключения: их текст
    регулярно содержит строку подключения вместе с паролем.
    """

    ok: bool
    message: str
    latency_ms: int | None = None
    error_kind: ErrorKind | None = None


@runtime_checkable
class DataAdapter(Protocol):
    async def check_connection(self) -> ConnectionCheckResult: ...
