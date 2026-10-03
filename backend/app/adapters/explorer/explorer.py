"""Everything a tree of files can do, over one storage (D150).

A source that is a tree of files is this plus a storage: `file` gives it the
server's own disk, and a remote source gives it the server it reaches. What
differs between them — the options, how the storage is built, a terminal —
stays with the source; nothing here knows which storage it has.
"""

from typing import Any, ClassVar

from anyio import to_thread

from app.adapters.actions import Action, ActionType
from app.adapters.catalog import CatalogNode
from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.content import (
    BoundedContentPreview,
    ContentRequest,
    ContentResult,
    ContentStream,
    ContentUpdated,
    EditorContent,
    EditorContentRequest,
    UpdateContentRequest,
)
from app.adapters.explorer.actions import (
    EXPLORER_ACTION_TYPES,
    ExplorerActions,
    ExplorerActionType,
)
from app.adapters.explorer.catalog import ExplorerCatalog
from app.adapters.explorer.content import ExplorerContent
from app.adapters.explorer.fetch import ExplorerFetch
from app.adapters.explorer.new_relation import ExplorerNewRelations
from app.adapters.explorer.query import ExplorerExecution, ExplorerQuery
from app.adapters.explorer.relation import ExplorerRelations
from app.adapters.explorer.samples import write_samples
from app.adapters.explorer.search import ExplorerSearch
from app.adapters.explorer.storage import ROOT, Storage
from app.adapters.explorer.summary import ExplorerSummaries
from app.adapters.explorer.update import ExplorerTableChanges
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
from app.adapters.relation import RelationModel
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
)
from app.adapters.search import (
    LastSearch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    SearchedField,
    SourceCost,
)
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


class Explorer:
    """Facade over a storage and the capabilities built on it.

    A subclass is a source: it builds its storage and says which actions it
    offers. Capabilities are read off the class (D2), so every source built on
    this claims every one of them — which is the point of writing them once.
    """

    # What this kind of source can be asked to do, before one exists. The same
    # tuple its actions are built from, so the catalog cannot advertise an
    # action the driver does not dispatch.
    explorer_action_types: ClassVar[tuple[ExplorerActionType, ...]] = (
        EXPLORER_ACTION_TYPES
    )
    # What walking its tree by name costs. A remote storage lists a folder per
    # round trip, so a walk there is many of them; one on this server's disk
    # says it is cheap.
    name_search_cost: ClassVar[SourceCost] = "costly"

    def __init__(self, storage: Storage) -> None:
        self._storage = storage
        self._catalog = ExplorerCatalog(storage)
        self._content = ExplorerContent(storage)
        self._fetch = ExplorerFetch(storage)
        self._relations = ExplorerRelations(storage)
        self._new_relations = ExplorerNewRelations(storage)
        self._actions = ExplorerActions(storage, self.explorer_action_types)
        self._table_changes = ExplorerTableChanges(storage)
        self._summaries = ExplorerSummaries(storage)
        self._search = ExplorerSearch(storage)
        self._query = ExplorerQuery(storage)

    @property
    def storage(self) -> Storage:
        return self._storage

    async def check_connection(self) -> ConnectionCheckResult:
        return await to_thread.run_sync(self._storage.check)

    async def install_sample_data(self) -> str:
        """The sample files, written into the folder this source stands in."""

        def fill() -> int:
            with self._storage.filled(ROOT) as folder:
                write_samples(folder)
                return sum(1 for _ in folder.iterdir())

        written = await to_thread.run_sync(fill)
        return f"{written} sample files and folders"

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return await self._catalog.path_to(node_id)

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        return await self._search.search_nodes(request, bounds)

    async def search_contents(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        return await self._search.search_contents(request, bounds)

    @classmethod
    def search_cost(cls, field: SearchedField, last: LastSearch | None) -> SourceCost:
        """A walk by name of the storage this source brings (D200)."""
        return cls.name_search_cost if field == "names" else "costly"

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return await self._fetch.fetch(request)

    async def update_cell(self, request: UpdateCellRequest) -> UpdateCellResult:
        return await self._table_changes.update_cell(request)

    async def update_cells(self, request: UpdateCellsRequest) -> UpdateCellsResult:
        return await self._table_changes.update_cells(request)

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        return await self._table_changes.insert_row(request)

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        return await self._table_changes.insert_rows(request)

    async def delete_rows(self, request: DeleteRowsRequest) -> DeleteRowsResult:
        return await self._table_changes.delete_rows(request)

    async def add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        return await self._table_changes.add_column(request)

    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        return await self._table_changes.drop_column(request)

    async def rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        return await self._table_changes.rename_column(request)

    def query_profile(self) -> QueryProfile:
        return self._query.profile()

    def prepare_query(self, text: str) -> PreparedScript:
        return self._query.prepare(text)

    def open_query(self, request: QueryRequest) -> ExplorerExecution:
        return self._query.open(request)

    async def query_metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        return await self._query.metadata(request)

    async def generate_query(self, request: GenerateQueryRequest) -> GeneratedQuery:
        return await self._query.generate(request)

    async def explain_query(self, request: ExplainRequest) -> ExplainResult:
        return await self._query.explain(request)

    async def relation_model(self, node_id: str) -> RelationModel:
        return await self._relations.relation_model(node_id)

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        return await self._new_relations.new_relation_options(parent_node_id)

    async def create_relation(
        self, request: CreateRelationRequest
    ) -> CreateRelationResult:
        return await self._new_relations.create_relation(request)

    async def node_summary(self, node_id: str) -> NodeSummary:
        return await self._summaries.node_summary(node_id)

    async def read_content(self, request: ContentRequest) -> ContentResult:
        return await self._content.read_content(request)

    async def read_editor_content(
        self, request: EditorContentRequest
    ) -> EditorContent:
        return await self._content.read_editor_content(request)

    async def update_content(self, request: UpdateContentRequest) -> ContentUpdated:
        return await self._content.update_content(request)

    async def preview_content(
        self, request: ContentRequest
    ) -> BoundedContentPreview:
        return await self._content.preview_content(request)

    async def open_content_stream(self, request: ContentRequest) -> ContentStream:
        return await self._content.open_content_stream(request)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return await self._actions.available(node_id)

    def action(self, name: str) -> Action[Any]:
        return self._actions.action(name)

    async def all_actions(self) -> list[Action[Any]]:
        return await self._actions.all_actions()

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return cls.explorer_action_types
