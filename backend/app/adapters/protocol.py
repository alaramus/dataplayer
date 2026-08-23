from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from app.adapters.catalog import CatalogNode
from app.adapters.fetch import FetchRequest, FetchResult

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

        Raises AdapterError for source failures and ValueError for a node_id
        the source cannot or may not reach — a path leaving the root of a file
        source, for instance. An empty list means an empty node, never a
        failure: the old application returned an empty result for both.
        """
        ...


@runtime_checkable
class SupportsFetch(Protocol):
    async def fetch(self, request: FetchRequest) -> FetchResult:
        """Read a page of rows.

        Raises AdapterError for source failures and ValueError for a request
        that names a column the relation does not have — that check happens
        before any SQL is built.
        """
        ...


@runtime_checkable
class SupportsConnectionString(Protocol):
    def connection_string(self) -> str:
        """How to reach this source, in one line, for a human to copy.

        Never carries the password: it is shown on screen and pasted into
        other tools, and the one place that composes it is the one place
        already obliged to keep the password out of anything the caller sees.

        A capability rather than part of the contract because a source may
        genuinely have none — a personal directory is not addressed by a URL,
        and answering with an invented one would be worse than answering 501.
        """
        ...


@runtime_checkable
class ParsesConnectionString(Protocol):
    """A source type that can take a pasted address apart again.

    Asked of the class, not of an instance: an adapter cannot be built until
    there are options, and parsing is what produces them. The same reason
    `action_types` is a classmethod — and, as there, a classmethod rather than
    data so that `issubclass` can answer it.

    The answer is options in the shape the schema declares, discriminator
    included: which way of connecting a string describes is the driver's
    inference. A form that read it off the presence of a substring would be
    the `isFieldShowing` of the old application.

    Raises ValueError for a string the driver cannot read as an address. What
    counts as one is the driver's own rule; nothing here inspects the text.
    """

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]: ...
