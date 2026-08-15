from app.adapters.catalog import CatalogNode
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.options import PostgresOptions
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.registry import register


class PostgresAdapter:
    """Facade over a session and the capabilities built on it.

    Deliberately thin: a new capability is a new module composed here, not
    another hundred lines in this class.
    """

    def __init__(self, options: PostgresOptions) -> None:
        self._session = PostgresSession(options)
        self._catalog = PostgresCatalog(self._session)

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)


@register(name="postgres", title="PostgreSQL", options_schema=PostgresOptions)
def _build(options: PostgresOptions) -> PostgresAdapter:
    return PostgresAdapter(options)
