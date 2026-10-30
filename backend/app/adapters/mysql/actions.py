"""What a MySQL source can be asked to do from its catalog (D9, D238).

MySQL commits every structure statement by itself (D233), so nothing here is
rehearsed: a preview reads `information_schema` for what a change would meet,
and the change refuses what the preview would have shown blocked. A database
cannot be renamed: MySQL has no statement for it, and moving every table out
leaves its views, routines, triggers and events behind.
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
from app.adapters.model_code import DIALECT_SUFFIX, DIALECT_TITLE, CodeDialect, render
from app.adapters.mysql import ids
from app.adapters.mysql.catalog import MysqlCatalog, is_system_database
from app.adapters.mysql.design import MysqlTableDesign
from app.adapters.mysql.relation import MysqlRelation
from app.adapters.mysql.relation_changes import MysqlRelationChanges
from app.adapters.mysql.session import MysqlSession
from app.adapters.mysql.sql import SQL, Composable, Identifier
from app.adapters.mysql.users import USERS_REPORT_ID, CreateUser
from app.adapters.relation import RelationModel
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)
from app.adapters.table_design import DesignRefused, TableDefinition
from app.core.access import Access
from app.core.translation import N_, say

NAME_LIMIT = 64

DATABASE_REFUSALS: dict[int, str] = {
    1007: N_("A database of that name is already there"),
    1044: N_("This connection may not change databases"),
    1102: N_("MySQL does not accept that database name"),
}

RELATION_REFUSALS: dict[int, str] = {
    1050: N_("Something with that name is already there"),
    1142: N_("This connection may not change that relation"),
    1435: N_("A table with triggers cannot leave its database"),
    1450: N_("A view cannot leave its database"),
    # What the preview names first; this is what the server says if a key
    # arrived in between.
    1451: N_("Another table refers to it through a foreign key"),
    3730: N_("Another table refers to it through a foreign key"),
}


def _name(value: str) -> str:
    """A database or relation name MySQL will keep as given."""
    if value == "" or value != value.strip() or len(value) > NAME_LIMIT:
        raise ValueError(
            say(
                "A MySQL name is 1 to {limit} characters and does not start or end with spaces",
                limit=NAME_LIMIT,
            )
        )
    return value


async def _database_exists(session: MysqlSession, name: str) -> bool:
    rows = await session.query(
        "SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s", (name,)
    )
    return bool(rows)


async def create_database(session: MysqlSession, name: str) -> None:
    _name(name)
    if is_system_database(name):
        raise ActionRefused("not_applicable", say("That database name belongs to the server"))
    if await _database_exists(session, name):
        raise ActionRefused("conflict", say('Database "{name}" already exists', name=name))
    await _alter(session, SQL("CREATE DATABASE {}").format(Identifier(name)), refusals=DATABASE_REFUSALS)


async def _alter(
    session: MysqlSession, *statements: Composable, refusals: Mapping[int, str], unchecked: bool = False
) -> None:
    """Run structure statements on one connection; a refusal is the action's.

    `unchecked` drops foreign key checks for these statements alone, for a
    set whose keys point only at each other: MariaDB refuses to drop a table
    a later one in the same statement refers to, and drops the ones before it.
    """
    try:
        async with session.altering(refusals=refusals) as work:
            if not unchecked:
                for statement in statements:
                    await work.execute(statement.text())
                return
            await work.execute("SET @dp_checks = @@SESSION.foreign_key_checks", ())
            await work.execute("SET SESSION foreign_key_checks = 0", ())
            try:
                for statement in statements:
                    await work.execute(statement.text())
            finally:
                await work.execute("SET SESSION foreign_key_checks = @dp_checks", ())
    except ValueError as refused:
        raise ActionRefused("not_applicable", str(refused)) from None


async def _database_target(catalog: MysqlCatalog, node_id: str | None, refused: str) -> SchemaNode:
    if node_id is None:
        raise ActionRefused("not_applicable", say("Choose a database"))
    node = (await catalog.path_to(node_id))[-1]
    if not isinstance(node, SchemaNode) or node.is_system:
        raise ActionRefused("not_applicable", refused)
    return node


async def _relation_target(
    catalog: MysqlCatalog, node_id: str | None, refused: str
) -> tuple[str, TableNode | ViewNode]:
    if node_id is None:
        raise ActionRefused("not_applicable", say("Choose a relation"))
    path = await catalog.path_to(node_id)
    node = path[-1]
    if not isinstance(node, TableNode | ViewNode) or node.is_system:
        raise ActionRefused("not_applicable", refused)
    return path[0].name, node


async def _arriving_keys(
    session: MysqlSession, targets: Sequence[tuple[str, str]], *, database: str | None = None
) -> list[str]:
    """The foreign keys of other tables that point into what is going.

    Either the relations named, or a whole database. MySQL refuses a drop they
    stand in the way of, and MariaDB has already dropped part of a set by then.
    """
    if database is not None:
        condition = "UNIQUE_CONSTRAINT_SCHEMA = %s AND CONSTRAINT_SCHEMA <> %s"
        params: tuple[object, ...] = (database, database)
    else:
        if not targets:
            return []
        pair = "(UNIQUE_CONSTRAINT_SCHEMA = %s AND REFERENCED_TABLE_NAME = %s)"
        source = "(CONSTRAINT_SCHEMA = %s AND TABLE_NAME = %s)"
        condition = (
            f"({' OR '.join([pair] * len(targets))}) AND NOT ({' OR '.join([source] * len(targets))})"
        )
        flat = tuple(value for target in targets for value in target)
        params = flat + flat
    # The condition is written above and every name in it is bound.
    statement = f"""
        SELECT CONSTRAINT_SCHEMA AS from_schema, TABLE_NAME AS from_table,
               CONSTRAINT_NAME AS name, UNIQUE_CONSTRAINT_SCHEMA AS to_schema,
               REFERENCED_TABLE_NAME AS to_table
        FROM information_schema.REFERENTIAL_CONSTRAINTS
        WHERE {condition} ORDER BY from_schema, from_table, name
    """  # noqa: S608
    rows = await session.query(statement, params)
    return [
        say(
            "{table} refers to {target} through {key}",
            table=f"{row['from_schema']}.{row['from_table']}",
            target=f"{row['to_schema']}.{row['to_table']}",
            key=row["name"],
        )
        for row in rows
    ]


class CreateDatabaseParams(BaseModel):
    name: str = Field(title=N_("Name"))

    _check = field_validator("name")(_name)


class CreateDatabase(JsonAction[CreateDatabaseParams]):
    """A database at the top of the connection, beside the others (D229)."""

    name: ClassVar[str] = "create_database"
    title: ClassVar[str] = N_("New database")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset()
    acts_on: ClassVar[ActsOn] = "level"
    requires: ClassVar[Access] = "structure"
    params_model = CreateDatabaseParams

    def __init__(self, session: MysqlSession, catalog: MysqlCatalog) -> None:
        self._session = session

    async def run(self, node_id: str | None, params: CreateDatabaseParams) -> ActionResult:
        if node_id is not None:
            raise ActionRefused(
                "not_applicable", say("Databases are created at the top of the connection")
            )
        await create_database(self._session, params.name)
        return ActionResult(
            message=say("Database {name} created", name=params.name),
            reload_node_ids=[None, ids.database_id(params.name)],
        )


class DropDatabaseParams(BaseModel):
    cascade: bool = Field(
        default=False,
        title=N_("Also drop everything in it"),
        description=N_("Required when the database still holds anything"),
    )


# What a database may hold, counted for a preview, in the order it is listed.
_HOLDINGS: tuple[tuple[str, str], ...] = (
    (
        "SELECT COUNT(*) AS found FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE <> 'VIEW'",
        N_("{count} tables and their rows"),
    ),
    (
        "SELECT COUNT(*) AS found FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'VIEW'",
        N_("{count} views"),
    ),
    (
        "SELECT COUNT(*) AS found FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA = %s",
        N_("{count} functions and procedures"),
    ),
    (
        "SELECT COUNT(*) AS found FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = %s",
        N_("{count} triggers"),
    ),
    (
        "SELECT COUNT(*) AS found FROM information_schema.EVENTS WHERE EVENT_SCHEMA = %s",
        N_("{count} events"),
    ),
)


class DropDatabase(JsonAction[DropDatabaseParams]):
    """Drop a database and everything in it, once it was said what that is."""

    name: ClassVar[str] = "drop_database"
    title: ClassVar[str] = N_("Drop database")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "group"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    params_model = DropDatabaseParams

    def __init__(self, session: MysqlSession, catalog: MysqlCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: DropDatabaseParams) -> ActionResult:
        preview = await self._preview(node_id, params)
        if preview.blocked:
            raise ActionRefused("not_applicable", preview.summary)
        node = await self._target(node_id)
        await _alter(
            self._session, SQL("DROP DATABASE {}").format(Identifier(node.name)), refusals=DATABASE_REFUSALS
        )
        return ActionResult(
            message=say("Database {name} dropped", name=node.name),
            reload_node_ids=[None, node.id],
        )

    async def preview(self, node_id: str | None, raw: Mapping[str, Any]) -> ActionPreview:
        return await self._preview(node_id, self._validated(raw))

    async def _target(self, node_id: str | None) -> SchemaNode:
        return await _database_target(self._catalog, node_id, say("This database cannot be dropped"))

    async def _preview(self, node_id: str | None, params: DropDatabaseParams) -> ActionPreview:
        node = await self._target(node_id)
        arriving = await _arriving_keys(self._session, [], database=node.name)
        if arriving:
            return ActionPreview(
                summary=say("Tables in other databases refer to {name}", name=node.name),
                items=arriving,
                blocked=True,
            )
        held: list[str] = []
        for statement, sentence in _HOLDINGS:
            count = int((await self._session.query(statement, (node.name,)))[0]["found"])
            if count:
                held.append(say(sentence, count=count))
        if not held:
            return ActionPreview(summary=say("Database {name} is empty", name=node.name))
        if not params.cascade:
            return ActionPreview(
                summary=say("The database is not empty"), items=held, blocked=True
            )
        return ActionPreview(
            summary=say("What dropping {name} would do:", name=node.name),
            items=[say("Drop {what}", what=line) for line in held],
        )


class RenameRelationParams(BaseModel):
    new_name: str = Field(title=N_("New name"), json_schema_extra={"x-ui-purpose": "node-name"})

    _check = field_validator("new_name")(_name)


class RenameRelation(JsonAction[RenameRelationParams]):
    name: ClassVar[str] = "rename_relation"
    title: ClassVar[str] = N_("Rename")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    params_model = RenameRelationParams

    def __init__(self, session: MysqlSession, catalog: MysqlCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: RenameRelationParams) -> ActionResult:
        schema, node = await _relation_target(
            self._catalog, node_id, say("This relation cannot be renamed")
        )
        if params.new_name == node.name:
            raise ActionRefused("conflict", say("The relation already has that name"))
        siblings = await self._catalog.list_children(ids.database_id(schema))
        if params.new_name in {sibling.name for sibling in siblings}:
            raise ActionRefused(
                "conflict",
                say('{schema} already has a relation named "{name}"', schema=schema, name=params.new_name),
            )
        # RENAME TABLE takes a view as well, and carries the foreign keys
        # that point at a table along with it.
        await _alter(
            self._session,
            SQL("RENAME TABLE {} TO {}").format(
                Identifier(schema, node.name), Identifier(schema, params.new_name)
            ),
            refusals=RELATION_REFUSALS,
        )
        return ActionResult(
            message=say("Renamed to {name}", name=params.new_name),
            reload_node_ids=[ids.database_id(schema)],
            replacement=NodeReplacement(
                old_node_id=node.id,
                new_node_id=ids.relation_id(schema, params.new_name),
                title=params.new_name,
            ),
        )


class MoveRelationParams(BaseModel):
    # One of the source's own database ids, which the form lists.
    target_schema: str = Field(
        title=N_("Target database"), json_schema_extra={"x-ui-purpose": "grouping"}
    )


class MoveRelation(JsonAction[MoveRelationParams]):
    """Move a table to another database; a view cannot leave its own."""

    name: ClassVar[str] = "move_relation"
    title: ClassVar[str] = N_("Move to database")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    bulk: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    params_model = MoveRelationParams

    def __init__(self, session: MysqlSession, catalog: MysqlCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: MoveRelationParams) -> ActionResult:
        schema, node = await _relation_target(self._catalog, node_id, say("This relation cannot be moved"))
        if not isinstance(node, TableNode):
            raise ActionRefused("not_applicable", say("A view cannot leave its database"))
        target_schema, relation = ids.parse(params.target_schema)
        if relation is not None or not await _database_exists(self._session, target_schema):
            raise ActionRefused(
                "not_applicable", say('Database "{name}" does not exist', name=target_schema)
            )
        if is_system_database(target_schema):
            raise ActionRefused(
                "not_applicable", say("Relations cannot be moved into the server's own databases")
            )
        if target_schema == schema:
            raise ActionRefused("conflict", say("The relation is already in {schema}", schema=schema))
        triggers = await self._session.query(
            "SELECT 1 FROM information_schema.TRIGGERS "
            "WHERE EVENT_OBJECT_SCHEMA = %s AND EVENT_OBJECT_TABLE = %s LIMIT 1",
            (schema, node.name),
        )
        if triggers:
            raise ActionRefused("not_applicable", say("A table with triggers cannot leave its database"))
        siblings = await self._catalog.list_children(ids.database_id(target_schema))
        if node.name in {sibling.name for sibling in siblings}:
            raise ActionRefused(
                "conflict",
                say('{schema} already has a relation named "{name}"', schema=target_schema, name=node.name),
            )
        await _alter(
            self._session,
            SQL("RENAME TABLE {} TO {}").format(
                Identifier(schema, node.name), Identifier(target_schema, node.name)
            ),
            refusals=RELATION_REFUSALS,
        )
        return ActionResult(
            message=say("{name} moved to {schema}", name=node.name, schema=target_schema),
            reload_node_ids=[ids.database_id(schema), ids.database_id(target_schema)],
            replacement=NodeReplacement(
                old_node_id=node.id,
                new_node_id=ids.relation_id(target_schema, node.name),
                title=node.name,
            ),
        )


class DropRelationParams(BaseModel):
    # MySQL has no cascade: what refers to a table is named and stops the drop.
    model_config = ConfigDict(extra="forbid")


class DropRelation(JsonAction[DropRelationParams]):
    """Drop relations together, once what refers to them was named.

    A selection is one request: a table and the tables whose keys point only
    at it go together, which separate requests would refuse in whatever order
    they arrived.
    """

    name: ClassVar[str] = "drop_relation"
    title: ClassVar[str] = N_("Drop")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = True
    params_model = DropRelationParams

    def __init__(self, session: MysqlSession, catalog: MysqlCatalog) -> None:
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

    async def _drop(self, node_ids: Sequence[str | None]) -> ActionResult:
        targets = await self._targets(node_ids)
        arriving = await _arriving_keys(
            self._session, [(schema, node.name) for schema, node in targets]
        )
        if arriving:
            raise ActionRefused("not_applicable", arriving[0])
        views = [Identifier(schema, node.name) for schema, node in targets if isinstance(node, ViewNode)]
        tables = [Identifier(schema, node.name) for schema, node in targets if isinstance(node, TableNode)]
        statements: list[Composable] = []
        if views:
            statements.append(SQL("DROP VIEW {}").format(SQL(", ").join(views)))
        if tables:
            statements.append(SQL("DROP TABLE {}").format(SQL(", ").join(tables)))
        # Nothing outside the set refers to it, as was just read, so the keys
        # inside it are all that the checks would stop on.
        await _alter(self._session, *statements, refusals=RELATION_REFUSALS, unchecked=True)
        name = _one_name(targets)
        return ActionResult(
            message=(
                say("{name} dropped", name=name)
                if name is not None
                else say("{count} relations dropped", count=len(targets))
            ),
            reload_node_ids=[*sorted({ids.database_id(schema) for schema, _ in targets})],
        )

    async def _targets(self, node_ids: Sequence[str | None]) -> list[tuple[str, TableNode | ViewNode]]:
        if len(set(node_ids)) != len(node_ids):
            raise ActionRefused("not_applicable", say("A relation may be dropped only once"))
        return [
            await _relation_target(self._catalog, node_id, say("This relation cannot be dropped"))
            for node_id in node_ids
        ]

    async def _preview(self, targets: Sequence[tuple[str, TableNode | ViewNode]]) -> ActionPreview:
        names = [(schema, node.name) for schema, node in targets]
        name = _one_name(targets)
        arriving = await _arriving_keys(self._session, names)
        if arriving:
            return ActionPreview(
                summary=(
                    say("Other tables refer to {name}", name=name)
                    if name is not None
                    else say("Other tables refer to {count} relations", count=len(targets))
                ),
                items=arriving,
                blocked=True,
            )
        items = await self._triggers(names) + await self._readers(names)
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

    async def _triggers(self, names: Sequence[tuple[str, str]]) -> list[str]:
        found: list[str] = []
        for schema, table in names:
            rows = await self._session.query(
                "SELECT TRIGGER_NAME AS name FROM information_schema.TRIGGERS "
                "WHERE EVENT_OBJECT_SCHEMA = %s AND EVENT_OBJECT_TABLE = %s ORDER BY name",
                (schema, table),
            )
            found += [say("Trigger {name} goes with it", name=row["name"]) for row in rows]
        return found

    async def _readers(self, names: Sequence[tuple[str, str]]) -> list[str]:
        """Views outside the set that read from it, and will stop working.

        MySQL keeps which tables a view reads; MariaDB keeps no such list,
        and a guess from the text of its views would name the wrong ones.
        """
        if (await self._session.profile()).mariadb:
            return []
        dropped = set(names)
        found: list[str] = []
        for schema, table in names:
            rows = await self._session.query(
                "SELECT VIEW_SCHEMA AS view_schema, VIEW_NAME AS view_name "
                "FROM information_schema.VIEW_TABLE_USAGE "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY view_schema, view_name",
                (schema, table),
            )
            found += [
                say(
                    "View {view} reads {name} and will stop working",
                    view=f"{row['view_schema']}.{row['view_name']}",
                    name=table,
                )
                for row in rows
                if (row["view_schema"], row["view_name"]) not in dropped
            ]
        return found


def _one_name(targets: Sequence[tuple[str, TableNode | ViewNode]]) -> str | None:
    """One relation is called by its name; several are counted."""
    return targets[0][1].name if len(targets) == 1 else None


class LoadCsvParams(SharedLoadCsvParams):
    @field_validator("name")
    @classmethod
    def named_or_empty(cls, value: str) -> str:
        return value if value == "" else _name(value)


class LoadCsv(FileAction[LoadCsvParams]):
    """A delimited file, uploaded, becomes a table of the database being read.

    Every column is TEXT: a file states no types, and one read off its rows
    would depend on how many were looked at. VARCHAR(255) would refuse the
    first long cell.
    """

    name: ClassVar[str] = "load_csv"
    title: ClassVar[str] = N_("Load from CSV")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = False
    params_model = LoadCsvParams

    def __init__(self, session: MysqlSession, catalog: MysqlCatalog) -> None:
        self._session = session
        self._catalog = catalog
        self._relations = MysqlRelationChanges(session, catalog)

    async def run(self, node_id: str | None, params: LoadCsvParams, payload: FilePayload) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a database to load into"))
        if params.create_schema:
            await create_database(self._session, params.schema_name)
            database = ids.database_id(params.schema_name)
        else:
            database = params.schema_name or node_id
            databases = await self._catalog.list_children(None)
            if database not in {
                node.id for node in databases if isinstance(node, SchemaNode) and not node.is_system
            }:
                raise ActionRefused(
                    "not_applicable",
                    say('Database "{name}" does not exist', name=ids.parse(database)[0]),
                )
        name = table_name(params, payload, _name)
        siblings = await self._catalog.list_children(database)
        if name in {sibling.name for sibling in siblings}:
            raise ActionRefused("conflict", say("{name} is already there", name=name))
        targets, rows = chosen_rows(await read_upload(payload), params, _name)
        try:
            result = await self._relations.create_relation(
                CreateRelationRequest(
                    parent_node_id=database,
                    name=name,
                    columns=[NewColumn(name=target, type_code="long_text") for target in targets],
                    rows=rows,
                )
            )
        except ValueError as refused:
            raise ActionRefused("not_applicable", str(refused)) from None
        if not isinstance(result, RelationCreated):
            cell = result.cells[0]
            raise ActionRefused(
                "not_applicable",
                say(
                    "Row {row}, column {column}: that value cannot be read",
                    row=cell.row + 1,
                    column=cell.column,
                ),
            )
        return ActionResult(
            message=say("{name} created with {count} rows", name=name, count=result.inserted),
            reload_node_ids=[None, database] if params.create_schema else [database],
            created_node_id=result.node.id,
        )


class CreateTableParams(BaseModel):
    # The designer is registered against this workflow, as PostgreSQL's is.
    model_config = ConfigDict(extra="forbid", json_schema_extra={"x-ui-workflow": "table-designer"})

    definition: TableDefinition
    fingerprint: str = Field(min_length=1, max_length=64)


class CreateTable(JsonAction[CreateTableParams]):
    """Design a table, review its statement, then create it (D117, D236)."""

    name: ClassVar[str] = "create_table"
    title: ClassVar[str] = N_("Create table")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = False
    params_model = CreateTableParams

    def __init__(self, session: MysqlSession, catalog: MysqlCatalog) -> None:
        self._design = MysqlTableDesign(session, catalog, MysqlRelation(session))

    async def run(self, node_id: str | None, params: CreateTableParams) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a database to create it in"))
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

    A database stands for its tables and views, which is what makes selecting
    one the way to draw it.
    """

    name: ClassVar[str] = "describe_model"
    title: ClassVar[str] = N_("Model as code")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema", "table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "read"
    bulk: ClassVar[bool] = True
    params_model = DescribeModelParams

    def __init__(self, session: MysqlSession, catalog: MysqlCatalog) -> None:
        self._relation = MysqlRelation(session)
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
                raise ActionRefused(
                    "not_applicable", say("{name} has no model to write out", name=node.name)
                )
            for relation_id in relations:
                if relation_id not in gathered:
                    gathered[relation_id] = await self._relation.relation_model(relation_id)
        return list(gathered.values())


