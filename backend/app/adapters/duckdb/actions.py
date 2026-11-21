"""What a DuckDB source can be asked to do from its catalog (D9, D399).

PostgreSQL's catalog actions where DuckDB has the thing they act on: schemas
are made and dropped but not renamed, and nothing moves between them, since
DuckDB has neither. Its structure changes are transactional (D393), so a drop
is rehearsed — carried out and rolled back — and its preview is what that did.
"""

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any, ClassVar, Protocol

import duckdb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adapters import database_ids as ids
from app.adapters.actions import (
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
from app.adapters.catalog import NodeKind, ReportNode, SchemaNode, TableNode, ViewNode
from app.adapters.csv_load import LoadCsvParams as SharedLoadCsvParams
from app.adapters.csv_load import chosen_rows, read_upload, table_name
from app.adapters.duckdb.catalog import DuckdbCatalog
from app.adapters.duckdb.design import NAME_LIMIT, DuckdbTableDesign
from app.adapters.duckdb.inspection import list_schemas, read_relation
from app.adapters.duckdb.relation import DuckdbRelation
from app.adapters.duckdb.relation_changes import DuckdbRelationChanges
from app.adapters.duckdb.session import DuckdbSession, Reading
from app.adapters.duckdb.sql import SQL, Identifier
from app.adapters.duckdb.structure import rehearse, restructure
from app.adapters.model_code import DIALECT_SUFFIX, DIALECT_TITLE, CodeDialect, render
from app.adapters.relation import RelationModel
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)
from app.adapters.table_design import DesignRefused, TableDefinition
from app.core.access import Access
from app.core.translation import N_, say

# DuckDB keeps `main` whatever is asked (checked on 2.0.0).
_KEPT_SCHEMA = "main"

# Every foreign key of the file: DuckDB keeps one within its schema (D389).
_KEYS = """
SELECT schema_name, table_name, constraint_name, referenced_table
FROM duckdb_constraints()
WHERE database_name = current_database() AND constraint_type = 'FOREIGN KEY'
ORDER BY schema_name, table_name, constraint_index
"""

# Which table takes values from which sequence: the sequence depends on the
# table in DuckDB's record, not the other way round (checked on 2.0.0).
_SEQUENCE_USERS = """
SELECT q.schema_name, q.sequence_name, t.schema_name, t.table_name
FROM duckdb_dependencies() AS d
JOIN duckdb_sequences() AS q ON q.sequence_oid = d.objid
JOIN duckdb_tables() AS t ON t.table_oid = d.refobjid
WHERE q.database_name = current_database() AND t.database_name = current_database()
"""

# What a schema may hold, counted for a preview, in the order it is listed.
_HOLDINGS: tuple[tuple[str, str], ...] = (
    (
        "SELECT count(*) FROM duckdb_tables() WHERE database_name = current_database() "
        "AND schema_name = ? AND NOT internal",
        N_("{count} tables and their rows"),
    ),
    (
        "SELECT count(*) FROM duckdb_views() WHERE database_name = current_database() "
        "AND schema_name = ? AND NOT internal",
        N_("{count} views"),
    ),
    (
        "SELECT count(*) FROM duckdb_sequences() WHERE database_name = current_database() "
        "AND schema_name = ?",
        N_("{count} sequences"),
    ),
    (
        "SELECT count(*) FROM duckdb_types() WHERE database_name = current_database() "
        "AND schema_name = ? AND NOT internal",
        N_("{count} types"),
    ),
    (
        "SELECT count(*) FROM duckdb_functions() WHERE database_name = current_database() "
        "AND schema_name = ? AND NOT internal AND function_type IN ('macro', 'table_macro')",
        N_("{count} macros"),
    ),
)


def _name(value: str) -> str:
    """A name DuckDB keeps as given (D397's rule)."""
    if value == "" or value != value.strip() or len(value) > NAME_LIMIT:
        raise ValueError(
            say(
                "A DuckDB name is 1 to {limit} characters and does not start or end with spaces",
                limit=NAME_LIMIT,
            )
        )
    return value


