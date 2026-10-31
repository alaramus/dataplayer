from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from app.adapters.actions import Action, ActionType
from app.adapters.cache import CacheArea
from app.adapters.catalog import CatalogNode
from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    ColumnTypeChangeResult,
    ColumnTypeRequest,
    DropColumnRequest,
    RenameColumnRequest,
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
from app.adapters.mongodb.actions import MONGODB_ACTION_TYPES, MongodbActions
from app.adapters.mongodb.catalog import MongodbCatalog
from app.adapters.mongodb.console import console_program
from app.adapters.mongodb.content import MongodbContent
from app.adapters.mongodb.export import MongodbExport
from app.adapters.mongodb.fetch import MongodbFetch
from app.adapters.mongodb.options import MongodbOptions
from app.adapters.mongodb.relation import MongodbRelation
from app.adapters.mongodb.report_pages import report_page
from app.adapters.mongodb.reports import in_section, report_for
from app.adapters.mongodb.row_commands import MongodbRowCommands
from app.adapters.mongodb.search import MongodbSearch
from app.adapters.mongodb.session import (
    MongodbSession,
    compose_url,
    compose_url_with_password,
    options_from_url,
)
from app.adapters.mongodb.structure import MongodbStructure
from app.adapters.mongodb.summary import MongodbSummaries
from app.adapters.mongodb.update import MongodbUpdate
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.adapters.registry import AdapterContext, register
from app.adapters.relation import RelationModel, RelationModelsRequest
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
from app.core.schemas import get_datetime_utc
from app.core.translation import N_, say


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


def _address(options: Mapping[str, Any]) -> dict[str, Any] | None:
    host = options.get("host")
    if not isinstance(host, str) or host == "":
        return None
    named = options.get("auth_method") == "user_password"
    return {
        "host": host,
        "port": _as_port(options.get("port")),
        "user": _as_text(options.get("user")) if named else "",
        "database": _as_text(options.get("database")),
        "auth_source": _as_text(options.get("auth_source")) if named else "",
        "tls": options.get("tls") is True,
    }


class MongodbAdapter:
    """Facade over a session and the capabilities built on it (D2b).

    What a source of this type cannot do yet it does not claim: a capability
    arrives as a module composed here, and the registry reads it off the class.
    """

    def __init__(
        self,
        options: MongodbOptions,
        pooling: Pooling | None = None,
        tunnels: TunnelAccess | None = None,
    ) -> None:
        self._session = MongodbSession(options, pooling, tunnels)
        self._catalog = MongodbCatalog(self._session)
        self._relation = MongodbRelation(self._session)
        self._fetch = MongodbFetch(self._session, self._relation)
        self._content = MongodbContent(self._session, self._relation)
        self._update = MongodbUpdate(self._session, self._relation)
        self._structure = MongodbStructure(self._session, self._relation)
        self._export = MongodbExport(self._session, self._fetch)
        self._row_commands = MongodbRowCommands(self._session)
        self._search = MongodbSearch(self._session, self._catalog)
        self._actions = MongodbActions(self._session, self._catalog)
        self._summaries = MongodbSummaries(self._relation)

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
        address = _address(options)
        return None if address is None else compose_url(**address)

    @classmethod
    def connection_url_with_password(cls, options: Mapping[str, Any]) -> str | None:
        address = _address(options)
        if address is None:
            return None
        password = options.get("password") if address["user"] else ""
        return compose_url_with_password(
            **address, password=password if isinstance(password, str) else ""
        )

    def connection_string(self) -> str:
        return self._session.connection_string()

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def source_features(self) -> SourceFeatures:
        try:
            version: str | None = f"MongoDB {(await self._session.profile()).text}"
        except AdapterError:
            version = None
        return SourceFeatures(
            observed_at=get_datetime_utc(), server_version=version, features=[]
        )

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return await self._catalog.path_to(node_id)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        report = report_for(request.node_id)
        if report is not None:
            return await report_page(self._session, report, request)
        if in_section(request.node_id):
            raise ValueError(
                say('"{node_id}" is not a report of this source', node_id=request.node_id)
            )
        return await self._fetch.fetch(request)

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        return self._export.export_rows(request)

    def row_commands(self, node_id: str) -> list[RowCommand]:
        return self._row_commands.for_node(node_id)

    async def run_row_command(
        self, node_id: str, name: str, keys: Sequence[str]
    ) -> RowCommandResult:
        """Stop an operation from its report (D289)."""
        return await self._row_commands.run(node_id, name, keys)

    def enumerate_names(self, limit: int, bounds: SearchBounds) -> AsyncIterator[NameBatch]:
        return self._search.enumerate_names(limit, bounds)

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        return await self._search.search_nodes(request, bounds)

    @classmethod
    def search_cost(cls, field: SearchedField, last: LastSearch | None) -> SourceCost:
        """Names are a listing per database; fields are not searched (D289)."""
        return "cheap" if field == "names" else "costly"

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        return MONGODB_ACTION_TYPES

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return await self._actions.available(node_id)

    def action(self, name: str) -> Action[Any]:
        return self._actions.action(name)

    async def all_actions(self) -> list[Action[Any]]:
        return await self._actions.all_actions()

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
        """One field of one document, if it is still the document read (D287)."""
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
        """The field, null, in every document without it (D288)."""
        return await self._structure.add_column(request)

    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        return await self._structure.drop_column(request)

    async def rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        return await self._structure.rename_column(request)

    async def change_column_type(self, request: ColumnTypeRequest) -> ColumnTypeChangeResult:
        """Converted by the server, counted first and refused if any would not."""
        return await self._structure.change_column_type(request)

    async def create_index(self, request: CreateIndexRequest) -> CreateIndexResult:
        return await self._structure.create_index(request)

    async def drop_index(self, request: DropIndexRequest) -> IndexDropped:
        return await self._structure.drop_index(request)

    async def console_program(self) -> ConsoleProgram:
        """mongosh, signed in as this connection, in a container (D286)."""
        return console_program(self._session)


@register(
    name="mongodb",
    title=N_("MongoDB"),
    category="document",
    description=N_(
        "A MongoDB server. Browse databases, collections and views, and read "
        "documents a page at a time as rows, their fields found from the "
        "documents themselves, with sorting and filtering done by the server, "
        "and work in mongosh in a terminal."
    ),
    options_schema=MongodbOptions,
    adapter_class=MongodbAdapter,
)
def _build(options: MongodbOptions, context: AdapterContext) -> MongodbAdapter:
    return MongodbAdapter(options, context.pooling, context.tunnels)
