from collections.abc import Mapping
from typing import Any

from app.adapters.catalog import CatalogNode
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.fetch import PostgresFetch
from app.adapters.postgres.options import PostgresOptions
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.postgres.session import (
    PostgresSession,
    compose_url,
    options_from_url,
)
from app.adapters.postgres.update import PostgresUpdate
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.registry import AdapterContext, register
from app.adapters.relation import RelationModel
from app.adapters.resources import Pooling
from app.adapters.update import (
    DeleteRowsRequest,
    DeleteRowsResult,
    InsertRowRequest,
    InsertRowResult,
    UpdateCellRequest,
    UpdateCellResult,
)


def _as_text(value: Any) -> str:
    """A form value read as text, or nothing when it is not text yet."""
    return value if isinstance(value, str) else ""


def _as_port(value: Any) -> int | None:
    """A form value read as a port, or nothing when it is not one yet.

    A number typed into a field arrives as a string until it parses, and an
    untouched numeric field arrives as null.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


class PostgresAdapter:
    """Facade over a session and the capabilities built on it.

    Deliberately thin: a new capability is a new module composed here, not
    another hundred lines in this class.
    """

    def __init__(
        self, options: PostgresOptions, pooling: Pooling | None = None
    ) -> None:
        self._session = PostgresSession(options, pooling)
        self._catalog = PostgresCatalog(self._session)
        self._fetch = PostgresFetch(self._session)
        self._update = PostgresUpdate(self._session, self._fetch)
        self._relation = PostgresRelation(self._session)

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]:
        """Asked of the class: parsing is what produces the options."""
        return options_from_url(url)

    @classmethod
    def draft_connection_string(cls, options: Mapping[str, Any]) -> str | None:
        """The address of a form that does not validate yet.

        The values arrive as the form holds them, so every one of them is
        checked here rather than assumed: a port half-typed as "65" is a
        string, and a field never touched is absent. What cannot be read is
        left out of the address instead of stopping it — the point is to show
        as much as there is.

        Composed by `compose_url`, the same function the finished address goes
        through, so the two agree on the quoting by construction.
        """
        host = options.get("host")
        if not isinstance(host, str) or host == "":
            return None
        return compose_url(
            host=host,
            port=_as_port(options.get("port")),
            user=_as_text(options.get("user")),
            database=_as_text(options.get("database")),
        )

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    def connection_string(self) -> str:
        return self._session.connection_string()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return await self._catalog.path_to(node_id)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return await self._fetch.fetch(request)

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        return await self._update.update_cell(request)

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        return await self._update.insert_row(request)

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        return await self._update.delete_rows(request)

    async def relation_model(self, node_id: str) -> RelationModel:
        return await self._relation.relation_model(node_id)


@register(
    name="postgres",
    title="PostgreSQL",
    category="sql",
    description=(
        "Relational database. Browse schemas, tables and views, and read "
        "rows a page at a time with sorting and filtering done by the server."
    ),
    options_schema=PostgresOptions,
    adapter_class=PostgresAdapter,
)
def _build(options: PostgresOptions, context: AdapterContext) -> PostgresAdapter:
    return PostgresAdapter(options, context.pooling)
