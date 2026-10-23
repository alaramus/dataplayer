from collections.abc import Mapping
from typing import Any

from app.adapters.cache import CacheArea
from app.adapters.catalog import CatalogNode
from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    ColumnDefaultRequest,
    ColumnNullabilityRequest,
    ColumnNullabilityResult,
    ColumnTypeChangeResult,
    ColumnTypeRequest,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.constraints import (
    ConstraintDropped,
    CreateConstraintRequest,
    CreateConstraintResult,
    DropConstraintRequest,
)
from app.adapters.content import ContentRequest, ContentResult
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexDropped,
)
from app.adapters.mysql.catalog import MysqlCatalog
from app.adapters.mysql.columns import MysqlColumns
from app.adapters.mysql.content import MysqlContent
from app.adapters.mysql.explain import MysqlExplain
from app.adapters.mysql.features import MysqlFeatures
from app.adapters.mysql.fetch import MysqlFetch
from app.adapters.mysql.keys import MysqlKeys
from app.adapters.mysql.metadata import MysqlGeneration, MysqlMetadata
from app.adapters.mysql.options import MysqlOptions
from app.adapters.mysql.query import MysqlExecution, MysqlQuery, MysqlTransaction
from app.adapters.mysql.references import MysqlReferences
from app.adapters.mysql.relation import MysqlRelation
from app.adapters.mysql.session import (
    MysqlSession,
    compose_url,
    compose_url_with_password,
    options_from_url,
)
from app.adapters.mysql.statements import format_text
from app.adapters.mysql.summary import MysqlSummaries
from app.adapters.mysql.update import MysqlUpdate
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
    TransactionContext,
)
from app.adapters.references import (
    ArrivingReference,
    FollowReferenceRequest,
    ReferenceTarget,
)
from app.adapters.registry import AdapterContext, register
from app.adapters.relation import RelationModel
from app.adapters.resources import Pooling
from app.adapters.summary import NodeSummary
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


class MysqlAdapter:
    """Facade over a session and the capabilities built on it (D2b).

    What a source of this type cannot do yet it does not claim: a capability
    arrives as a module composed here, and the registry reads it off the class.
    """

    def __init__(self, options: MysqlOptions, pooling: Pooling | None = None) -> None:
        self._session = MysqlSession(options, pooling)
        self._features = MysqlFeatures(self._session)
        self._catalog = MysqlCatalog(self._session)
        self._relation = MysqlRelation(self._session)
        self._fetch = MysqlFetch(self._session, self._relation)
        self._content = MysqlContent(self._session, self._relation)
        self._summaries = MysqlSummaries(self._session, self._relation)
        self._query = MysqlQuery(self._session)
        self._update = MysqlUpdate(self._session, self._relation)
        self._columns = MysqlColumns(self._session, self._relation)
        self._keys = MysqlKeys(self._session, self._relation)
        self._references = MysqlReferences(self._session, self._catalog, self._relation)
        self._explain = MysqlExplain(self._session)
        self._metadata = MysqlMetadata(self._session)
        self._generation = MysqlGeneration(self._session, self._metadata)

    @classmethod
    def cache_ttl(cls, area: CacheArea) -> float:
        """The windows PostgreSQL keeps, for the same kinds of answer."""
        if area == "metadata":
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

    async def node_summary(self, node_id: str) -> NodeSummary:
        return await self._summaries.node_summary(node_id)

    async def read_content(self, request: ContentRequest) -> ContentResult:
        return await self._content.read_content(request)

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        return await self._update.update_cell(request)

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        return await self._update.update_cells(request)

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        return await self._update.insert_row(request)

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        return await self._update.insert_rows(request)

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        return await self._update.delete_rows(request)

    async def add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        return await self._columns.add_column(request)

    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        return await self._columns.drop_column(request)

    async def rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        return await self._columns.rename_column(request)

    async def change_column_default(self, request: ColumnDefaultRequest) -> ColumnChangeResult:
        return await self._columns.change_column_default(request)

    async def change_column_nullability(
        self, request: ColumnNullabilityRequest
    ) -> ColumnNullabilityResult:
        return await self._columns.change_column_nullability(request)

    async def change_column_type(self, request: ColumnTypeRequest) -> ColumnTypeChangeResult:
        return await self._columns.change_column_type(request)

    async def create_index(self, request: CreateIndexRequest) -> CreateIndexResult:
        return await self._keys.create_index(request)

    async def drop_index(self, request: DropIndexRequest) -> IndexDropped:
        return await self._keys.drop_index(request)

    async def create_constraint(self, request: CreateConstraintRequest) -> CreateConstraintResult:
        return await self._keys.create_constraint(request)

    async def drop_constraint(self, request: DropConstraintRequest) -> ConstraintDropped:
        return await self._keys.drop_constraint(request)

    async def follow_reference(self, request: FollowReferenceRequest) -> ReferenceTarget:
        return await self._references.follow_reference(request)

    async def arriving_references(self, node_id: str) -> list[ArrivingReference]:
        return await self._references.arriving_references(node_id)

    def query_profile(self) -> QueryProfile:
        """What this source accepts as a complete statement (D62)."""
        return self._query.profile()

    def prepare_query(self, text: str) -> PreparedScript:
        return self._query.prepare(text)

    def open_query(self, request: QueryRequest) -> MysqlExecution:
        return self._query.open(request)

    async def begin_transaction(self, context: TransactionContext) -> MysqlTransaction:
        """Hold a transaction open between requests (D66, D233)."""
        return await self._query.begin(context)

    async def explain_query(self, request: ExplainRequest) -> ExplainResult:
        return await self._explain.explain(request)

    async def query_metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        return await self._metadata.metadata(request)

    def format_query(self, text: str) -> str:
        return format_text(text)

    async def generate_query(self, request: GenerateQueryRequest) -> GeneratedQuery:
        return await self._generation.generate(request)


@register(
    name="mysql",
    title=N_("MySQL"),
    category="sql",
    description=N_(
        "MySQL or MariaDB. Browse databases, tables and views, and read rows a "
        "page at a time with sorting and filtering done by the server."
    ),
    options_schema=MysqlOptions,
    adapter_class=MysqlAdapter,
)
def _build(options: MysqlOptions, context: AdapterContext) -> MysqlAdapter:
    return MysqlAdapter(options, context.pooling)
