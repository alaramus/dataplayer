from collections.abc import Mapping
from typing import Any

from app.adapters.cache import CacheArea
from app.adapters.cassandra.catalog import CassandraCatalog
from app.adapters.cassandra.console import console_program
from app.adapters.cassandra.content import CassandraContent
from app.adapters.cassandra.features import CassandraFeatures
from app.adapters.cassandra.fetch import CassandraFetch
from app.adapters.cassandra.inspection import Inspector
from app.adapters.cassandra.metadata import CassandraGeneration, CassandraMetadata
from app.adapters.cassandra.options import CassandraOptions
from app.adapters.cassandra.query import CassandraExecution, CassandraQuery
from app.adapters.cassandra.relation import CassandraRelation
from app.adapters.cassandra.session import (
    CassandraSession,
    compose_url,
    compose_url_with_password,
    options_from_url,
)
from app.adapters.cassandra.summary import CassandraSummaries
from app.adapters.cassandra.update import CassandraUpdate
from app.adapters.catalog import CatalogNode
from app.adapters.content import ContentRequest, ContentResult
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.query import (
    GeneratedQuery,
    GenerateQueryRequest,
    PreparedScript,
    QueryMetadata,
    QueryMetadataRequest,
    QueryProfile,
    QueryRequest,
)
from app.adapters.registry import AdapterContext, CatalogFace, register
from app.adapters.relation import RelationModel, RelationModelsRequest
from app.adapters.resources import Pooling
from app.adapters.summary import NodeSummary
from app.adapters.terminal import ConsoleProgram
from app.adapters.tunnels import TunnelAccess
from app.adapters.update import (
    DeleteRowsRequest,
    DeleteRowsResult,
    InsertRowRequest,
    InsertRowResult,
    InsertRowsRequest,
    InsertRowsResult,
    UpdateCellRequest,
    UpdateCellResult,
    UpdateCellsRequest,
    UpdateCellsResult,
)
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


def _user_of(options: Mapping[str, Any]) -> str:
    return (
        _as_text(options.get("user"))
        if options.get("auth_method") != "no_password"
        else ""
    )


class CassandraAdapter:
    """Facade over a session and the capabilities built on it (D2b).

    What a source of this type cannot do yet it does not claim: a capability
    arrives as a module composed here, and the registry reads it off the class.
    """

    def __init__(
        self,
        options: CassandraOptions,
        pooling: Pooling | None = None,
        tunnels: TunnelAccess | None = None,
    ) -> None:
        self._session = CassandraSession(options, pooling, tunnels)
        self._inspector = Inspector(self._session)
        self._features = CassandraFeatures(self._session)
        self._catalog = CassandraCatalog(self._session, self._inspector)
        self._relation = CassandraRelation(self._inspector)
        self._fetch = CassandraFetch(self._session, self._relation)
        self._content = CassandraContent(self._session, self._relation)
        self._summaries = CassandraSummaries(self._relation)
        self._query = CassandraQuery(self._session, self._inspector)
        self._update = CassandraUpdate(self._session, self._relation)
        self._metadata = CassandraMetadata(self._session, self._inspector)
        self._generation = CassandraGeneration(self._inspector)

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
            user=_user_of(options),
            keyspace=_as_text(options.get("keyspace")),
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
            user=_user_of(options),
            keyspace=_as_text(options.get("keyspace")),
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
        """A page by offset, served from the paging state before it (D342)."""
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

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        """A row found by its key, changed only when it reads as it did (D345)."""
        return await self._update.update_cell(request)

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        return await self._update.update_cells(request)

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        return await self._update.insert_row(request)

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        return await self._update.insert_rows(request)

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        return await self._update.delete_rows(request)

    def query_profile(self) -> QueryProfile:
        """What this source accepts as a complete statement (D62, D343)."""
        return self._query.profile()

    def prepare_query(self, text: str) -> PreparedScript:
        return self._query.prepare(text)

    def open_query(self, request: QueryRequest) -> CassandraExecution:
        return self._query.open(request)

    async def query_metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        return await self._metadata.metadata(request)

    async def generate_query(self, request: GenerateQueryRequest) -> GeneratedQuery:
        return await self._generation.generate(request)

    async def console_program(self) -> ConsoleProgram:
        """cqlsh in Cassandra's image, signed in from a file it writes (D344)."""
        return console_program(self._session.options)


@register(
    name="cassandra",
    title=N_("Cassandra"),
    category="sql",
    description=N_(
        "Apache Cassandra or ScyllaDB, over CQL. Browse keyspaces, tables and "
        "materialized views, and read rows a page at a time with filtering done "
        "by the server."
    ),
    options_schema=CassandraOptions,
    adapter_class=CassandraAdapter,
    # Two products, one type (D340): a card each, so ScyllaDB is found as
    # itself.
    faces=(
        CatalogFace(key="cassandra", title=N_("Apache Cassandra")),
        CatalogFace(key="scylladb", title=N_("ScyllaDB")),
    ),
)
def _build(options: CassandraOptions, context: AdapterContext) -> CassandraAdapter:
    return CassandraAdapter(options, context.pooling, context.tunnels)
