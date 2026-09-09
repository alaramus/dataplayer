"""Catalog actions owned by PostgreSQL."""

from collections.abc import AsyncIterator, Mapping, Sequence
from functools import partial
from pathlib import PurePosixPath
from typing import Any, ClassVar, Protocol

from anyio import to_thread
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.adapters.actions import (
    CHUNK_BYTES,
    Action,
    ActionDownload,
    ActionDownloadMetadata,
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
from app.adapters.model_code import (
    DIALECT_SUFFIX,
    DIALECT_TITLE,
    CodeDialect,
    render,
)
from app.adapters.postgres.catalog import PostgresCatalog, is_system_schema
from app.adapters.postgres.names import name_check
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.postgres.relation_changes import PostgresRelationChanges
from app.adapters.postgres.roles import CreateRole
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import ROLES_REPORT_ID
from app.adapters.postgres.table_design import PostgresTableDesign
from app.adapters.relation import RelationModel
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)
from app.adapters.table_design import DesignRefused, TableDefinition
from app.core.access import Access

_relation_name = name_check("relation")
_schema_name = name_check("schema")


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
    reason = await catalog.schema_action_reason(node.name)
    if reason is None:
        reason = await catalog.cascade_reason(node.name)
    if reason is not None:
        raise ActionRefused("not_applicable", reason)
    return node


async def _guard_relation_action(
    catalog: PostgresCatalog, schema: str, node: TableNode | ViewNode
) -> None:
    reason = await catalog.relation_action_reason(schema, node.name)
    if reason is not None:
        raise ActionRefused("not_applicable", reason)


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
    acts_on: ClassVar[ActsOn] = "group"
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
        await _guard_relation_action(self._catalog, schema, node)
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
    bulk: ClassVar[bool] = True
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
        await _guard_relation_action(self._catalog, source_schema, node)
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
        reason = await self._catalog.schema_action_reason(
            target_name, include_relations=False
        )
        if reason is not None:
            raise ActionRefused("not_applicable", reason)
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


class CreateTableParams(BaseModel):
    # A screen of its own rather than a form: what a table is cannot be asked
    # for with a list of fields, and the editor that asks for it is registered
    # against this workflow rather than against the name of the action (D73).
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"x-ui-workflow": "table-designer"}
    )

    definition: TableDefinition
    # What the reviewer was looking at. The statements are composed again here
    # from the definition, and a definition that no longer composes to the
    # reviewed plan is refused rather than run.
    fingerprint: str = Field(min_length=1, max_length=64)


class CreateTable(JsonAction[CreateTableParams]):
    """Design a table object by object, review the SQL, then create it.

    Distinct from `load_csv` and from keeping rows as a table: both of those
    make a relation out of data that already exists and take their columns from
    it. This one starts from nothing, so the keys, the indexes and the checks
    are part of what is being asked for (D117).
    """

    name: ClassVar[str] = "create_table"
    title: ClassVar[str] = "Create table"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    # It makes something inside the schema rather than changing the schema, as
    # loading a file does.
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    # One design is one table. Applying a draft to every selected schema would
    # be creating things nobody looked at a plan for.
    bulk: ClassVar[bool] = False
    params_model = CreateTableParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._design = PostgresTableDesign(session, catalog, PostgresRelation(session))

    async def run(
        self, node_id: str | None, params: CreateTableParams
    ) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", "Choose a schema to create it in")
        try:
            node = await self._design.create_table(
                node_id, params.definition, params.fingerprint
            )
        except DesignRefused as refused:
            raise ActionRefused(
                "conflict" if refused.problem.kind == "conflict" else "not_applicable",
                refused.problem.message,
            ) from None
        return ActionResult(
            message=f"{params.definition.name} created",
            reload_node_ids=[node_id],
            created_node_id=node.id,
        )


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
    acts_on: ClassVar[ActsOn] = "destination"
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
def drop_refusals(subject: str) -> dict[str, str]:
    """The same three refusals, about whatever is being dropped.

    Written per call rather than as one constant because the subject is a
    relation when one is selected and a count when several are: "something
    else is built on this relation" is the wrong sentence about five of them.
    """
    return {
        # dependent_objects_still_exist.
        "2BP01": f"Something else is built on {subject}",
        # lock_not_available: somebody is reading or writing it right now.
        "55P03": f"Something is using {subject}; try again in a moment",
        # insufficient_privilege.
        "42501": f"This connection may not drop {subject}",
    }


