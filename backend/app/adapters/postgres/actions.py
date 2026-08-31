"""Catalog actions owned by PostgreSQL."""

from collections.abc import Mapping
from functools import partial
from pathlib import PurePosixPath
from typing import Any, ClassVar, Protocol

from anyio import to_thread
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.adapters.actions import (
    CHUNK_BYTES,
    Action,
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActionSet,
    ActionType,
    ActsOn,
    FileAction,
    FilePayload,
    JsonAction,
    NodeReplacement,
)
from app.adapters.catalog import NodeKind, SchemaNode, TableNode, ViewNode
from app.adapters.delimited import DelimitedTable, read_table
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.relation_changes import PostgresRelationChanges
from app.adapters.postgres.session import PostgresSession
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)
from app.core.access import Access


def _relation_name(value: str) -> str:
    if value == "" or value != value.strip():
        raise ValueError("A relation name cannot be empty or start or end with spaces")
    if len(value.encode("utf-8")) > 63:
        raise ValueError("A PostgreSQL relation name cannot exceed 63 bytes")
    return value


class RenameRelationParams(BaseModel):
    new_name: str = Field(
        title="New name", json_schema_extra={"x-ui-purpose": "node-name"}
    )

    _check = field_validator("new_name")(_relation_name)


class RenameRelation(JsonAction[RenameRelationParams]):
    name: ClassVar[str] = "rename_relation"
    title: ClassVar[str] = "Rename"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    # Renaming a relation is DDL, and it is the shape of the source that
    # changes; someone who may edit rows is not thereby allowed to do it.
    requires: ClassVar[Access] = "structure"
    params_model = RenameRelationParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(
        self, node_id: str | None, params: RenameRelationParams
    ) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", "Choose a relation to rename")
        path = await self._catalog.path_to(node_id)
        node = path[-1]
        if not isinstance(node, (TableNode, ViewNode)) or node.is_system:
            raise ActionRefused("not_applicable", "This relation cannot be renamed")
        if params.new_name == node.name:
            raise ActionRefused("conflict", "The relation already has that name")

        schema = path[0].name
        siblings = await self._catalog.list_children(schema)
        if params.new_name in {sibling.name for sibling in siblings}:
            raise ActionRefused(
                "conflict", f'{schema} already has a relation named "{params.new_name}"'
            )

        if isinstance(node, TableNode):
            command = sql.SQL("ALTER TABLE")
        elif node.is_materialized:
            command = sql.SQL("ALTER MATERIALIZED VIEW")
        else:
            command = sql.SQL("ALTER VIEW")
        statement = sql.SQL("{} {} RENAME TO {}").format(
            command,
            sql.Identifier(schema, node.name),
            sql.Identifier(params.new_name),
        )
        await self._session.schema_change(statement.as_string())
        new_node_id = f"{schema}.{params.new_name}"
        return ActionResult(
            message=f"Renamed to {params.new_name}",
            reload_node_id=schema,
            replacement=NodeReplacement(
                old_node_id=node_id,
                new_node_id=new_node_id,
                title=params.new_name,
            ),
        )


# How many rows one loaded file may bring. More than this is a durable job
# with progress and cancellation, which is Phase 4. Refused rather than
# truncated: the reader handed over a whole file and would have no way of
# knowing that only its beginning arrived.
CSV_ROW_CEILING = 5000

# How much of the file is read before it is refused. The rows are parsed from
# what arrived rather than from a temporary file, so this is what bounds the
# memory of one request; the row ceiling alone would not, since one row can be
# as long as the whole file.
CSV_MAX_BYTES = 16 * 1024 * 1024


def _stem(filename: str) -> str:
    """The file's own name without its extension, and without any directory.

    Only ever the default of a form field, never a path: a browser that sends
    a full name should still suggest the last part of it.
    """
    tail = filename.replace("\\", "/").rsplit("/", 1)[-1]
    return PurePosixPath(tail).stem


class LoadCsvColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)


class LoadCsvParams(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"x-ui-workflow": "file-to-relation"}
    )

    name: str = Field(
        default="",
        title="Table name",
        description="Leave empty to name the table after the file",
        json_schema_extra={"x-ui-purpose": "filename-stem"},
    )
    schema_name: str = Field(default="", title="Schema")
    create_schema: bool = False
    columns: list[LoadCsvColumn] | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def named_or_empty(cls, value: str) -> str:
        return value if value == "" else _relation_name(value)

    @model_validator(mode="after")
    def distinct_columns(self) -> LoadCsvParams:
        columns = self.columns or []
        sources = [column.source for column in columns]
        targets = [column.target for column in columns]
        if len(sources) != len(set(sources)):
            raise ValueError("A source column may be selected only once")
        if len(targets) != len(set(targets)):
            raise ValueError("A target column may be named only once")
        return self


