from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from app.adapters.catalog import CatalogNode

ErrorKind = Literal["auth", "network", "timeout", "config", "unknown"]


class AdapterError(Exception):
    """Failure of an adapter operation, already reduced to safe values.

    Raised instead of letting a driver exception escape: driver messages
    regularly contain the connection string together with the password.
    """

    def __init__(self, error_kind: ErrorKind, message: str) -> None:
        super().__init__(message)
        self.error_kind = error_kind
        self.message = message


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
    """What every source can do, whatever it is.

    Kept to the minimum on purpose. Everything else is an optional capability
    below, because capabilities are independent: a queue has no columns, an
    object store has no SQL. A single contract that demanded all of them would
    force meaningless implementations, and a single inheritance chain would
    force them into one line — which is how the old application ended up with
    four levels of base classes.
    """

    async def check_connection(self) -> ConnectionCheckResult: ...


@runtime_checkable
class SupportsCatalog(Protocol):
    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        """Children of a catalog node; the root when node_id is None.

        Raises AdapterError. An empty list means an empty node, never a
        failure — the old application returned an empty result for both.
        """
        ...