async def _one_chunk(body: bytes) -> AsyncIterator[bytes]:
    yield body


class MysqlActionType(ActionType, Protocol):
    def __call__(self, session: MysqlSession, catalog: MysqlCatalog) -> Action[Any]: ...


MYSQL_ACTION_TYPES: tuple[MysqlActionType, ...] = (
    CreateDatabase,
    RenameRelation,
    MoveRelation,
    LoadCsv,
    CreateTable,
    DropRelation,
    DropDatabase,
    DescribeModel,
    CreateUser,
)

# Which report admits which commands: a report is a kind, and only the Users
# report adds an account (D243).
REPORT_COMMANDS: dict[str, tuple[str, ...]] = {USERS_REPORT_ID: (CreateUser.name,)}


class MysqlActions:
    def __init__(self, session: MysqlSession, catalog: MysqlCatalog) -> None:
        self._catalog = catalog
        self._actions = ActionSet([action_type(session, catalog) for action_type in MYSQL_ACTION_TYPES])

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        if node_id is None:
            return [self._actions.get(CreateDatabase.name)]
        node = (await self._catalog.path_to(node_id))[-1]
        # The server's own databases and what is in them are read and never
        # changed; their model may still be written out.
        if isinstance(node, SchemaNode | TableNode | ViewNode):
            if node.is_system:
                return [self._actions.get(DescribeModel.name)]
            return self._actions.for_kind(node.kind)
        if isinstance(node, ReportNode):
            return [self._actions.get(name) for name in REPORT_COMMANDS.get(node_id, ())]
        return []