class LoadCsv(FileAction[LoadCsvParams]):
    """A delimited file, uploaded, becomes a table of the schema being read.

    An action rather than a route of its own, so the button for it appears in
    the catalog without the screen learning anything about PostgreSQL: what a
    source offers, what its form holds and whether it carries a file are all
    read off this declaration (D9, D13).
    """

    name: ClassVar[str] = "load_csv"
    title: ClassVar[str] = "Load from CSV"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    # It makes something inside the schema rather than changing the schema, so
    # it belongs to the place being looked at rather than to what is ticked.
    acts_on: ClassVar[ActsOn] = "children"
    # Creating a relation is DDL: someone who may edit rows may not do it.
    requires: ClassVar[Access] = "structure"
    # One file is one table. Loading it into three schemas at once is not the
    # same kind of thing as deleting three files with one form.
    bulk: ClassVar[bool] = False
    params_model = LoadCsvParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog
        self._relations = PostgresRelationChanges(session, catalog)

    async def run(
        self, node_id: str | None, params: LoadCsvParams, payload: FilePayload
    ) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", "Choose a schema to load into")
        schema = params.schema_name or node_id
        if params.create_schema:
            await self._create_schema(schema)
        else:
            schemas = await self._catalog.list_children(None)
            if schema not in {node.id for node in schemas if isinstance(node, SchemaNode)}:
                raise ActionRefused("not_applicable", f'Schema "{schema}" does not exist')

        name = params.name or _stem(payload.filename or "")
        if name.strip() == "":
            raise ActionRefused(
                "not_applicable", "The file has no name to use; type one"
            )
        _relation_name(name)

        siblings = await self._catalog.list_children(schema)
        if name in {sibling.name for sibling in siblings}:
            raise ActionRefused("conflict", f"{name} is already there")

        table = await self._read(payload)
        if not table.columns:
            raise ActionRefused(
                "not_applicable", "That file has no first line to name columns"
            )
        if table.more:
            raise ActionRefused(
                "too_large",
                f"A file loaded this way may hold at most {CSV_ROW_CEILING} rows",
            )

        selected = (
            [LoadCsvColumn(source=column, target=column) for column in table.columns]
            if params.columns is None
            else params.columns
        )
        positions = {column: index for index, column in enumerate(table.columns)}
        for column in selected:
            if column.source not in positions:
                raise ActionRefused(
                    "not_applicable", f'The file has no column "{column.source}"'
                )
            _relation_name(column.target)
        if not selected:
            raise ActionRefused("not_applicable", "Choose at least one column")

        result = await self._relations.create_relation(
            CreateRelationRequest(
                parent_node_id=schema,
                name=name,
                # Every column is text, because a delimited file states no
                # types and one read off its rows would depend on how many of
                # them were looked at. A column takes another type afterwards
                # through the change that counts the rows in its way (D38).
                columns=[
                    NewColumn(name=column.target, type_code="text")
                    for column in selected
                ],
                rows=[
                    [row[positions[column.source]] for column in selected]
                    for row in table.rows
                ],
            )
        )
        if not isinstance(result, RelationCreated):
            # Unreachable while every column is text, and answered rather than
            # ignored: what a value may be is the source's to say, not this
            # action's to assume.
            cell = result.cells[0]
            raise ActionRefused(
                "not_applicable",
                f"Row {cell.row + 1}, column {cell.column}: that value cannot be read",
            )
        return ActionResult(
            message=f"{name} created with {result.inserted} rows",
            # A new schema itself is a child of the root. Existing schemas only
            # gain the relation below them.
            reload_node_id=None if params.create_schema else schema,
        )

    async def _create_schema(self, schema: str) -> None:
        _relation_name(schema)
        schemas = await self._catalog.list_children(None)
        if schema in {node.id for node in schemas if isinstance(node, SchemaNode)}:
            raise ActionRefused("conflict", f'Schema "{schema}" already exists')
        await self._session.schema_change(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)).as_string(),
            refusals={"42501": "This connection may not create schemas"},
        )

    async def _read(self, payload: FilePayload) -> DelimitedTable:
        """The upload, as columns and rows.

        Held whole rather than staged on disk: it has to be parsed anyway, and
        the two ceilings say what "whole" may mean. Parsing is blocking work,
        so it goes to a worker thread.
        """
        chunks: list[bytes] = []
        size = 0
        while chunk := await payload.read(CHUNK_BYTES):
            size += len(chunk)
            if size > CSV_MAX_BYTES:
                raise ActionRefused(
                    "too_large",
                    "A file loaded this way must be under "
                    f"{CSV_MAX_BYTES // (1024 * 1024)} MB",
                )
            chunks.append(chunk)
        # errors="replace" for the reason the file source reads that way: one
        # byte that is not text is not a reason to refuse the whole file.
        text = b"".join(chunks).decode("utf-8", errors="replace")
        return await to_thread.run_sync(
            partial(read_table, text, payload.filename or "", CSV_ROW_CEILING)
        )


