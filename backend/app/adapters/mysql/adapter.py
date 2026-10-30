from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any

from app.adapters.actions import Action, ActionType
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
from app.adapters.export import ExportBatch, ExportRequest
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexDropped,
)
from app.adapters.metrics import MetricPreset, MetricSample
from app.adapters.mysql import ids as database_ids
from app.adapters.mysql.actions import (
    MYSQL_ACTION_TYPES,
    DropRelation,
    MysqlActions,
    create_database,
)
from app.adapters.mysql.backup import MysqlBackup
from app.adapters.mysql.catalog import MysqlCatalog
from app.adapters.mysql.columns import MysqlColumns
from app.adapters.mysql.content import MysqlContent
from app.adapters.mysql.design import MysqlTableDesign
from app.adapters.mysql.explain import MysqlExplain
from app.adapters.mysql.export import MysqlExport
from app.adapters.mysql.features import MysqlFeatures
from app.adapters.mysql.fetch import MysqlFetch
from app.adapters.mysql.keys import MysqlKeys
from app.adapters.mysql.metadata import MysqlGeneration, MysqlMetadata
from app.adapters.mysql.metrics import PRESETS as METRIC_PRESETS
from app.adapters.mysql.metrics import MysqlMetrics
from app.adapters.mysql.options import MysqlOptions
from app.adapters.mysql.query import MysqlExecution, MysqlQuery, MysqlTransaction
from app.adapters.mysql.references import MysqlReferences
from app.adapters.mysql.relation import MysqlRelation
from app.adapters.mysql.relation_changes import MysqlRelationChanges
from app.adapters.mysql.row_commands import MysqlRowCommands
from app.adapters.mysql.samples import MysqlSamples
from app.adapters.mysql.search import MysqlSearch
from app.adapters.mysql.session import (
    MysqlSession,
    compose_url,
    compose_url_with_password,
    options_from_url,
)
from app.adapters.mysql.statements import format_text
from app.adapters.mysql.summary import MysqlSummaries
from app.adapters.mysql.table_copy import DIALECT, MysqlTableCopy
from app.adapters.mysql.update import MysqlUpdate
from app.adapters.protocol import (
    BackupAvailability,
    BackupProgram,
    ConnectionCheckResult,
)
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
from app.adapters.registry import AdapterContext, CatalogFace, register
from app.adapters.relation import RelationModel, RelationModelsRequest
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
)
from app.adapters.resources import Pooling
from app.adapters.row_commands import RowCommand, RowCommandResult
from app.adapters.search import (
    LastSearch,
    NameBatch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    SearchedField,
    SourceCost,
)
from app.adapters.summary import NodeSummary
from app.adapters.table_copy import (
    Arrived,
    CopiedTable,
    RowsOf,
    TableCopyPlan,
    TableCopyRequest,
    TableRows,
)
from app.adapters.table_design import TableDesignOptions, TablePlan, TablePlanRequest
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


