from pathlib import Path

from app.adapters.catalog import CatalogNode
from app.adapters.content import ContentRequest, ContentResult
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.registry import AdapterContext, register
from app.adapters.relation import RelationModel, RelationModelsRequest
from app.adapters.sqlite.catalog import SqliteCatalog
from app.adapters.sqlite.content import SqliteContent
from app.adapters.sqlite.features import SqliteFeatures
from app.adapters.sqlite.fetch import SqliteFetch
from app.adapters.sqlite.options import SqliteOptions
from app.adapters.sqlite.relation import SqliteRelation
from app.adapters.sqlite.session import SqliteSession
from app.adapters.sqlite.summary import SqliteSummaries
from app.adapters.summary import NodeSummary
from app.core.translation import N_


class SqliteAdapter:
    """Facade over a session and the capabilities built on it (D2b).

    What a source of this type cannot do yet it does not claim: a capability
    arrives as a module composed here, and the registry reads it off the class.
    No read cache: the file is on this server's disk, and it can be replaced
    by an upload no connection hears of (D105).
    """

    def __init__(self, options: SqliteOptions, home_dir: Path) -> None:
        self._session = SqliteSession(options, home_dir)
        self._features = SqliteFeatures()
        self._catalog = SqliteCatalog(self._session)
        self._relation = SqliteRelation(self._session)
        self._fetch = SqliteFetch(self._session, self._relation)
        self._content = SqliteContent(self._session, self._relation)
        self._summaries = SqliteSummaries(self._relation)

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def source_features(self) -> SourceFeatures:
        return await self._features.source_features()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return await self._catalog.path_to(node_id)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return await self._fetch.fetch(request)

    async def relation_model(self, node_id: str) -> RelationModel:
        return await self._relation.relation_model(node_id)

    async def relation_models_for_nodes(
        self, request: RelationModelsRequest
    ) -> list[RelationModel]:
        return await self._relation.relation_models_for_nodes(request.node_ids)

    async def node_summary(self, node_id: str) -> NodeSummary:
        return await self._summaries.node_summary(node_id)

    async def read_content(self, request: ContentRequest) -> ContentResult:
        return await self._content.read_content(request)


@register(
    name="sqlite",
    title=N_("SQLite"),
    category="sql",
    description=N_(
        "A SQLite database file in your personal storage. Browse its tables and "
        "views, and read rows a page at a time with sorting and filtering."
    ),
    options_schema=SqliteOptions,
    adapter_class=SqliteAdapter,
)
def _build(options: SqliteOptions, context: AdapterContext) -> SqliteAdapter:
    return SqliteAdapter(options, context.home_dir)
