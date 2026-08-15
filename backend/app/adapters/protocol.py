from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

ErrorKind = Literal["auth", "network", "timeout", "config", "unknown"]


class ConnectionCheckResult(BaseModel):
    """Outcome of a connection check.

    Drivers never let their own exceptions escape: the text of those regularly
    contains the connection string together with the password.
    """

    ok: bool
    message: str
    latency_ms: int | None = None
    error_kind: ErrorKind | None = None


@runtime_checkable
class DataAdapter(Protocol):
    async def check_connection(self) -> ConnectionCheckResult: ...
