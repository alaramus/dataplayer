from collections.abc import AsyncIterator, Mapping
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
from app.adapters.export import ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexDropped,
)
from app.adapters.postgres.actions import POSTGRES_ACTION_TYPES, PostgresActions
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.columns import PostgresColumns
from app.adapters.postgres.constraints import PostgresConstraints
from app.adapters.postgres.export import PostgresExport
from app.adapters.postgres.fetch import PostgresFetch
from app.adapters.postgres.indexes import PostgresIndexes
from app.adapters.postgres.options import PostgresOptions
from app.adapters.postgres.references import PostgresReferences
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.postgres.relation_changes import PostgresRelationChanges
from app.adapters.postgres.session import (
    PostgresSession,
    compose_url,
    options_from_url,
)
from app.adapters.postgres.update import PostgresUpdate
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.references import FollowReferenceRequest, ReferenceTarget
from app.adapters.registry import AdapterContext, register
from app.adapters.relation import RelationModel
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
)
from app.adapters.resources import Pooling
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
        self._catalog = PostgresCatalog(self._session)
        self._actions = PostgresActions(self._session, self._catalog)
        self._fetch = PostgresFetch(self._session)
        self._export = PostgresExport(self._session, self._fetch)
        self._update = PostgresUpdate(self._session, self._fetch)
        self._references = PostgresReferences(self._catalog, self._fetch)
        self._relation = PostgresRelation(self._session)
        self._columns = PostgresColumns(self._session, self._relation)
        self._indexes = PostgresIndexes(self._session, self._relation)
        self._constraints = PostgresConstraints(self._session, self._relation)
        self._relations = PostgresRelationChanges(self._session, self._catalog)

    def cache_ttl(self, area: CacheArea) -> float:
        """A short stale window for reads whose source is under our control."""
        return 30.0 if area == "catalog" else 10.0

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        """The same declarations used to build the callable action set."""
        return POSTGRES_ACTION_TYPES

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return await self._actions.available(node_id)

    def action(self, name: str) -> Action[Any]:
        return self._actions.action(name)

    def all_actions(self) -> list[Action[Any]]:
        return self._actions.all_actions()

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

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    def connection_string(self) -> str:
        return self._session.connection_string()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return await self._catalog.path_to(node_id)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return await self._fetch.fetch(request)

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

    async def relation_model(self, node_id: str) -> RelationModel:
        return await self._relation.relation_model(node_id)

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        return await self._relations.new_relation_options(parent_node_id)

    async def create_relation(
        self, request: CreateRelationRequest
    ) -> CreateRelationResult:
        return await self._relations.create_relation(request)

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
