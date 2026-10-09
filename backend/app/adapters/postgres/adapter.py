from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any

from app.adapters.actions import Action, ActionOffers, ActionType
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
from app.adapters.hypertable_design import HypertableDesignState
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexDropped,
)
from app.adapters.metrics import MetricPreset, MetricSample
from app.adapters.postgres.actions import POSTGRES_ACTION_TYPES, PostgresActions
from app.adapters.postgres.backup import PostgresBackup
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.columns import PostgresColumns
from app.adapters.postgres.constraints import PostgresConstraints
from app.adapters.postgres.content import PostgresContent
from app.adapters.postgres.explain import PostgresExplain
from app.adapters.postgres.export import PostgresExport
from app.adapters.postgres.features import PostgresFeatures
from app.adapters.postgres.fetch import PostgresFetch
from app.adapters.postgres.indexes import PostgresIndexes
from app.adapters.postgres.metadata import PostgresGeneration, PostgresMetadata
from app.adapters.postgres.metrics import PRESETS as METRIC_PRESETS
from app.adapters.postgres.metrics import PostgresMetrics
from app.adapters.postgres.options import PostgresOptions
from app.adapters.postgres.query import (
    PostgresExecution,
    PostgresQuery,
    PostgresTransaction,
)
from app.adapters.postgres.references import PostgresReferences
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.postgres.relation_changes import PostgresRelationChanges
from app.adapters.postgres.relation_context import PostgresRelationContext
from app.adapters.postgres.row_commands import PostgresRowCommands
from app.adapters.postgres.samples import PostgresSamples
from app.adapters.postgres.search import PostgresSearch
from app.adapters.postgres.session import (
    PostgresSession,
    compose_url,
    compose_url_with_password,
    options_from_url,
)
from app.adapters.postgres.statements import format_text
from app.adapters.postgres.summary import PostgresSummaries
from app.adapters.postgres.table_copy import DIALECT, PostgresTableCopy
from app.adapters.postgres.table_design import PostgresTableDesign
from app.adapters.postgres.timescale.actions import TIMESCALE_ACTION_TYPES
from app.adapters.postgres.update import PostgresUpdate
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
    QueryRehearsal,
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
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
)
from app.adapters.resources import Pooling
from app.adapters.row_commands import RowCommand, RowCommandResult
from app.adapters.search import (
    LastSearch,
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
from app.adapters.table_design import (
    TableDesignOptions,
    TablePlan,
    TablePlanRequest,
)
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
        self._features = PostgresFeatures(self._session)
        self._metrics = PostgresMetrics(self._session)
        self._relation_context = PostgresRelationContext(
            self._session, self._features
        )
        self._catalog = PostgresCatalog(self._session, self._relation_context)
        self._search = PostgresSearch(self._session, self._relation_context)
        self._actions = PostgresActions(self._session, self._catalog)
        self._fetch = PostgresFetch(self._session, self._relation_context)
        self._export = PostgresExport(self._session, self._fetch)
        self._update = PostgresUpdate(self._session, self._fetch)
        self._references = PostgresReferences(self._catalog, self._fetch)
        self._relation = PostgresRelation(self._session, self._relation_context)
        self._columns = PostgresColumns(self._session, self._relation)
        self._indexes = PostgresIndexes(self._session, self._relation)
        self._constraints = PostgresConstraints(self._session, self._relation)
        self._relations = PostgresRelationChanges(self._session, self._catalog)
        self._content = PostgresContent(self._session, self._relation_context)
        self._query = PostgresQuery(self._session)
        self._metadata = PostgresMetadata(self._session)
        self._explain = PostgresExplain(self._session)
        self._generation = PostgresGeneration(self._session, self._metadata)
        self._row_commands = PostgresRowCommands(self._session)
        self._summaries = PostgresSummaries(self._session, self._relation)
        self._design = PostgresTableDesign(
            self._session, self._catalog, self._relation
        )
        self._backup = PostgresBackup(self._session, options)
        self._samples = PostgresSamples(self._session)
        self._table_copy = PostgresTableCopy(self._session, self._relations)

    table_copy_dialect = DIALECT

    @property
    def table_copy_database(self) -> str:
        return self._table_copy.table_copy_database

    async def describe_for_copy(self, node_ids: list[str]) -> list[CopiedTable]:
        """Each table as a copy of it is made (D182)."""
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
        await self._table_copy.carry_table_copy(request, rows_of, arrived)

    async def backup_availability(self) -> BackupAvailability:
        return await self._backup.backup_availability()

    async def backup_program(self, *, into: str) -> BackupProgram:
        """What copies this server out, in the version that can (D87)."""
        return await self._backup.backup_program(into=into)

    async def restore_program(self, *, from_file: str) -> BackupProgram:
        return await self._backup.restore_program(from_file=from_file)

    async def restore_inventory_program(self, *, from_file: str) -> BackupProgram:
        return await self._backup.restore_inventory_program(from_file=from_file)

    def validate_restore_inventory(self, lines: Sequence[str]) -> None:
        self._backup.validate_restore_inventory(lines)

    async def install_sample_data(self) -> str:
        """Put this project's own demonstration schema into an empty server."""
        return await self._samples.install_sample_data()

    def query_profile(self) -> QueryProfile:
        """What this source accepts as a complete statement (D62)."""
        return self._query.profile()

    def prepare_query(self, text: str) -> PreparedScript:
        return self._query.prepare(text)

    def open_query(self, request: QueryRequest) -> PostgresExecution:
        return self._query.open(request)

    async def begin_transaction(self, context: TransactionContext) -> PostgresTransaction:
        """Hold a transaction open between requests (D66)."""
        return await self._query.begin(context)

    async def rehearse_query(self, request: QueryRequest) -> QueryRehearsal:
        """Carry the change out, describe it, and undo it (D66)."""
        return await self._query.rehearse(request)

    async def explain_query(self, request: ExplainRequest) -> ExplainResult:
        """Plan the statement, without running it (D65)."""
        return await self._explain.explain(request)

    async def query_metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        """What an editor may complete to, progressively (D65)."""
        return await self._metadata.metadata(request)

    def format_query(self, text: str) -> str:
        return format_text(text)

    async def generate_query(self, request: GenerateQueryRequest) -> GeneratedQuery:
        return await self._generation.generate(request)

    @classmethod
    def cache_ttl(cls, area: CacheArea) -> float:
        """A short stale window for reads whose source is under our control.

        What an editor completes against is worth keeping far longer than a
        page of rows: five minutes, thrown away early by anything that changes
        this connection (D65).
        """
        if area == "metadata":
            return 300.0
        return 30.0 if area == "catalog" else 10.0

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        """The same declarations used to build the callable action set."""
        return (*POSTGRES_ACTION_TYPES, *TIMESCALE_ACTION_TYPES)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return await self._actions.available(node_id)

    async def action_offers(self, node_id: str | None) -> ActionOffers:
        return await self._actions.action_offers(node_id)

    def action(self, name: str) -> Action[Any]:
        return self._actions.action(name)

    async def hypertable_design_state(self, node_id: str) -> HypertableDesignState:
        return await self._actions.hypertable_design_state(node_id)

    async def all_actions(self) -> list[Action[Any]]:
        return await self._actions.all_actions()

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

    @classmethod
    def connection_url_with_password(cls, options: Mapping[str, Any]) -> str | None:
        """The address a person pastes into psql, password included (D89).

        Written here rather than by whoever shows it, for the reason every
        other spelling of an address is written here: the grammar has one
        home.
        """
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

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def metric_samples(self) -> list[MetricSample]:
        return await self._metrics.metric_samples()

    @classmethod
    def metric_presets(cls) -> tuple[MetricPreset, ...]:
        return METRIC_PRESETS

    async def source_features(self) -> SourceFeatures:
        return await self._features.source_features()

    def connection_string(self) -> str:
        return self._session.connection_string()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return await self._catalog.path_to(node_id)

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

    async def read_content(self, request: ContentRequest) -> ContentResult:
        return await self._content.read_content(request)

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        return self._export.export_rows(request)

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

    async def follow_reference(
        self, request: FollowReferenceRequest
    ) -> ReferenceTarget:
        return await self._references.follow_reference(request)

    async def arriving_references(self, node_id: str) -> list[ArrivingReference]:
        return await self._references.arriving_references(node_id)

    async def relation_model(self, node_id: str) -> RelationModel:
        return await self._relation.relation_model(node_id)

    async def node_summary(self, node_id: str) -> NodeSummary:
        """What one relation is, apart from the shape of its rows (D75)."""
        return await self._summaries.node_summary(node_id)

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        return await self._relations.new_relation_options(parent_node_id)

    async def create_relation(
        self, request: CreateRelationRequest
    ) -> CreateRelationResult:
        return await self._relations.create_relation(request)

    async def table_design_options(self, node_id: str) -> TableDesignOptions:
        """What a schema will accept a designed table with (D117)."""
        return await self._design.table_design_options(node_id)

    async def plan_table(self, request: TablePlanRequest) -> TablePlan:
        return await self._design.plan_table(request)

    async def add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        return await self._columns.add_column(request)

    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        return await self._columns.drop_column(request)

    async def rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        return await self._columns.rename_column(request)

    async def change_column_default(
        self, request: ColumnDefaultRequest
    ) -> ColumnChangeResult:
        return await self._columns.change_column_default(request)

    async def change_column_nullability(
        self, request: ColumnNullabilityRequest
    ) -> ColumnNullabilityResult:
        return await self._columns.change_column_nullability(request)

    async def change_column_type(
        self, request: ColumnTypeRequest
    ) -> ColumnTypeChangeResult:
        return await self._columns.change_column_type(request)

    async def create_index(self, request: CreateIndexRequest) -> CreateIndexResult:
        return await self._indexes.create_index(request)

    async def drop_index(self, request: DropIndexRequest) -> IndexDropped:
        return await self._indexes.drop_index(request)

    async def create_constraint(
        self, request: CreateConstraintRequest
    ) -> CreateConstraintResult:
        return await self._constraints.create_constraint(request)

    async def drop_constraint(
        self, request: DropConstraintRequest
    ) -> ConstraintDropped:
        return await self._constraints.drop_constraint(request)


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
