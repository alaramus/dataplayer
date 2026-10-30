from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

from app.adapters.actions import Action, ActionType
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
from app.adapters.protocol import (
    BackupAvailability,
    BackupProgram,
    ConnectionCheckResult,
    MadeSource,
    MakeChoice,
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
from app.adapters.relation import RelationModel, RelationModelsRequest
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
)
from app.adapters.search import (
    LastSearch,
    NameBatch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    SearchedField,
    SourceCost,
)
from app.adapters.sqlite import made_here
from app.adapters.sqlite.actions import SQLITE_ACTION_TYPES, DropRelation, SqliteActions
from app.adapters.sqlite.backup import SqliteBackup
from app.adapters.sqlite.catalog import SqliteCatalog
from app.adapters.sqlite.columns import SqliteColumns
from app.adapters.sqlite.content import SqliteContent
from app.adapters.sqlite.design import SqliteTableDesign
from app.adapters.sqlite.explain import SqliteExplain
from app.adapters.sqlite.export import SqliteExport
from app.adapters.sqlite.features import SqliteFeatures
from app.adapters.sqlite.fetch import SqliteFetch
from app.adapters.sqlite.keys import SqliteKeys
from app.adapters.sqlite.metadata import SqliteGeneration, SqliteMetadata
from app.adapters.sqlite.options import SqliteOptions
from app.adapters.sqlite.query import SqliteExecution, SqliteQuery, SqliteTransaction
from app.adapters.sqlite.references import SqliteReferences
from app.adapters.sqlite.relation import SqliteRelation
from app.adapters.sqlite.relation_changes import SqliteRelationChanges
from app.adapters.sqlite.search import SqliteSearch
from app.adapters.sqlite.session import SqliteSession
from app.adapters.sqlite.statements import format_text
from app.adapters.sqlite.summary import SqliteSummaries
from app.adapters.sqlite.table_copy import DIALECT, SqliteTableCopy
from app.adapters.sqlite.update import SqliteUpdate
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
        self._query = SqliteQuery(self._session)
        self._explain = SqliteExplain(self._session)
        self._metadata = SqliteMetadata(self._session)
        self._generation = SqliteGeneration(self._session)
        self._update = SqliteUpdate(self._session, self._relation)
        self._columns = SqliteColumns(self._session, self._relation)
        self._keys = SqliteKeys(self._session, self._relation)
        self._design = SqliteTableDesign(self._session, self._catalog, self._relation)
        self._relations = SqliteRelationChanges(self._session, self._catalog)
        self._actions = SqliteActions(self._session, self._catalog)
        self._search = SqliteSearch(self._session)
        self._export = SqliteExport(self._session, self._fetch)
        self._references = SqliteReferences(self._session, self._catalog, self._relation)
        self._table_copy = SqliteTableCopy(self._session, self._relations)
        self._backup = SqliteBackup(self._session)

    @classmethod
    def make_source_here(cls, home_dir: Path, choice: MakeChoice) -> MadeSource:
        """A new file, `databases/dataplayer.db` with the lab unless chosen (D263)."""
        return made_here.make(home_dir, choice)

    @classmethod
    def unmake_source_here(cls, home_dir: Path, made: MadeSource) -> None:
        made_here.unmake(home_dir, made)

    async def backup_availability(self) -> BackupAvailability:
        return await self._backup.backup_availability()

    async def backup_program(self, *, into: str) -> BackupProgram:
        """The file, by SQLite's online backup (D260)."""
        return await self._backup.backup_program(into=into)

    async def restore_program(self, *, from_file: str) -> BackupProgram:
        return await self._backup.restore_program(from_file=from_file)

    async def restore_inventory_program(self, *, from_file: str) -> BackupProgram:
        return await self._backup.restore_inventory_program(from_file=from_file)

    def validate_restore_inventory(self, lines: Sequence[str]) -> None:
        self._backup.validate_restore_inventory(lines)

    def restore_archive_reason(self, head: bytes) -> str | None:
        return self._backup.restore_archive_reason(head)

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
        """Tables, rows and indexes in one transaction (D259)."""
        await self._table_copy.carry_table_copy(request, rows_of, arrived)

    @classmethod
    def search_cost(cls, field: SearchedField, last: LastSearch | None) -> SourceCost:
        """The file is on this server's disk, and its catalog is read whole (D257)."""
        return "cheap"

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

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        return self._export.export_rows(request)

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return SQLITE_ACTION_TYPES

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return await self._actions.available(node_id)

    def action(self, name: str) -> Action[Any]:
        return self._actions.action(name)

    async def drop_created(self, node_id: str) -> None:
        drop = self._actions.action(DropRelation.name)
        if not isinstance(drop, DropRelation):
            raise TypeError("drop_relation is not the drop this adapter registers")
        await drop.perform_on_set([node_id], {})

    async def all_actions(self) -> list[Action[Any]]:
        return await self._actions.all_actions()

    async def table_design_options(self, node_id: str) -> TableDesignOptions:
        """What `main` will accept a designed table with (D117)."""
        return await self._design.table_design_options(node_id)

    async def plan_table(self, request: TablePlanRequest) -> TablePlan:
        return await self._design.plan_table(request)

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        return await self._relations.new_relation_options(parent_node_id)

    async def create_relation(self, request: CreateRelationRequest) -> CreateRelationResult:
        return await self._relations.create_relation(request)

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

    def open_query(self, request: QueryRequest) -> SqliteExecution:
        return self._query.open(request)

    async def begin_transaction(self, context: TransactionContext) -> SqliteTransaction:
        """Hold a transaction open between requests (D66)."""
        return await self._query.begin(context)

    async def rehearse_query(self, request: QueryRequest) -> QueryRehearsal:
        """Carry the change out, describe it, and undo it (D66, D253)."""
        return await self._query.rehearse(request)

    async def explain_query(self, request: ExplainRequest) -> ExplainResult:
        return await self._explain.explain(request)

    async def query_metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        return await self._metadata.metadata(request)

    def format_query(self, text: str) -> str:
        return format_text(text)

    async def generate_query(self, request: GenerateQueryRequest) -> GeneratedQuery:
        return await self._generation.generate(request)


@register(
    name="sqlite",
    title=N_("SQLite"),
    category="sql",
    description=N_(
        "A SQLite database file in your personal storage. Browse its tables and "
        "views, read and edit rows a page at a time with sorting and filtering, and run SQL."
    ),
    options_schema=SqliteOptions,
    adapter_class=SqliteAdapter,
)
def _build(options: SqliteOptions, context: AdapterContext) -> SqliteAdapter:
    return SqliteAdapter(options, context.home_dir)
