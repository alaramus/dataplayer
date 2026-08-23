from app.adapters.catalog import CatalogNode
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.fetch import PostgresFetch
from app.adapters.postgres.options import PostgresOptions
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.registry import AdapterContext, register
from app.adapters.resources import Pooling


class PostgresAdapter:
    """Facade over a session and the capabilities built on it.

    Deliberately thin: a new capability is a new module composed here, not
    another hundred lines in this class.
    """

    def __init__(self, options: PostgresOptions, pooling: Pooling | None = None) -> None:
        self._session = PostgresSession(options, pooling)
        self._catalog = PostgresCatalog(self._session)
        self._fetch = PostgresFetch(self._session)

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return await self._fetch.fetch(request)


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
