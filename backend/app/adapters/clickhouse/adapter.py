from collections.abc import Mapping
from typing import Any

from app.adapters.cache import CacheArea
from app.adapters.catalog import CatalogNode
from app.adapters.clickhouse.catalog import ClickhouseCatalog
from app.adapters.clickhouse.content import ClickhouseContent
from app.adapters.clickhouse.explain import ClickhouseExplain
from app.adapters.clickhouse.features import ClickhouseFeatures
from app.adapters.clickhouse.fetch import ClickhouseFetch
from app.adapters.clickhouse.metadata import ClickhouseGeneration, ClickhouseMetadata
from app.adapters.clickhouse.options import ClickhouseOptions
from app.adapters.clickhouse.query import ClickhouseExecution, ClickhouseQuery
from app.adapters.clickhouse.relation import ClickhouseRelation
from app.adapters.clickhouse.session import (
    ClickhouseSession,
    compose_url,
    compose_url_with_password,
    options_from_url,
)
from app.adapters.clickhouse.statements import format_text
from app.adapters.clickhouse.summary import ClickhouseSummaries
from app.adapters.content import ContentRequest, ContentResult
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.query import (
    ExplainRequest,
    ExplainResult,
    GeneratedQuery,
    GenerateQueryRequest,
    PreparedScript,
    QueryMetadata,
    QueryMetadataRequest,
    QueryProfile,
    QueryRequest,
)
from app.adapters.registry import AdapterContext, register
from app.adapters.relation import RelationModel, RelationModelsRequest
from app.adapters.resources import Pooling
from app.adapters.summary import NodeSummary
from app.core.translation import N_


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_port(value: Any) -> int | None:
    """A form value read as a port, as PostgreSQL's draft reads one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


class ClickhouseAdapter:
    """Facade over a session and the capabilities built on it (D2b).

    What a source of this type cannot do yet it does not claim: a capability
    arrives as a module composed here, and the registry reads it off the class.
    """

    def __init__(self, options: ClickhouseOptions, pooling: Pooling | None = None) -> None:
        self._session = ClickhouseSession(options, pooling)
        self._features = ClickhouseFeatures(self._session)
        self._catalog = ClickhouseCatalog(self._session)
        self._relation = ClickhouseRelation(self._session)
        self._fetch = ClickhouseFetch(self._session, self._relation)
        self._content = ClickhouseContent(self._session, self._relation)
        self._summaries = ClickhouseSummaries(self._session, self._relation)
        self._query = ClickhouseQuery(self._session)
        self._explain = ClickhouseExplain(self._session)
        self._metadata = ClickhouseMetadata(self._session)
        self._generation = ClickhouseGeneration(self._session)

    @classmethod
    def cache_ttl(cls, area: CacheArea) -> float:
        """The windows PostgreSQL keeps, for the same kinds of answer."""
        if area in {"metadata", "relation"}:
            return 300.0
        return 30.0 if area == "catalog" else 10.0

    @classmethod
    def options_from_url(cls, url: str) -> dict[str, Any]:
        return options_from_url(url)

    @classmethod
    def draft_connection_string(cls, options: Mapping[str, Any]) -> str | None:
        host = options.get("host")
        if not isinstance(host, str) or host == "":
            return None
        return compose_url(
            host=host,
            port=_as_port(options.get("port")),
            user=_as_text(options.get("user")),
            database=_as_text(options.get("database")),
            secure=options.get("secure") is True,
        )

    @classmethod
    def connection_url_with_password(cls, options: Mapping[str, Any]) -> str | None:
        host = options.get("host")
        if not isinstance(host, str) or host == "":
            return None
        password = options.get("password")
        return compose_url_with_password(
            host=host,
            port=_as_port(options.get("port")),
            user=_as_text(options.get("user")),
            database=_as_text(options.get("database")),
            secure=options.get("secure") is True,
            password=password if isinstance(password, str) else "",
        )

    def connection_string(self) -> str:
        return self._session.connection_string()

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

    def query_profile(self) -> QueryProfile:
        """What this source accepts as a complete statement (D62, D270)."""
        return self._query.profile()

    def prepare_query(self, text: str) -> PreparedScript:
        return self._query.prepare(text)

    def open_query(self, request: QueryRequest) -> ClickhouseExecution:
        return self._query.open(request)

    async def explain_query(self, request: ExplainRequest) -> ExplainResult:
        return await self._explain.explain(request)

    async def query_metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        return await self._metadata.metadata(request)

    def format_query(self, text: str) -> str:
        return format_text(text)

    async def generate_query(self, request: GenerateQueryRequest) -> GeneratedQuery:
        return await self._generation.generate(request)


@register(
    name="clickhouse",
    title=N_("ClickHouse"),
    category="sql",
    description=N_(
        "A ClickHouse server, over its HTTP interface. Browse databases, tables "
        "and views, read rows a page at a time with sorting and filtering "
        "done by the server, and run SQL."
    ),
    options_schema=ClickhouseOptions,
    adapter_class=ClickhouseAdapter,
)
def _build(options: ClickhouseOptions, context: AdapterContext) -> ClickhouseAdapter:
    return ClickhouseAdapter(options, context.pooling)