class DropRelationParams(BaseModel):
    cascade: bool = Field(
        default=False,
        title="Also drop everything built on it",
        description="Required when a view or a reference depends on this relation",
    )


# What a relation is dropped by, and the order the commands are issued in.
# A view is dropped before the table it reads, so that selecting both succeeds
# without a cascade; the other order would refuse a set the user meant.
DROP_COMMANDS: tuple[tuple[str, sql.SQL], ...] = (
    ("view", sql.SQL("DROP VIEW")),
    ("materialized view", sql.SQL("DROP MATERIALIZED VIEW")),
    ("table", sql.SQL("DROP TABLE")),
)


class DropRelation(JsonAction[DropRelationParams]):
    """Drop relations, with or without what stands on them.

    Previewable, and that is the point of it: what a cascade takes with it is
    written in `pg_depend`, and the only answer worth showing somebody about to
    destroy something is PostgreSQL's own. So the preview is the drop itself,
    rolled back, and what it lists cannot disagree with what happens.

    A selection is dropped together rather than one relation at a time. Three
    relations that depend on each other are dropped by one transaction and
    refused by three separate requests, in whatever order the client happened
    to send them in — and somebody who ticked all three meant the set.
    """

    name: ClassVar[str] = "drop_relation"
    title: ClassVar[str] = "Drop"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = True
    params_model = DropRelationParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(
        self, node_id: str | None, params: DropRelationParams
    ) -> ActionResult:
        return await self._drop([node_id], params)

    async def perform_on_set(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionResult:
        return await self._drop(list(node_ids), self._validated(raw))

    async def preview(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ActionPreview:
        return await self._rehearse([node_id], self._validated(raw))

    async def preview_on_set(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionPreview:
        return await self._rehearse(list(node_ids), self._validated(raw))

    async def _drop(
        self, node_ids: Sequence[str | None], params: DropRelationParams
    ) -> ActionResult:
        targets = await self._targets(node_ids)
        await self._guard_cascades(targets, cascade=params.cascade)
        statements = self._statements(targets, cascade=params.cascade)
        subject = _subject(targets)
        # One transaction, so a selection that cannot be dropped whole leaves
        # every relation in it standing. Half a drop is not a partial success,
        # it is a schema nobody asked for.
        async with self._session.transaction(
            refusals=drop_refusals(subject)
        ) as change:
            for statement in statements:
                await change.schema_change(statement)
        return ActionResult(
            message=f"{subject} dropped",
            reload_node_ids=[*sorted({schema for schema, _ in targets})],
        )

    async def _rehearse(
        self, node_ids: Sequence[str | None], params: DropRelationParams
    ) -> ActionPreview:
        """What this drop would take with it, as the server itself reports it.

        The same statements the form describes, so ticking the box changes the
        answer: without a cascade a relation something is built on refuses, and
        the refusal names what is in the way; with one, the server lists what
        it would drop as it goes.
        """
        targets = await self._targets(node_ids)
        await self._guard_cascades(targets, cascade=params.cascade)
        subject = _subject(targets)
        rehearsal = await self._session.rehearse(
            *self._statements(targets, cascade=params.cascade),
            refusals=drop_refusals(subject),
        )
        if rehearsal.refused is not None:
            # An answer rather than a failure: the question was "what would
            # happen", and what would happen is that it would be refused.
            return ActionPreview(
                summary=rehearsal.refused, items=rehearsal.said, blocked=True
            )
        if not rehearsal.said:
            return ActionPreview(summary=f"Nothing else depends on {subject}")
        # The lines are the server's own sentences, so the summary leaves room
        # for them to say what they say rather than repeating half of it.
        return ActionPreview(
            summary=f"What dropping {subject} would do:", items=rehearsal.said
        )

    async def _guard_cascades(
        self, targets: Sequence[tuple[str, TableNode | ViewNode]], *, cascade: bool
    ) -> None:
        if not cascade:
            return
        for schema, node in targets:
            reason = await self._catalog.cascade_reason(schema, node.name)
            if reason is not None:
                raise ActionRefused("not_applicable", reason)

    async def _targets(
        self, node_ids: Sequence[str | None]
    ) -> list[tuple[str, TableNode | ViewNode]]:
        if len(set(node_ids)) != len(node_ids):
            raise ActionRefused(
                "not_applicable", "A relation may be dropped only once"
            )
        return [await self._target(node_id) for node_id in node_ids]

    async def _target(self, node_id: str | None) -> tuple[str, TableNode | ViewNode]:
        if node_id is None:
            raise ActionRefused("not_applicable", "Choose a relation to drop")
        path = await self._catalog.path_to(node_id)
        node = path[-1]
        if not isinstance(node, TableNode | ViewNode) or node.is_system:
            raise ActionRefused("not_applicable", "This relation cannot be dropped")
        await _guard_relation_action(self._catalog, path[0].name, node)
        return path[0].name, node

    @staticmethod
    def _statements(
        targets: Sequence[tuple[str, TableNode | ViewNode]], *, cascade: bool
    ) -> list[str]:
        """One statement per kind of relation, naming every target of that kind.

        Composed from the catalog's description rather than from a guess: a
        materialized view is not dropped by DROP VIEW, and PostgreSQL says so
        with an error that names neither. Grouping rather than one statement
        each is what lets a table and the view over it go together: everything
        named in one DROP is already gone when the server checks what depends
        on the rest of it.
        """
        by_kind: dict[str, list[sql.Composable]] = {}
        for schema, node in targets:
            by_kind.setdefault(_kind_of(node), []).append(
                sql.Identifier(schema, node.name)
            )
        statements: list[str] = []
        for kind, command in DROP_COMMANDS:
            named = by_kind.get(kind)
            if not named:
                continue
            statement = sql.SQL("{} {}").format(command, sql.SQL(", ").join(named))
            if cascade:
                statement += sql.SQL(" CASCADE")
            statements.append(statement.as_string())
        return statements


def _kind_of(node: TableNode | ViewNode) -> str:
    if isinstance(node, TableNode):
        return "table"
    return "materialized view" if node.is_materialized else "view"


def _subject(targets: Sequence[tuple[str, TableNode | ViewNode]]) -> str:
    """What a message about this drop is about, named once.

    One relation is called by its name, because that is what the person is
    looking at. Several are counted: five names in a toast is a list nobody
    reads, and the catalog is about to show which ones went.
    """
    if len(targets) == 1:
        return targets[0][1].name
    return f"{len(targets)} relations"


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
    acts_on: ClassVar[ActsOn] = "group"
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
        await self._guard_cascade(node.name, cascade=params.cascade)
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
        await self._guard_cascade(node.name, cascade=params.cascade)
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

    async def _guard_cascade(self, schema: str, *, cascade: bool) -> None:
        if cascade:
            reason = await self._catalog.cascade_reason(schema)
            if reason is not None:
                raise ActionRefused("not_applicable", reason)

    @staticmethod
    def _statement(schema: str, *, cascade: bool) -> str:
        statement = sql.SQL("DROP SCHEMA {}").format(sql.Identifier(schema))
        if cascade:
            statement += sql.SQL(" CASCADE")
        return statement.as_string()


class DescribeModelParams(BaseModel):
    # A screen of its own rather than a form: the answer is a document, and
    # what somebody does with it — read it, copy it, take it to a website —
    # is not a thing a generic form has anywhere to put (D73).
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"x-ui-workflow": "model-as-code"}
    )

    dialect: CodeDialect = Field(
        default="dbml",
        title="Written as",
        description="What the file is for: an ORM, or a diagram",
        # The names are the source's, so the three buttons say what a person
        # recognises rather than the value behind them.
        json_schema_extra={
            "x-ui-choices": [
                {"value": dialect, "label": title}
                for dialect, title in DIALECT_TITLE.items()
            ]
        },
    )


class DescribeModel(Action[DescribeModelParams]):
    """Write the model of what was selected as code, and hand it over.

    A download rather than a view, because what comes out is meant to be
    taken somewhere else: pasted into dbdiagram.io, or dropped into a
    project. The bytes are produced from the model the source already
    publishes (D22), so nothing here reads the catalog a second time.

    Offered on a schema as well as on a relation, and that is the useful
    case: a diagram of one table is a rectangle, while a diagram of a schema
    is the thing people draw.
    """

    name: ClassVar[str] = "describe_model"
    title: ClassVar[str] = "Model as code"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset(
        {"schema", "table", "view"}
    )
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "read"
    bulk: ClassVar[bool] = True
    params_model = DescribeModelParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._relation = PostgresRelation(session)
        self._catalog = catalog

    async def download(
        self, node_ids: Sequence[str], raw: Mapping[str, Any]
    ) -> ActionDownload:
        params = self._validated(raw)
        models = await self._models(node_ids)
        if not models:
            raise ActionRefused(
                "not_applicable", "There is nothing here to describe"
            )
        try:
            text = render(models, params.dialect)
        except ValueError as exc:
            raise ActionRefused("too_large", str(exc)) from None
        body = text.encode("utf-8")
        return ActionDownload(
            metadata=ActionDownloadMetadata(
                filename=_model_filename(node_ids, params.dialect),
                media_type="text/plain; charset=utf-8",
                size_bytes=len(body),
            ),
            body=_one_chunk(body),
        )

    async def _models(self, node_ids: Sequence[str]) -> list[RelationModel]:
        """Every relation the selection names, each described once.

        A schema stands for its contents, which is what makes selecting one
        the way to draw a whole database; a relation stands for itself.
        """
        gathered: dict[str, RelationModel] = {}
        for node_id in node_ids:
            path = await self._catalog.path_to(node_id)
            node = path[-1]
            if isinstance(node, SchemaNode):
                reason = await self._catalog.schema_action_reason(node.name)
                if reason is not None:
                    raise ActionRefused("not_applicable", reason)
                for model in await self._relation.relation_models(node.name):
                    gathered.setdefault(model.node_id, model)
                continue
            if not isinstance(node, TableNode | ViewNode):
                raise ActionRefused(
                    "not_applicable", f"{node.name} has no model to write out"
                )
            await _guard_relation_action(self._catalog, path[0].name, node)
            model = await self._relation.relation_model(node_id)
            gathered.setdefault(model.node_id, model)
        return list(gathered.values())


def _model_filename(node_ids: Sequence[str], dialect: CodeDialect) -> str:
    """What the file is called: after the one thing selected, or "model"."""
    suffix = DIALECT_SUFFIX[dialect]
    if len(node_ids) == 1:
        stem = node_ids[0].replace(".", "_")
        return f"{stem}{suffix}"
    return f"model{suffix}"


async def _one_chunk(body: bytes) -> AsyncIterator[bytes]:
    yield body


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
    CreateTable,
    DropRelation,
    DropSchema,
    CreateRole,
    DescribeModel,
)

