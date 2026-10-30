from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any

from app.adapters.actions import Action, ActionType
from app.adapters.cache import CacheArea
from app.adapters.catalog import CatalogNode
from app.adapters.clickhouse.actions import (
    CLICKHOUSE_ACTION_TYPES,
    ClickhouseActions,
    DropRelation,
    create_database,
)
from app.adapters.clickhouse.backup import ClickhouseBackup
from app.adapters.clickhouse.catalog import ClickhouseCatalog
from app.adapters.clickhouse.columns import ClickhouseColumns
from app.adapters.clickhouse.content import ClickhouseContent
from app.adapters.clickhouse.design import ClickhouseTableDesign
from app.adapters.clickhouse.explain import ClickhouseExplain
from app.adapters.clickhouse.export import ClickhouseExport
from app.adapters.clickhouse.features import ClickhouseFeatures
from app.adapters.clickhouse.fetch import ClickhouseFetch
from app.adapters.clickhouse.indexes import ClickhouseIndexes
from app.adapters.clickhouse.metadata import ClickhouseGeneration, ClickhouseMetadata
from app.adapters.clickhouse.metrics import PRESETS as METRIC_PRESETS
from app.adapters.clickhouse.metrics import ClickhouseMetrics
from app.adapters.clickhouse.options import ClickhouseOptions
from app.adapters.clickhouse.query import ClickhouseExecution, ClickhouseQuery
from app.adapters.clickhouse.relation import ClickhouseRelation
from app.adapters.clickhouse.relation_changes import ClickhouseRelationChanges
from app.adapters.clickhouse.row_commands import ClickhouseRowCommands
from app.adapters.clickhouse.samples import ClickhouseSamples
from app.adapters.clickhouse.search import ClickhouseSearch
from app.adapters.clickhouse.session import (
    ClickhouseSession,
    compose_url,
    compose_url_with_password,
    options_from_url,
)
from app.adapters.clickhouse.statements import format_text
from app.adapters.clickhouse.summary import ClickhouseSummaries
from app.adapters.clickhouse.table_copy import DIALECT, ClickhouseTableCopy
from app.adapters.clickhouse.update import ClickhouseUpdate
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
from app.adapters.content import ContentRequest, ContentResult
from app.adapters.database_ids import database_id
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
)
from app.adapters.registry import AdapterContext, register
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
        self._update = ClickhouseUpdate(self._session, self._relation)
        self._columns = ClickhouseColumns(self._session, self._relation)
        self._indexes = ClickhouseIndexes(self._session, self._relation)
        self._design = ClickhouseTableDesign(self._session, self._catalog)
        self._relations = ClickhouseRelationChanges(self._session, self._catalog, self._update)
        self._table_copy = ClickhouseTableCopy(self._session, self._relations)
        self._actions = ClickhouseActions(self._session, self._catalog)
        self._export = ClickhouseExport(self._session, self._fetch)
        self._row_commands = ClickhouseRowCommands(self._session)
        self._search = ClickhouseSearch(self._session)
        self._explain = ClickhouseExplain(self._session)
        self._metadata = ClickhouseMetadata(self._session)
        self._generation = ClickhouseGeneration(self._session)
        self._backup = ClickhouseBackup(self._session, options)
        self._metrics = ClickhouseMetrics(self._session)
        self._samples = ClickhouseSamples(self._session)

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
        """Tables made, rows streamed in, everything made dropped on failure (D277)."""
        await self._table_copy.carry_table_copy(request, rows_of, arrived)

    async def install_sample_data(self) -> str:
        """The lab, in a database of its own, for a server started here (D280)."""
        return await self._samples.install_sample_data()

    async def metric_samples(self) -> list[MetricSample]:
        """The server's counters, and the database's size and parts, per poll (D279)."""
        return await self._metrics.metric_samples()

    @classmethod
    def metric_presets(cls) -> tuple[MetricPreset, ...]:
        return METRIC_PRESETS

    async def backup_availability(self) -> BackupAvailability:
        return await self._backup.backup_availability()

    async def backup_program(self, *, into: str) -> BackupProgram:
        """A script over the HTTP interface, writing one text file (D278)."""
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

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        return self._export.export_rows(request)

    def row_commands(self, node_id: str) -> list[RowCommand]:
        return self._row_commands.for_node(node_id)

    async def run_row_command(
        self, node_id: str, name: str, keys: Sequence[str]
    ) -> RowCommandResult:
        """Stop a query or a mutation from its report (D275)."""
        return await self._row_commands.run(node_id, name, keys)

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
        """Every row alike to the ones picked, identical rows together (D272)."""
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
        """Counted first and put back on failure: a failed mutation breaks a table (D273)."""
        return await self._columns.change_column_type(request)

    async def create_index(self, request: CreateIndexRequest) -> CreateIndexResult:
        return await self._indexes.create_index(request)

    async def drop_index(self, request: DropIndexRequest) -> IndexDropped:
        return await self._indexes.drop_index(request)

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return CLICKHOUSE_ACTION_TYPES

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return await self._actions.available(node_id)

    def action(self, name: str) -> Action[Any]:
        return self._actions.action(name)

    async def create_grouping(self, name: str) -> str:
        await create_database(self._session, name)
        return database_id(name)

    async def drop_created(self, node_id: str) -> None:
        drop = self._actions.action(DropRelation.name)
        if not isinstance(drop, DropRelation):
            raise TypeError("drop_relation is not the drop this adapter registers")
        await drop.perform_on_set([node_id], {})

    async def all_actions(self) -> list[Action[Any]]:
        return await self._actions.all_actions()

    async def table_design_options(self, node_id: str) -> TableDesignOptions:
        """What a database will accept a designed table with (D117, D274)."""
        return await self._design.table_design_options(node_id)

    async def plan_table(self, request: TablePlanRequest) -> TablePlan:
        return await self._design.plan_table(request)

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        return await self._relations.new_relation_options(parent_node_id)

    async def create_relation(self, request: CreateRelationRequest) -> CreateRelationResult:
        return await self._relations.create_relation(request)

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
        "and views, read and edit rows a page at a time with sorting and "
        "filtering done by the server, and run SQL."
    ),
    options_schema=ClickhouseOptions,
    adapter_class=ClickhouseAdapter,
)
def _build(options: ClickhouseOptions, context: AdapterContext) -> ClickhouseAdapter:
    return ClickhouseAdapter(options, context.pooling)
