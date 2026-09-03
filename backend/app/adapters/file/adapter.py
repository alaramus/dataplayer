from pathlib import Path, PurePosixPath
from typing import Any

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
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.file.actions import FILE_ACTION_TYPES, FileActions
from app.adapters.file.catalog import FileCatalog
from app.adapters.file.content import FileContent
from app.adapters.file.fetch import FileFetch
from app.adapters.file.options import FileOptions
from app.adapters.file.query import FileExecution, FileQuery
from app.adapters.file.relation import FileRelations
from app.adapters.file.search import FileSearch
from app.adapters.file.session import FileSession
from app.adapters.file.summary import FileSummaries
from app.adapters.file.update import FileTableChanges
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
from app.adapters.relation import RelationModel
from app.adapters.search import NodeSearchRequest, NodeSearchResult
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


class FileAdapter:
    """Facade over a root and the capabilities built on it.

    The root is composed here and nowhere else: the home directory decided by
    the server, plus the folder the user chose inside it.
    """

    def __init__(self, options: FileOptions, context: AdapterContext) -> None:
        root = context.home_dir.joinpath(*PurePosixPath(options.path).parts)
        self._session = FileSession(root)
        self._catalog = FileCatalog(self._session)
        self._content = FileContent(self._session)
        self._fetch = FileFetch(self._session)
        self._relations = FileRelations(self._session)
        self._actions = FileActions(self._session)
        self._table_changes = FileTableChanges(self._session)
        self._summaries = FileSummaries(self._session)
        self._search = FileSearch(self._session)
        self._query = FileQuery(self._session)

    @property
    def root(self) -> Path:
        return self._session.root

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return await self._catalog.path_to(node_id)

    async def search_nodes(self, request: NodeSearchRequest) -> NodeSearchResult:
        return await self._search.search_nodes(request)

    async def search_contents(self, request: NodeSearchRequest) -> NodeSearchResult:
        return await self._search.search_contents(request)

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

    def open_query(self, request: QueryRequest) -> FileExecution:
        return self._query.open(request)

    async def query_metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        return await self._query.metadata(request)

    async def generate_query(self, request: GenerateQueryRequest) -> GeneratedQuery:
        return await self._query.generate(request)

    async def explain_query(self, request: ExplainRequest) -> ExplainResult:
        return await self._query.explain(request)

    async def relation_model(self, node_id: str) -> RelationModel:
        return await self._relations.relation_model(node_id)

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

    def all_actions(self) -> list[Action[Any]]:
        return self._actions.all_actions()

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        """What this type of source can be asked to do, before one exists.

        The same tuple `FileActions` builds its set from, so the catalog
        cannot advertise an action the driver does not dispatch.
        """
        return FILE_ACTION_TYPES


@register(
    name="file",
    title="Files",
    category="files",
    description=(
        "Your personal storage on this server. Browse folders and open files "
        "through representations appropriate to their content."
    ),
    options_schema=FileOptions,
    adapter_class=FileAdapter,
)
def _build(options: FileOptions, context: AdapterContext) -> FileAdapter:
    return FileAdapter(options, context)
