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
from app.adapters.catalog import (
    NodeKind,
    ReportNode,
    SchemaNode,
    TableNode,
    ViewNode,
)
from app.adapters.delimited import DelimitedTable, read_table
from app.adapters.postgres.catalog import PostgresCatalog, is_system_schema
from app.adapters.postgres.relation_changes import PostgresRelationChanges
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import EXTENSIONS_REPORT_ID
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


def _schema_name(value: str) -> str:
    if value == "" or value != value.strip():
        raise ValueError("A schema name cannot be empty or start or end with spaces")
    if len(value.encode("utf-8")) > 63:
        raise ValueError("A PostgreSQL schema name cannot exceed 63 bytes")
    return value


SCHEMA_CHANGE_REFUSALS = {
    # insufficient_privilege.
    "42501": "This connection may not change schemas",
    # reserved_name: PostgreSQL reserves pg_ for its own schemas.
    "42939": "That schema name is reserved by PostgreSQL",
}


async def _existing_schema(session: PostgresSession, name: str) -> str | None:
    """The server's exact spelling of one schema, or nothing."""
    rows = await session.query(
        "SELECT nspname AS name FROM pg_catalog.pg_namespace WHERE nspname = %s",
        (name,),
    )
    return None if not rows else str(rows[0]["name"])


async def _schema_target(
    catalog: PostgresCatalog, node_id: str | None, *, action: str, refused_as: str
) -> SchemaNode:
    if node_id is None:
        raise ActionRefused("not_applicable", f"Choose a schema to {action}")
    node = (await catalog.path_to(node_id))[-1]
    if not isinstance(node, SchemaNode) or node.is_system:
        raise ActionRefused("not_applicable", f"This schema cannot be {refused_as}")
    return node


class CreateSchemaParams(BaseModel):
    name: str = Field(title="Name")

    _check = field_validator("name")(_schema_name)


class CreateSchema(JsonAction[CreateSchemaParams]):
    """Create a grouping at the current catalog level, not inside one."""

    name: ClassVar[str] = "create_schema"
    title: ClassVar[str] = "New schema"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset()
    acts_on: ClassVar[ActsOn] = "level"
    requires: ClassVar[Access] = "structure"
    params_model = CreateSchemaParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session

    async def run(
        self, node_id: str | None, params: CreateSchemaParams
    ) -> ActionResult:
        if node_id is not None:
            raise ActionRefused(
                "not_applicable", "Schemas are created at the top of the connection"
            )
        if is_system_schema(params.name):
            raise ActionRefused(
                "not_applicable", "That schema name belongs to the server"
            )
        if await _existing_schema(self._session, params.name) is not None:
            raise ActionRefused(
                "conflict", f'Schema "{params.name}" already exists'
            )
        statement = sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(params.name))
        await self._session.schema_change(
            statement.as_string(), refusals=SCHEMA_CHANGE_REFUSALS
        )
        return ActionResult(
            message=f"Schema {params.name} created",
            # Clear a branch left under the same opaque id by an earlier drop,
            # as well as the root that gained this grouping.
            reload_node_ids=[None, params.name],
        )


class RenameSchemaParams(BaseModel):
    new_name: str = Field(
        title="New name", json_schema_extra={"x-ui-purpose": "node-name"}
    )

    _check = field_validator("new_name")(_schema_name)


class RenameSchema(JsonAction[RenameSchemaParams]):
    name: ClassVar[str] = "rename_schema"
    title: ClassVar[str] = "Rename schema"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    params_model = RenameSchemaParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(
        self, node_id: str | None, params: RenameSchemaParams
    ) -> ActionResult:
        node = await _schema_target(
            self._catalog, node_id, action="rename", refused_as="renamed"
        )
        if params.new_name == node.name:
            raise ActionRefused("conflict", "The schema already has that name")
        if is_system_schema(params.new_name):
            raise ActionRefused(
                "not_applicable", "That schema name belongs to the server"
            )
        if await _existing_schema(self._session, params.new_name) is not None:
            raise ActionRefused(
                "conflict", f'Schema "{params.new_name}" already exists'
            )
        statement = sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(
            sql.Identifier(node.name), sql.Identifier(params.new_name)
        )
        await self._session.schema_change(
            statement.as_string(), refusals=SCHEMA_CHANGE_REFUSALS
        )
        return ActionResult(
            message=f"Schema {node.name} renamed to {params.new_name}",
            reload_node_ids=[None, node.name, params.new_name],
            replacement=NodeReplacement(
                old_node_id=node.name,
                new_node_id=params.new_name,
                title=params.new_name,
            ),
        )


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
            reload_node_ids=[schema],
            replacement=NodeReplacement(
                old_node_id=node_id,
                new_node_id=new_node_id,
                title=params.new_name,
            ),
        )