# Which report admits which commands. `applies_to` speaks about kinds, and
# every report is a report: one of them is about extensions and another about
# roles, and neither offers the other's commands. A table rather than a chain
# of comparisons, so that a report gaining a command is an entry here.
REPORT_COMMANDS: dict[str, tuple[str, ...]] = {
    ROLES_REPORT_ID: (CreateRole.name,),
}


class PostgresActions:
    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._catalog = catalog
        self._relations = PostgresRelationChanges(session, catalog)
        self._actions = ActionSet(
            [action_type(session, catalog) for action_type in POSTGRES_ACTION_TYPES]
        )

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
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
            if not options.supported:
                return []
            actions = self._actions.for_kind(node.kind)
            reason = await self._catalog.schema_action_reason(node.name)
            if reason is not None:
                member_actions = {RenameSchema.name, DropSchema.name, DescribeModel.name}
                return [action for action in actions if action.name not in member_actions]
            if await self._catalog.cascade_reason(node.name) is not None:
                schema_mutations = {RenameSchema.name, DropSchema.name}
                return [action for action in actions if action.name not in schema_mutations]
            return actions
        if isinstance(node, (TableNode, ViewNode)) and not node.is_system:
            reason = await self._catalog.relation_action_reason(path[0].name, node.name)
            if reason is not None:
                return []
            return self._actions.for_kind(node.kind)
        # A report admits a command when the command is about what it reports,
        # which is a question of state and so is answered here rather than by
        # `applies_to`.
        if isinstance(node, ReportNode):
            return [self._actions.get(name) for name in REPORT_COMMANDS.get(node_id, ())]
        return []