# What a refused drop means, by SQLSTATE. The code is safe to look at and the
# message beside it is not, so the wording is ours; the DETAIL of the first of
# them is the list of what stands in the way, and that is passed on.
DROP_REFUSALS = {
    # dependent_objects_still_exist.
    "2BP01": "Something else is built on this relation",
    # lock_not_available: somebody is reading or writing it right now.
    "55P03": "Something is using this relation; try again in a moment",
    # insufficient_privilege.
    "42501": "This connection may not drop that relation",
}


class DropRelationParams(BaseModel):
    cascade: bool = Field(
        default=False,
        title="Also drop everything built on it",
        description="Required when a view or a reference depends on this relation",
    )


class DropRelation(JsonAction[DropRelationParams]):
    """Drop one relation, with or without what stands on it.

    Previewable, and that is the point of it: what a cascade takes with it is
    written in `pg_depend`, and the only answer worth showing somebody about to
    destroy something is PostgreSQL's own. So the preview is the drop itself,
    rolled back, and what it lists cannot disagree with what happens.
    """

    name: ClassVar[str] = "drop_relation"
    title: ClassVar[str] = "Drop"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    # One at a time, unlike deleting files: what a drop takes with it is the
    # whole question here, and one list of consequences cannot be told apart
    # into five relations' worth by whoever reads it.
    bulk: ClassVar[bool] = False
    params_model = DropRelationParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(
        self, node_id: str | None, params: DropRelationParams
    ) -> ActionResult:
        schema, node = await self._target(node_id)
        await self._session.schema_change(
            self._statement(schema, node, cascade=params.cascade),
            refusals=DROP_REFUSALS,
        )
        return ActionResult(message=f"{node.name} dropped", reload_node_id=schema)

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        """What this drop would take with it, as the server itself reports it.

        The same statement the form describes, so ticking the box changes the
        answer: without a cascade a relation something is built on refuses, and
        the refusal names what is in the way; with one, the server lists what
        it would drop as it goes.
        """
        params = self._validated(raw)
        schema, node = await self._target(node_id)
        rehearsal = await self._session.rehearse(
            self._statement(schema, node, cascade=params.cascade),
            refusals=DROP_REFUSALS,
        )
        if rehearsal.refused is not None:
            # An answer rather than a failure: the question was "what would
            # happen", and what would happen is that it would be refused.
            return ActionPreview(
                summary=rehearsal.refused, items=rehearsal.said, blocked=True
            )
        if not rehearsal.said:
            return ActionPreview(summary=f"Nothing else depends on {node.name}")
        # The lines are the server's own sentences, so the summary leaves room
        # for them to say what they say rather than repeating half of it.
        return ActionPreview(
            summary=f"What dropping {node.name} would do:", items=rehearsal.said
        )

    async def _target(self, node_id: str | None) -> tuple[str, TableNode | ViewNode]:
        if node_id is None:
            raise ActionRefused("not_applicable", "Choose a relation to drop")
        path = await self._catalog.path_to(node_id)
        node = path[-1]
        if not isinstance(node, TableNode | ViewNode) or node.is_system:
            raise ActionRefused("not_applicable", "This relation cannot be dropped")
        return path[0].name, node

    @staticmethod
    def _statement(
        schema: str, node: TableNode | ViewNode, *, cascade: bool
    ) -> str:
        """The DROP this node needs, with its own kind of relation named.

        Composed from the catalog's description rather than from a guess: a
        materialized view is not dropped by DROP VIEW, and PostgreSQL says so
        with an error that names neither.
        """
        if isinstance(node, TableNode):
            command = sql.SQL("DROP TABLE")
        elif node.is_materialized:
            command = sql.SQL("DROP MATERIALIZED VIEW")
        else:
            command = sql.SQL("DROP VIEW")
        statement = sql.SQL("{} {}").format(
            command, sql.Identifier(schema, node.name)
        )
        if cascade:
            statement += sql.SQL(" CASCADE")
        return statement.as_string()


class PostgresActionType(ActionType, Protocol):
    def __call__(
        self, session: PostgresSession, catalog: PostgresCatalog
    ) -> Action[Any]: ...


POSTGRES_ACTION_TYPES: tuple[PostgresActionType, ...] = (
    RenameRelation,
    LoadCsv,
    DropRelation,
)


class PostgresActions:
    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._catalog = catalog
        self._relations = PostgresRelationChanges(session, catalog)
        self._actions = ActionSet(
            [action_type(session, catalog) for action_type in POSTGRES_ACTION_TYPES]
        )

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        if node_id is None:
            return []
        path = await self._catalog.path_to(node_id)
        node = path[-1]
        if isinstance(node, SchemaNode):
            # Whether a schema will take a new relation is the schema's own
            # answer, asked here so that the rule is not stated a second time.
            options = await self._relations.new_relation_options(node_id)
            return self._actions.for_kind(node.kind) if options.supported else []
        if isinstance(node, (TableNode, ViewNode)) and not node.is_system:
            return self._actions.for_kind(node.kind)
        return []