class MoveRelationParams(BaseModel):
    # The destinations are the source's own groupings, and only the source can
    # list them. The hint says the value is one of their ids, so the form
    # offers what this connection actually has instead of asking for a name
    # that has to be spelled exactly right to be accepted.
    target_schema: str = Field(
        title="Target schema", json_schema_extra={"x-ui-purpose": "grouping"}
    )

    _check = field_validator("target_schema")(_schema_name)


class MoveRelation(JsonAction[MoveRelationParams]):
    """Move one source-issued relation and name both changed branches."""

    name: ClassVar[str] = "move_relation"
    title: ClassVar[str] = "Move to schema"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    params_model = MoveRelationParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(
        self, node_id: str | None, params: MoveRelationParams
    ) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", "Choose a relation to move")
        path = await self._catalog.path_to(node_id)
        node = path[-1]
        if not isinstance(node, TableNode | ViewNode) or node.is_system:
            raise ActionRefused("not_applicable", "This relation cannot be moved")

        source_schema = path[0].name
        if params.target_schema == source_schema:
            raise ActionRefused(
                "conflict", f"The relation is already in {source_schema}"
            )
        target_name = await _existing_schema(self._session, params.target_schema)
        if target_name is None:
            raise ActionRefused(
                "not_applicable",
                f'Schema "{params.target_schema}" does not exist',
            )
        if is_system_schema(target_name):
            raise ActionRefused(
                "not_applicable", "Relations cannot be moved into a system schema"
            )
        siblings = await self._catalog.list_children(target_name)
        if node.name in {sibling.name for sibling in siblings}:
            raise ActionRefused(
                "conflict",
                f'{target_name} already has a relation named "{node.name}"',
            )

        if isinstance(node, TableNode):
            command = sql.SQL("ALTER TABLE")
        elif node.is_materialized:
            command = sql.SQL("ALTER MATERIALIZED VIEW")
        else:
            command = sql.SQL("ALTER VIEW")
        statement = sql.SQL("{} {} SET SCHEMA {}").format(
            command,
            sql.Identifier(source_schema, node.name),
            sql.Identifier(target_name),
        )
        await self._session.schema_change(
            statement.as_string(),
            refusals={"42501": "This connection may not move that relation"},
        )
        new_node_id = f"{target_name}.{node.name}"
        return ActionResult(
            message=f"{node.name} moved to {target_name}",
            reload_node_ids=[source_schema, target_name],
            replacement=NodeReplacement(
                old_node_id=node_id,
                new_node_id=new_node_id,
                title=node.name,
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
            reload_node_ids=[None, schema] if params.create_schema else [schema],
        )

    async def _create_schema(self, schema: str) -> None:
        _schema_name(schema)
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
        return ActionResult(message=f"{node.name} dropped", reload_node_ids=[schema])

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


DROP_SCHEMA_REFUSALS = {
    # dependent_objects_still_exist.
    "2BP01": "The schema is not empty",
    # lock_not_available.
    "55P03": "Something is using this schema; try again in a moment",
    # insufficient_privilege.
    "42501": "This connection may not drop that schema",
}


class DropSchemaParams(BaseModel):
    cascade: bool = Field(
        default=False,
        title="Also drop everything in it",
        description="Required when the schema still contains objects",
    )


class DropSchema(JsonAction[DropSchemaParams]):
    """Drop one user schema after rehearsing PostgreSQL's exact statement."""

    name: ClassVar[str] = "drop_schema"
    title: ClassVar[str] = "Drop schema"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    params_model = DropSchemaParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(
        self, node_id: str | None, params: DropSchemaParams
    ) -> ActionResult:
        node = await _schema_target(
            self._catalog, node_id, action="drop", refused_as="dropped"
        )
        await self._session.schema_change(
            self._statement(node.name, cascade=params.cascade),
            refusals=DROP_SCHEMA_REFUSALS,
        )
        return ActionResult(
            message=f"Schema {node.name} dropped",
            reload_node_ids=[None, node.name],
        )

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        params = self._validated(raw)
        node = await _schema_target(
            self._catalog, node_id, action="drop", refused_as="dropped"
        )
        rehearsal = await self._session.rehearse(
            self._statement(node.name, cascade=params.cascade),
            refusals=DROP_SCHEMA_REFUSALS,
        )
        if rehearsal.refused is not None:
            return ActionPreview(
                summary=rehearsal.refused, items=rehearsal.said, blocked=True
            )
        if not rehearsal.said:
            return ActionPreview(summary=f"Schema {node.name} is empty")
        return ActionPreview(
            summary=f"What dropping {node.name} would do:", items=rehearsal.said
        )

    @staticmethod
    def _statement(schema: str, *, cascade: bool) -> str:
        statement = sql.SQL("DROP SCHEMA {}").format(sql.Identifier(schema))
        if cascade:
            statement += sql.SQL(" CASCADE")
        return statement.as_string()


EXTENSION_REFUSALS = {
    # duplicate_object: a backstop. Installing one already installed is
    # refused by name before the statement runs, but two callers can still
    # race, and the second must read like a refusal rather than a fault.
    "42710": "That extension is already installed",
    # dependent_objects_still_exist.
    "2BP01": "Something in this database is built on that extension",
    # insufficient_privilege: installing one usually needs a superuser.
    "42501": "This connection may not change the extensions of this server",
    # undefined_file: the extension is listed but its files are not installed.
    "58P01": "The server lists that extension but cannot find its files",
}


class ExtensionParams(BaseModel):
    name: str = Field(title="Extension")


class CreateExtensionParams(ExtensionParams):
    include_requirements: bool = Field(
        default=False,
        title="Also install what it requires",
        description="Some extensions are built on others, which are installed too",
    )


class ExtensionAction[P: ExtensionParams](JsonAction[P]):
    """What the two extension commands share: where they live and what they name.

    Offered on the Extensions report and nowhere else. `applies_to` says the
    command makes sense for a report; which report admits it is a question of
    state, and `PostgresActions.available` answers it — the split the action
    contract already draws.
    """

    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"report"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = False

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def _named(self, typed: str, *, installed: bool) -> str:
        """The server's own spelling of an extension it knows, or a refusal.

        The client's text selects a row; the identifier that reaches the
        statement is the `extname` that came back, never the string that was
        typed. So the only extension that can be named is one this server
        already lists.
        """
        if installed:
            rows = await self._session.query(
                "SELECT extname AS name FROM pg_extension WHERE extname = %s",
                (typed,),
            )
            if not rows:
                raise ActionRefused(
                    "not_applicable", f'"{typed}" is not installed on this server'
                )
            return str(rows[0]["name"])

        rows = await self._session.query(
            """
            SELECT name, installed_version IS NOT NULL AS already
            FROM pg_available_extensions WHERE name = %s
            """,
            (typed,),
        )
        if not rows:
            raise ActionRefused(
                "not_applicable",
                f'This server does not offer an extension called "{typed}"',
            )
        # A name that is taken is a conflict, not a fault: the same shape the
        # file source answers with when a folder of that name already exists.
        if rows[0]["already"]:
            raise ActionRefused("conflict", f'"{typed}" is already installed')
        return str(rows[0]["name"])

    def _refuse_unless_extensions_report(self, node_id: str | None) -> None:
        if node_id != EXTENSIONS_REPORT_ID:
            raise ActionRefused(
                "not_applicable", "Extensions are changed from the Extensions report"
            )


class CreateExtension(ExtensionAction[CreateExtensionParams]):
    name: ClassVar[str] = "create_extension"
    title: ClassVar[str] = "Install extension"
    params_model = CreateExtensionParams

    async def run(
        self, node_id: str | None, params: CreateExtensionParams
    ) -> ActionResult:
        self._refuse_unless_extensions_report(node_id)
        named = await self._named(params.name, installed=False)
        await self._session.schema_change(
            self._statement(named, requirements=params.include_requirements),
            refusals=EXTENSION_REFUSALS,
        )
        # The root, not the report: an extension may bring a schema of its own,
        # and what changed is more than the list it was installed from.
        return ActionResult(message=f"{named} installed", reload_node_ids=[None])

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        """What installing it would do, in the server's own words.

        Worth previewing for the same reason a drop is: with requirements
        included the server installs more than was asked for, and it says so
        as it goes. Ticking the box changes the answer.
        """
        params = self._validated(raw)
        self._refuse_unless_extensions_report(node_id)
        named = await self._named(params.name, installed=False)
        rehearsal = await self._session.rehearse(
            self._statement(named, requirements=params.include_requirements),
            refusals=EXTENSION_REFUSALS,
        )
        if rehearsal.refused is not None:
            return ActionPreview(
                summary=rehearsal.refused, items=rehearsal.said, blocked=True
            )
        if not rehearsal.said:
            return ActionPreview(summary=f"{named} installs on its own")
        return ActionPreview(
            summary=f"What installing {named} would do:", items=rehearsal.said
        )

    @staticmethod
    def _statement(named: str, *, requirements: bool) -> str:
        statement = sql.SQL("CREATE EXTENSION {}").format(sql.Identifier(named))
        # CASCADE here means "install what this one is built on", which is a
        # different promise from a cascading drop and is asked for by name.
        if requirements:
            statement += sql.SQL(" CASCADE")
        return statement.as_string()


class DropExtension(ExtensionAction[ExtensionParams]):
    """Remove an extension, and never what was built on it.

    No cascade, deliberately. A relation dropped with one is a thing the
    reader chose and can see; an extension's cascade reaches whatever anyone
    ever built on its types and functions, and the preview naming that is a
    better answer than a box that would destroy it.
    """

    name: ClassVar[str] = "drop_extension"
    title: ClassVar[str] = "Remove extension"
    destructive: ClassVar[bool] = True
    params_model = ExtensionParams

    async def run(self, node_id: str | None, params: ExtensionParams) -> ActionResult:
        self._refuse_unless_extensions_report(node_id)
        named = await self._named(params.name, installed=True)
        await self._session.schema_change(
            self._statement(named), refusals=EXTENSION_REFUSALS
        )
        return ActionResult(message=f"{named} removed", reload_node_ids=[None])

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        params = self._validated(raw)
        self._refuse_unless_extensions_report(node_id)
        named = await self._named(params.name, installed=True)
        rehearsal = await self._session.rehearse(
            self._statement(named), refusals=EXTENSION_REFUSALS
        )
        if rehearsal.refused is not None:
            return ActionPreview(
                summary=rehearsal.refused, items=rehearsal.said, blocked=True
            )
        return ActionPreview(summary=f"Nothing in this database uses {named}")

    @staticmethod
    def _statement(named: str) -> str:
        return sql.SQL("DROP EXTENSION {}").format(sql.Identifier(named)).as_string()


class PostgresActionType(ActionType, Protocol):
    def __call__(
        self, session: PostgresSession, catalog: PostgresCatalog
    ) -> Action[Any]: ...


POSTGRES_ACTION_TYPES: tuple[PostgresActionType, ...] = (
    CreateSchema,
    RenameSchema,
    RenameRelation,
    MoveRelation,
    LoadCsv,
    DropRelation,
    DropSchema,
    CreateExtension,
    DropExtension,
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
            return [self._actions.get(CreateSchema.name)]
        path = await self._catalog.path_to(node_id)
        node = path[-1]
        if isinstance(node, SchemaNode):
            # Whether a schema will take a new relation is the schema's own
            # answer, asked here so that the rule is not stated a second time.
            options = await self._relations.new_relation_options(node_id)
            return self._actions.for_kind(node.kind) if options.supported else []
        if isinstance(node, (TableNode, ViewNode)) and not node.is_system:
            return self._actions.for_kind(node.kind)
        # A report admits a command when the command is about what it reports.
        # Said here rather than in `applies_to`, which speaks about kinds:
        # every report is a report, and only one of them is about extensions.
        if isinstance(node, ReportNode) and node_id == EXTENSIONS_REPORT_ID:
            return self._actions.for_kind(node.kind)
        return []
