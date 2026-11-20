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
from app.adapters.duckdb.actions import DUCKDB_ACTION_TYPES, DuckdbActions
from app.adapters.duckdb.catalog import DuckdbCatalog
from app.adapters.duckdb.columns import DuckdbColumns
from app.adapters.duckdb.content import DuckdbContent
from app.adapters.duckdb.design import DuckdbTableDesign
from app.adapters.duckdb.explain import DuckdbExplain
from app.adapters.duckdb.features import DuckdbFeatures
from app.adapters.duckdb.fetch import DuckdbFetch
from app.adapters.duckdb.keys import DuckdbKeys
from app.adapters.duckdb.metadata import DuckdbGeneration, DuckdbMetadata
from app.adapters.duckdb.options import DuckdbOptions
from app.adapters.duckdb.query import DuckdbExecution, DuckdbQuery, DuckdbTransaction
from app.adapters.duckdb.references import DuckdbReferences
from app.adapters.duckdb.relation import DuckdbRelation
from app.adapters.duckdb.relation_changes import DuckdbRelationChanges
from app.adapters.duckdb.session import DuckdbSession
from app.adapters.duckdb.statements import format_text
from app.adapters.duckdb.summary import DuckdbSummaries
from app.adapters.duckdb.update import DuckdbUpdate
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexDropped,
)
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
from app.adapters.summary import NodeSummary
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


class DuckdbAdapter:
    """Facade over a session and the capabilities built on it (D2b).

    What a source of this type cannot do yet it does not claim: a capability
    arrives as a module composed here, and the registry reads it off the class.
    No read cache: the file is on this server's disk, and another program or
    an upload can change it without any connection hearing of it (D105).
    """

    def __init__(self, options: DuckdbOptions, home_dir: Path) -> None:
        self._session = DuckdbSession(options, home_dir)
        self._features = DuckdbFeatures()
        self._catalog = DuckdbCatalog(self._session)
        self._relation = DuckdbRelation(self._session)
        self._fetch = DuckdbFetch(self._session, self._relation)
        self._content = DuckdbContent(self._relation)
        self._summaries = DuckdbSummaries(self._relation)
        self._query = DuckdbQuery(self._session)
        self._explain = DuckdbExplain(self._session)
        self._metadata = DuckdbMetadata(self._session)
        self._generation = DuckdbGeneration(self._session)
        self._update = DuckdbUpdate(self._session, self._relation)
        self._references = DuckdbReferences(self._session, self._catalog, self._relation)
        self._columns = DuckdbColumns(self._session, self._relation)
        self._keys = DuckdbKeys(self._session, self._relation)
        self._design = DuckdbTableDesign(self._session, self._catalog, self._relation)
        self._relations = DuckdbRelationChanges(self._session, self._catalog)
        self._actions = DuckdbActions(self._session, self._catalog)

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return DUCKDB_ACTION_TYPES

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return await self._actions.available(node_id)

    def action(self, name: str) -> Action[Any]:
        return self._actions.action(name)

    async def all_actions(self) -> list[Action[Any]]:
        return await self._actions.all_actions()

    async def table_design_options(self, node_id: str) -> TableDesignOptions:
        """What a schema will accept a designed table with (D117, D397)."""
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
        """A unique key in place; DuckDB adds no other to an existing table (D396)."""
        return await self._keys.create_constraint(request)

    async def drop_constraint(self, request: DropConstraintRequest) -> ConstraintDropped:
        return await self._keys.drop_constraint(request)

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

    async def insert_rows_skipping(self, request: InsertRowsRequest) -> InsertRowsResult:
        return await self._update.insert_rows(request, skipping=True)

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        """Rows named by their primary key and checked against what was read (D395)."""
        return await self._update.delete_rows(request)

    async def follow_reference(self, request: FollowReferenceRequest) -> ReferenceTarget:
        return await self._references.follow_reference(request)

    async def arriving_references(self, node_id: str) -> list[ArrivingReference]:
        return await self._references.arriving_references(node_id)

    def query_profile(self) -> QueryProfile:
        """What this source accepts as a complete statement (D62, D392)."""
        return self._query.profile()

    def prepare_query(self, text: str) -> PreparedScript:
        return self._query.prepare(text)

    def open_query(self, request: QueryRequest) -> DuckdbExecution:
        return self._query.open(request)

    async def begin_transaction(self, context: TransactionContext) -> DuckdbTransaction:
        """Hold a transaction open between requests, and the file with it (D66, D393)."""
        return await self._query.begin(context)

    async def rehearse_query(self, request: QueryRequest) -> QueryRehearsal:
        """Carry the change out, describe it, and undo it (D66, D393)."""
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
    name="duckdb",
    title=N_("DuckDB"),
    category="sql",
    description=N_(
        "A DuckDB database file in your personal storage. Browse its schemas, "
        "tables and views, read and edit rows a page at a time with sorting and filtering, and run SQL "
        "over the file and the other files of your storage."
    ),
    options_schema=DuckdbOptions,
    adapter_class=DuckdbAdapter,
)
def _build(options: DuckdbOptions, context: AdapterContext) -> DuckdbAdapter:
    return DuckdbAdapter(options, context.home_dir)