class MysqlAdapter:
    """Facade over a session and the capabilities built on it (D2b).

    What a source of this type cannot do yet it does not claim: a capability
    arrives as a module composed here, and the registry reads it off the class.
    """

    def __init__(
        self,
        options: MysqlOptions,
        pooling: Pooling | None = None,
        tunnels: TunnelAccess | None = None,
    ) -> None:
        self._session = MysqlSession(options, pooling, tunnels)
        self._features = MysqlFeatures(self._session)
        self._catalog = MysqlCatalog(self._session)
        self._relation = MysqlRelation(self._session)
        self._fetch = MysqlFetch(self._session, self._relation)
        self._content = MysqlContent(self._session, self._relation)
        self._export = MysqlExport(self._session, self._fetch)
        self._row_commands = MysqlRowCommands(self._session)
        self._search = MysqlSearch(self._session)
        self._summaries = MysqlSummaries(self._session, self._relation)
        self._query = MysqlQuery(self._session)
        self._update = MysqlUpdate(self._session, self._relation)
        self._columns = MysqlColumns(self._session, self._relation)
        self._keys = MysqlKeys(self._session, self._relation)
        self._design = MysqlTableDesign(self._session, self._catalog, self._relation)
        self._relations = MysqlRelationChanges(self._session, self._catalog)
        self._table_copy = MysqlTableCopy(self._session, self._relations)
        self._backup = MysqlBackup(self._session, options)
        self._metrics = MysqlMetrics(self._session)
        self._samples = MysqlSamples(self._session)
        self._actions = MysqlActions(self._session, self._catalog)
        self._references = MysqlReferences(self._session, self._catalog, self._relation)
        self._explain = MysqlExplain(self._session)
        self._metadata = MysqlMetadata(self._session)
        self._generation = MysqlGeneration(self._session, self._metadata)

    table_copy_dialect = DIALECT

    @property
    def table_copy_database(self) -> str:
        return self._table_copy.table_copy_database

    async def describe_for_copy(self, node_ids: list[str]) -> list[CopiedTable]:
        return await self._table_copy.describe_for_copy(node_ids)

    async def free_table_names(self, place_node_id: str, wanted: list[str]) -> list[str]:
        return await self._table_copy.free_table_names(place_node_id, wanted)

    async def plan_table_copy(self, request: TableCopyRequest) -> TableCopyPlan:
        return await self._table_copy.plan_table_copy(request)

    def reading_tables(self) -> AbstractAsyncContextManager[TableRows]:
        return self._table_copy.reading_tables()

    async def carry_table_copy(
        self, request: TableCopyRequest, rows_of: RowsOf, arrived: Arrived
    ) -> None:
        """Tables made, rows in one transaction, then links; undone on failure (D239)."""
        await self._table_copy.carry_table_copy(request, rows_of, arrived)

    async def install_sample_data(self) -> str:
        """The lab, in a database of its own, for a server started here (D245)."""
        return await self._samples.install_sample_data()

    async def metric_samples(self) -> list[MetricSample]:
        """The server's counters and the database's size, per poll (D241)."""
        return await self._metrics.metric_samples()

    @classmethod
    def metric_presets(cls) -> tuple[MetricPreset, ...]:
        return METRIC_PRESETS

    async def backup_availability(self) -> BackupAvailability:
        return await self._backup.backup_availability()

    async def backup_program(self, *, into: str) -> BackupProgram:
        """A dump by the server's own family of program (D240)."""
        return await self._backup.backup_program(into=into)

    async def restore_program(self, *, from_file: str) -> BackupProgram:
        return await self._backup.restore_program(from_file=from_file)

    async def restore_inventory_program(self, *, from_file: str) -> BackupProgram:
        return await self._backup.restore_inventory_program(from_file=from_file)

    def validate_restore_inventory(self, lines: Sequence[str]) -> None:
        self._backup.validate_restore_inventory(lines)

    def restore_archive_reason(self, head: bytes) -> str | None:
        return self._backup.restore_archive_reason(head)

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

    def enumerate_names(self, limit: int, bounds: SearchBounds) -> AsyncIterator[NameBatch]:
        return self._search.enumerate_names(limit, bounds)

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        return await self._search.search_nodes(request, bounds)

    async def search_columns(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        return await self._search.search_columns(request, bounds)

    @classmethod
    def search_cost(cls, field: SearchedField, last: LastSearch | None) -> SourceCost:
        """Names are one query of the catalog; columns read every column (D200)."""
        return "cheap" if field == "names" else "costly"

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return await self._fetch.fetch(request)

    def row_commands(self, node_id: str) -> list[RowCommand]:
        return self._row_commands.for_node(node_id)

    async def run_row_command(
        self, node_id: str, name: str, keys: Sequence[str]
    ) -> RowCommandResult:
        return await self._row_commands.run(node_id, name, keys)

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        return self._export.export_rows(request)

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
        return await self._update.update_cell(request)

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        return await self._update.update_cells(request)

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        return await self._update.insert_row(request)

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        return await self._update.insert_rows(request)

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        return await self._update.delete_rows(request)

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return MYSQL_ACTION_TYPES

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return await self._actions.available(node_id)

    def action(self, name: str) -> Action[Any]:
        return self._actions.action(name)

    async def create_grouping(self, name: str) -> str:
        await create_database(self._session, name)
        return database_ids.database_id(name)

    async def drop_created(self, node_id: str) -> None:
        drop = self._actions.action(DropRelation.name)
        if not isinstance(drop, DropRelation):
            raise TypeError("drop_relation is not the drop this adapter registers")
        await drop.perform_on_set([node_id], {})

    async def all_actions(self) -> list[Action[Any]]:
        return await self._actions.all_actions()

    async def table_design_options(self, node_id: str) -> TableDesignOptions:
        """What a database will accept a designed table with (D117)."""
        return await self._design.table_design_options(node_id)

    async def plan_table(self, request: TablePlanRequest) -> TablePlan:
        return await self._design.plan_table(request)

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        return await self._relations.new_relation_options(parent_node_id)

    async def create_relation(self, request: CreateRelationRequest) -> CreateRelationResult:
        return await self._relations.create_relation(request)

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
    # Two products, one type (D228): a card each, so MariaDB is found as
    # itself, and each offers to start its own server (D244).
    faces=(
        CatalogFace(key="mysql", title=N_("MySQL"), templates=("mysql",)),
        CatalogFace(key="mariadb", title=N_("MariaDB"), templates=("mariadb",)),
    ),
)
def _build(options: MysqlOptions, context: AdapterContext) -> MysqlAdapter:
    return MysqlAdapter(options, context.pooling, context.tunnels)