def _executing(statement: str) -> Callable[[duckdb.DuckDBPyConnection], None]:
    def work(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(statement)

    return work


def _keys(reading: Reading) -> list[tuple[str, str, str, str]]:
    """(schema, table, key, referenced table) for every foreign key."""
    return [
        (str(row[0]), str(row[1]), str(row[2]), str(row[3])) for row in reading.tuples(_KEYS)
    ]


async def _relation_target(
    catalog: DuckdbCatalog, node_id: str | None, refused: str
) -> tuple[str, TableNode | ViewNode]:
    """The schema and node of a relation an action was asked about."""
    if node_id is None:
        raise ActionRefused("not_applicable", say("Choose a relation"))
    path = await catalog.path_to(node_id)
    node = path[-1]
    if not isinstance(node, TableNode | ViewNode) or not isinstance(path[0], SchemaNode):
        raise ActionRefused("not_applicable", refused)
    return path[0].name, node


async def _schema_target(catalog: DuckdbCatalog, node_id: str | None, refused: str) -> SchemaNode:
    if node_id is None:
        raise ActionRefused("not_applicable", say("Choose a schema"))
    node = (await catalog.path_to(node_id))[-1]
    if not isinstance(node, SchemaNode):
        raise ActionRefused("not_applicable", refused)
    return node


class CreateSchemaParams(BaseModel):
    name: str = Field(title=N_("Name"))

    _check = field_validator("name")(_name)


class CreateSchema(JsonAction[CreateSchemaParams]):
    """A schema at the top of the connection, beside the others."""

    name: ClassVar[str] = "create_schema"
    title: ClassVar[str] = N_("New schema")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset()
    acts_on: ClassVar[ActsOn] = "level"
    requires: ClassVar[Access] = "structure"
    params_model = CreateSchemaParams

    def __init__(self, session: DuckdbSession, catalog: DuckdbCatalog) -> None:
        self._session = session

    async def run(self, node_id: str | None, params: CreateSchemaParams) -> ActionResult:
        if node_id is not None:
            raise ActionRefused(
                "not_applicable", say("Schemas are created at the top of the connection")
            )
        schemas = await self._session.inspection(list_schemas)
        # DuckDB compares names without case (checked on 2.0.0).
        if params.name.lower() in {schema.lower() for schema in schemas}:
            raise ActionRefused("conflict", say('Schema "{name}" already exists', name=params.name))
        statement = SQL("CREATE SCHEMA {}").format(Identifier(params.name)).text()
        try:
            await restructure(self._session, _executing(statement))
        except ValueError as refused:
            raise ActionRefused("not_applicable", str(refused)) from None
        return ActionResult(
            message=say("Schema {name} created", name=params.name),
            reload_node_ids=[None, ids.database_id(params.name)],
        )


class DropSchemaParams(BaseModel):
    cascade: bool = Field(
        default=False,
        title=N_("Also drop everything in it"),
        description=N_("Required when the schema still holds anything"),
    )


class DropSchema(JsonAction[DropSchemaParams]):
    """Drop a schema and everything in it, once it was said what that is."""

    name: ClassVar[str] = "drop_schema"
    title: ClassVar[str] = N_("Drop schema")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "group"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    params_model = DropSchemaParams

    def __init__(self, session: DuckdbSession, catalog: DuckdbCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def _target(self, node_id: str | None) -> SchemaNode:
        node = await _schema_target(self._catalog, node_id, say("This schema cannot be dropped"))
        if node.name == _KEPT_SCHEMA:
            raise ActionRefused("not_applicable", say("DuckDB keeps the schema main"))
        return node

    @staticmethod
    def _statement(node: SchemaNode, cascade: bool) -> str:
        return SQL("DROP SCHEMA {}" + (" CASCADE" if cascade else "")).format(Identifier(node.name)).text()

    async def run(self, node_id: str | None, params: DropSchemaParams) -> ActionResult:
        preview = await self._preview(node_id, params)
        if preview.blocked:
            raise ActionRefused("not_applicable", preview.summary)
        node = await self._target(node_id)
        statement = self._statement(node, params.cascade)
        try:
            await restructure(self._session, _executing(statement))
        except ValueError as refused:
            raise ActionRefused("not_applicable", str(refused)) from None
        return ActionResult(
            message=say("Schema {name} dropped", name=node.name),
            reload_node_ids=[None, node.id],
        )

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        return await self._preview(node_id, self._validated(raw))

    async def _preview(self, node_id: str | None, params: DropSchemaParams) -> ActionPreview:
        node = await self._target(node_id)

        def read(reading: Reading) -> list[str]:
            return [
                say(sentence, count=count)
                for statement, sentence in _HOLDINGS
                if (count := int(reading.value(statement, [node.name]) or 0))
            ]

        # A foreign key never reaches into another schema (D389), so nothing
        # outside this one holds it back.
        held = await self._session.inspection(read)
        if not held:
            return ActionPreview(summary=say("Schema {name} is empty", name=node.name))
        if not params.cascade:
            return ActionPreview(summary=say("The schema is not empty"), items=held, blocked=True)
        statement = self._statement(node, cascade=True)
        try:
            broken = await rehearse(self._session, _executing(statement))
        except ValueError as refused:
            return ActionPreview(summary=str(refused), items=held, blocked=True)
        return ActionPreview(
            summary=say("What dropping {name} would do:", name=node.name),
            items=[say("Drop {what}", what=line) for line in held]
            + [say("View {view} will stop working", view=view) for view in broken],
        )


class RenameRelationParams(BaseModel):
    new_name: str = Field(title=N_("New name"), json_schema_extra={"x-ui-purpose": "node-name"})

    _check = field_validator("new_name")(_name)


class RenameRelation(JsonAction[RenameRelationParams]):
    """Rename a table or a view in its schema, every view bound after (D399).

    DuckDB renames without looking at the views that read the old name, so a
    view that stops binding refuses the rename. A table with a foreign key of
    its own is refused before DuckDB is asked: renamed, it leaves the table it
    points at unable to delete a row or be dropped (checked on 2.0.0).
    """

    name: ClassVar[str] = "rename_relation"
    title: ClassVar[str] = N_("Rename")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    params_model = RenameRelationParams

    def __init__(self, session: DuckdbSession, catalog: DuckdbCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: RenameRelationParams) -> ActionResult:
        schema, node = await _relation_target(
            self._catalog, node_id, say("This relation cannot be renamed")
        )
        new_name = params.new_name
        if new_name == node.name:
            raise ActionRefused("conflict", say("The relation already has that name"))
        siblings = await self._catalog.list_children(ids.database_id(schema))
        if new_name.lower() != node.name.lower() and new_name.lower() in {
            sibling.name.lower() for sibling in siblings
        }:
            raise ActionRefused(
                "conflict",
                say('{schema} already has a relation named "{name}"', schema=schema, name=new_name),
            )
        is_table = isinstance(node, TableNode)
        if is_table:
            await self._table_reason(schema, node.name)
        statement = SQL("ALTER TABLE {} RENAME TO {}" if is_table else "ALTER VIEW {} RENAME TO {}").format(
            Identifier(schema, node.name), Identifier(new_name)
        )
        try:
            await restructure(self._session, _executing(statement.text()), views=True)
        except ValueError as refused:
            raise ActionRefused("not_applicable", str(refused)) from None
        return ActionResult(
            message=say("Renamed to {name}", name=new_name),
            reload_node_ids=[ids.database_id(schema)],
            replacement=NodeReplacement(
                old_node_id=node.id, new_node_id=ids.relation_id(schema, new_name), title=new_name
            ),
        )

    async def _table_reason(self, schema: str, table: str) -> None:
        def read(reading: Reading) -> tuple[bool, bool, list[tuple[str, str, str, str]]]:
            facts = read_relation(reading, schema, table)
            if facts is None:
                return False, False, []
            indexed = any(not index.primary for index in facts.indexes)
            return bool(facts.foreign_keys), indexed, _keys(reading)

        own_key, indexed, keys = await self._session.inspection(read)
        if own_key:
            raise ActionRefused(
                "not_applicable",
                say(
                    "A table with a foreign key is not renamed: DuckDB would leave the table "
                    "it refers to unable to delete its rows or be dropped"
                ),
            )
        arriving = [
            f"{source}" for source_schema, source, _, target in keys
            if source_schema == schema and target == table and source != table
        ]
        if indexed or arriving:
            raise ActionRefused(
                "not_applicable",
                say(
                    "DuckDB cannot rename a table while an index of it, or another table's "
                    "foreign key to it, depends on it"
                ),
            )


class DropRelationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DropRelation(JsonAction[DropRelationParams]):
    """Drop relations together, after a rehearsal said what that does (D399).

    Views go first, then tables, one pointing at another of the selection
    before the table it points at. A key from outside the selection refuses
    the drop; a view outside it that reads a dropped relation is named, since
    DuckDB does not track what a view reads.
    """

    name: ClassVar[str] = "drop_relation"
    title: ClassVar[str] = N_("Drop")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = True
    params_model = DropRelationParams

    def __init__(self, session: DuckdbSession, catalog: DuckdbCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: DropRelationParams) -> ActionResult:
        return await self._drop([node_id])

    async def perform_on_set(self, node_ids: Sequence[str], raw: Mapping[str, Any]) -> ActionResult:
        self._validated(raw)
        return await self._drop(list(node_ids))

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        self._validated(raw)
        return await self._preview(await self._targets([node_id]))

    async def preview_on_set(self, node_ids: Sequence[str], raw: Mapping[str, Any]) -> ActionPreview:
        self._validated(raw)
        return await self._preview(await self._targets(list(node_ids)))

    async def _targets(self, node_ids: Sequence[str | None]) -> list[tuple[str, TableNode | ViewNode]]:
        if len(set(node_ids)) != len(node_ids):
            raise ActionRefused("not_applicable", say("A relation may be dropped only once"))
        return [
            await _relation_target(self._catalog, node_id, say("This relation cannot be dropped"))
            for node_id in node_ids
        ]

    @staticmethod
    def _carry_out(
        connection: duckdb.DuckDBPyConnection, targets: Sequence[tuple[str, TableNode | ViewNode]]
    ) -> None:
        views = [(schema, node.name) for schema, node in targets if isinstance(node, ViewNode)]
        tables = _children_first(
            _keys(Reading(connection)),
            [(schema, node.name) for schema, node in targets if isinstance(node, TableNode)],
        )
        # Read before the tables go: their dependencies go with them.
        sequences = _sequences_of(Reading(connection), set(tables))
        for view in views:
            connection.execute(SQL("DROP VIEW {}").format(Identifier(*view)).text())
        for table in tables:
            connection.execute(SQL("DROP TABLE {}").format(Identifier(*table)).text())
        for sequence in sequences:
            connection.execute(SQL("DROP SEQUENCE {}").format(Identifier(*sequence)).text())

    async def _drop(self, node_ids: Sequence[str | None]) -> ActionResult:
        targets = await self._targets(node_ids)
        blocking = await self._session.inspection(lambda reading: _arriving(_keys(reading), targets))
        if blocking:
            raise ActionRefused("not_applicable", blocking[0])
        try:
            await restructure(self._session, lambda connection: self._carry_out(connection, targets))
        except ValueError as refused:
            raise ActionRefused("not_applicable", str(refused)) from None
        name = _one_name(targets)
        return ActionResult(
            message=(
                say("{name} dropped", name=name)
                if name is not None
                else say("{count} relations dropped", count=len(targets))
            ),
            reload_node_ids=[*sorted({ids.database_id(schema) for schema, _ in targets})],
        )

    async def _preview(self, targets: Sequence[tuple[str, TableNode | ViewNode]]) -> ActionPreview:
        name = _one_name(targets)
        blocking = await self._session.inspection(lambda reading: _arriving(_keys(reading), targets))
        if blocking:
            return ActionPreview(
                summary=(
                    say("Other tables refer to {name}", name=name)
                    if name is not None
                    else say("Other tables refer to {count} relations", count=len(targets))
                ),
                items=blocking,
                blocked=True,
            )
        chosen = {(schema, node.name) for schema, node in targets if isinstance(node, TableNode)}
        sequences = await self._session.inspection(lambda reading: _sequences_of(reading, chosen))
        try:
            broken = await rehearse(self._session, lambda connection: self._carry_out(connection, targets))
        except ValueError as refused:
            return ActionPreview(summary=str(refused), blocked=True)
        items = [
            say("Sequence {name} goes with it: only what is dropped takes values from it", name=sequence)
            for _, sequence in sequences
        ] + [say("View {view} will stop working", view=view) for view in broken]
        if not items:
            return ActionPreview(
                summary=(
                    say("Nothing else depends on {name}", name=name)
                    if name is not None
                    else say("Nothing else depends on {count} relations", count=len(targets))
                )
            )
        return ActionPreview(
            summary=(
                say("What dropping {name} would do:", name=name)
                if name is not None
                else say("What dropping {count} relations would do:", count=len(targets))
            ),
            items=items,
        )


def _sequences_of(reading: Reading, tables: set[tuple[str, str]]) -> list[tuple[str, str]]:
    """The sequences only these tables take values from, as the designer's
    identity is (D397): they go with the tables rather than linger."""
    users: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for row in reading.tuples(_SEQUENCE_USERS):
        users.setdefault((str(row[0]), str(row[1])), set()).add((str(row[2]), str(row[3])))
    return sorted(sequence for sequence, used_by in users.items() if used_by <= tables)


def _arriving(
    keys: list[tuple[str, str, str, str]], targets: Sequence[tuple[str, TableNode | ViewNode]]
) -> list[str]:
    """Keys from tables left standing to tables of the selection."""
    chosen = {(schema, node.name) for schema, node in targets if isinstance(node, TableNode)}
    return [
        say("{table} refers to {target} through {key}", table=table, target=target, key=key)
        for schema, table, key, target in keys
        if (schema, target) in chosen and (schema, table) not in chosen
    ]


def _children_first(
    keys: list[tuple[str, str, str, str]], tables: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """The tables in an order where one pointing at another of them goes first.

    DuckDB refuses to drop a table another one's key points at; dropped
    earlier in the same transaction, the pointing table no longer counts
    (checked on 2.0.0).
    """
    chosen = set(tables)
    points_at: dict[tuple[str, str], set[tuple[str, str]]] = {table: set() for table in tables}
    for schema, table, _, target in keys:
        source, aim = (schema, table), (schema, target)
        if source in chosen and aim in chosen and source != aim:
            points_at[source].add(aim)
    ordered: list[tuple[str, str]] = []
    while points_at:
        # A table no remaining one points at can go last; a cycle goes as it is.
        pointed = {aim for aims in points_at.values() for aim in aims}
        ready = [one for one in points_at if one not in pointed] or list(points_at)
        for one in sorted(ready):
            ordered.append(one)
            points_at.pop(one)
    return ordered


def _one_name(targets: Sequence[tuple[str, TableNode | ViewNode]]) -> str | None:
    """One relation is called by its name; several are counted."""
    return targets[0][1].name if len(targets) == 1 else None


class LoadCsvParams(SharedLoadCsvParams):
    @field_validator("name")
    @classmethod
    def named_or_empty(cls, value: str) -> str:
        return value if value == "" else _name(value)


class LoadCsv(FileAction[LoadCsvParams]):
    """A delimited file, uploaded, becomes a table of a schema.

    Every column is VARCHAR: a file states no types, and one read off its rows
    would depend on how many were looked at.
    """

    name: ClassVar[str] = "load_csv"
    title: ClassVar[str] = N_("Load from CSV")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = False
    params_model = LoadCsvParams

    def __init__(self, session: DuckdbSession, catalog: DuckdbCatalog) -> None:
        self._catalog = catalog
        self._relations = DuckdbRelationChanges(session, catalog)

    async def run(self, node_id: str | None, params: LoadCsvParams, payload: FilePayload) -> ActionResult:
        schema = await _schema_target(self._catalog, node_id, say("Choose a schema to load into"))
        if params.create_schema or params.schema_name not in ("", schema.name):
            raise ActionRefused("not_applicable", say("A file is loaded into the schema it was asked of"))
        name = table_name(params, payload, _name)
        siblings = await self._catalog.list_children(schema.id)
        if name.lower() in {sibling.name.lower() for sibling in siblings}:
            raise ActionRefused("conflict", say("{name} is already there", name=name))
        targets, rows = chosen_rows(await read_upload(payload), params, _name)
        try:
            result = await self._relations.create_relation(
                CreateRelationRequest(
                    parent_node_id=schema.id,
                    name=name,
                    columns=[NewColumn(name=target, type_code="text") for target in targets],
                    rows=rows,
                )
            )
        except ValueError as refused:
            raise ActionRefused("not_applicable", str(refused)) from None
        if not isinstance(result, RelationCreated):
            # DuckDB refuses a whole table for one value (D397); no cells come back.
            raise ActionRefused("not_applicable", say("A value of the file cannot be read"))
        return ActionResult(
            message=say("{name} created with {count} rows", name=name, count=result.inserted),
            reload_node_ids=[schema.id],
            created_node_id=result.node.id,
        )


class CreateTableParams(BaseModel):
    # The designer is registered against this workflow, as PostgreSQL's is.
    model_config = ConfigDict(extra="forbid", json_schema_extra={"x-ui-workflow": "table-designer"})

    definition: TableDefinition
    fingerprint: str = Field(min_length=1, max_length=64)


class CreateTable(JsonAction[CreateTableParams]):
    """Design a table, review its statements, then create it (D117, D397)."""

    name: ClassVar[str] = "create_table"
    title: ClassVar[str] = N_("Create table")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = False
    params_model = CreateTableParams

    def __init__(self, session: DuckdbSession, catalog: DuckdbCatalog) -> None:
        self._design = DuckdbTableDesign(session, catalog, DuckdbRelation(session))

    async def run(self, node_id: str | None, params: CreateTableParams) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a schema to create it in"))
        try:
            node = await self._design.create_table(node_id, params.definition, params.fingerprint)
        except DesignRefused as refused:
            raise ActionRefused(
                "conflict" if refused.problem.kind == "conflict" else "not_applicable",
                refused.problem.message,
            ) from None
        return ActionResult(
            message=say("{name} created", name=params.definition.name),
            reload_node_ids=[node_id],
            created_node_id=node.id,
        )


class DescribeModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"x-ui-workflow": "model-as-code"})

    dialect: CodeDialect = Field(
        default="dbml",
        title=N_("Written as"),
        description=N_("What the file is for: an ORM, or a diagram"),
        json_schema_extra={
            "x-ui-choices": [{"value": dialect, "label": title} for dialect, title in DIALECT_TITLE.items()]
        },
    )


class DescribeModel(Action[DescribeModelParams]):
    """The model of what was selected, written as code and handed over (D73).

    A schema stands for its tables and views, which is what makes selecting
    it the way to draw it.
    """

    name: ClassVar[str] = "describe_model"
    title: ClassVar[str] = N_("Model as code")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema", "table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "read"
    bulk: ClassVar[bool] = True
    params_model = DescribeModelParams

    def __init__(self, session: DuckdbSession, catalog: DuckdbCatalog) -> None:
        self._relation = DuckdbRelation(session)
        self._catalog = catalog

    async def download(self, node_ids: Sequence[str], raw: Mapping[str, Any]) -> ActionDownload:
        params = self._validated(raw)
        models = await self._models(node_ids)
        if not models:
            raise ActionRefused("not_applicable", say("There is nothing here to describe"))
        try:
            text = render(models, params.dialect)
        except ValueError as exc:
            raise ActionRefused("too_large", str(exc)) from None
        body = text.encode("utf-8")
        stem = (ids.parse(node_ids[0])[1] or ids.parse(node_ids[0])[0]) if len(node_ids) == 1 else "model"
        return ActionDownload(
            metadata=ActionDownloadMetadata(
                filename=f"{stem}{DIALECT_SUFFIX[params.dialect]}",
                media_type="text/plain; charset=utf-8",
                size_bytes=len(body),
            ),
            body=_one_chunk(body),
        )

    async def _models(self, node_ids: Sequence[str]) -> list[RelationModel]:
        gathered: dict[str, RelationModel] = {}
        for node_id in node_ids:
            node = (await self._catalog.path_to(node_id))[-1]
            if isinstance(node, SchemaNode):
                relations = [
                    child.id
                    for child in await self._catalog.list_children(node_id)
                    if isinstance(child, TableNode | ViewNode)
                ]
            elif isinstance(node, TableNode | ViewNode):
                relations = [node.id]
            else:
                raise ActionRefused("not_applicable", say("{name} has no model to write out", name=node.name))
            for relation_id in relations:
                if relation_id not in gathered:
                    gathered[relation_id] = await self._relation.relation_model(relation_id)
        return list(gathered.values())


async def _one_chunk(body: bytes) -> AsyncIterator[bytes]:
    yield body


class DuckdbActionType(ActionType, Protocol):
    def __call__(self, session: DuckdbSession, catalog: DuckdbCatalog) -> Action[Any]: ...


DUCKDB_ACTION_TYPES: tuple[DuckdbActionType, ...] = (
    CreateSchema,
    RenameRelation,
    LoadCsv,
    CreateTable,
    DropRelation,
    DropSchema,
    DescribeModel,
)


class DuckdbActions:
    def __init__(self, session: DuckdbSession, catalog: DuckdbCatalog) -> None:
        self._catalog = catalog
        self._actions = ActionSet([action_type(session, catalog) for action_type in DUCKDB_ACTION_TYPES])

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        if node_id is None:
            return [self._actions.get(CreateSchema.name)]
        node = (await self._catalog.path_to(node_id))[-1]
        # A report changes nothing.
        if isinstance(node, ReportNode):
            return []
        actions = self._actions.for_kind(node.kind)
        if isinstance(node, SchemaNode) and node.name == _KEPT_SCHEMA:
            return [action for action in actions if action.name != DropSchema.name]
        return actions
