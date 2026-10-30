"""What a ClickHouse source can be asked to do from its catalog (D9, D276).

ClickHouse keeps every structure change at once (D271), so nothing here is
rehearsed: a preview reads the `system` tables for what a change would meet.
No foreign key stops a drop, so what a preview names is what would stop
working — a materialized view fed by a table being dropped.
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
from app.adapters.catalog import NodeKind, SchemaNode, TableNode, ViewNode
from app.adapters.clickhouse.catalog import ClickhouseCatalog, is_system_database
from app.adapters.clickhouse.columns import ALTERING
from app.adapters.clickhouse.design import ClickhouseTableDesign
from app.adapters.clickhouse.relation import ClickhouseRelation
from app.adapters.clickhouse.relation_changes import ClickhouseRelationChanges
from app.adapters.clickhouse.session import ClickhouseSession
from app.adapters.clickhouse.sql import SQL, Composable, Identifier
from app.adapters.clickhouse.update import ClickhouseUpdate
from app.adapters.csv_load import LoadCsvParams as SharedLoadCsvParams
from app.adapters.csv_load import chosen_rows, read_upload, table_name
from app.adapters.database_ids import database_id, parse, relation_id
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

# The longest name the forms here take; ClickHouse allows more.
NAME_LIMIT = 63

REFUSALS: dict[int, str] = {
    82: N_("A database of that name is already there"),
    57: N_("Something with that name is already there"),
    81: N_("That database is not there"),
    60: N_("That relation is not there"),
    497: N_("This connection may not change that"),
    # The server's guard against dropping a table larger than its
    # `max_table_size_to_drop`, 50 GB unless configured otherwise.
    359: N_("The server refuses to drop a table this large; its administrator can raise the limit"),
    630: N_("Other tables or views depend on it"),
}


def _name(value: str) -> str:
    """A database or relation name ClickHouse will keep as given."""
    if value == "" or value != value.strip() or len(value) > NAME_LIMIT:
        raise ValueError(
            say(
                "A name is 1 to {limit} characters and does not start or end with spaces",
                limit=NAME_LIMIT,
            )
        )
    return value


_DATABASE = "SELECT 1 FROM system.databases WHERE name = {database:String}"


async def _database_exists(session: ClickhouseSession, name: str) -> bool:
    return bool(await session.query(_DATABASE, {"database": name}))


async def _run(session: ClickhouseSession, *statements: Composable) -> None:
    """Structure statements, each waited for; a refusal is the action's."""
    try:
        for statement in statements:
            await session.command(statement.text(), {}, settings=ALTERING, refusals=REFUSALS)
    except ValueError as refused:
        raise ActionRefused("not_applicable", str(refused)) from None


async def create_database(session: ClickhouseSession, name: str) -> None:
    _name(name)
    if is_system_database(name):
        raise ActionRefused("not_applicable", say("That database name belongs to the server"))
    if await _database_exists(session, name):
        raise ActionRefused("conflict", say('Database "{name}" already exists', name=name))
    await _run(session, SQL("CREATE DATABASE {}").format(Identifier(name)))


async def _database_target(catalog: ClickhouseCatalog, node_id: str | None, refused: str) -> SchemaNode:
    if node_id is None:
        raise ActionRefused("not_applicable", say("Choose a database"))
    node = (await catalog.path_to(node_id))[-1]
    if not isinstance(node, SchemaNode) or node.is_system:
        raise ActionRefused("not_applicable", refused)
    return node


async def _relation_target(
    catalog: ClickhouseCatalog, node_id: str | None, refused: str
) -> tuple[str, TableNode | ViewNode]:
    if node_id is None:
        raise ActionRefused("not_applicable", say("Choose a relation"))
    path = await catalog.path_to(node_id)
    node = path[-1]
    if not isinstance(node, TableNode | ViewNode) or node.is_system:
        raise ActionRefused("not_applicable", refused)
    return path[0].name, node


class CreateDatabaseParams(BaseModel):
    name: str = Field(title=N_("Name"))

    _check = field_validator("name")(_name)


class CreateDatabase(JsonAction[CreateDatabaseParams]):
    """A database at the top of the connection, beside the others (D267)."""

    name: ClassVar[str] = "create_database"
    title: ClassVar[str] = N_("New database")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset()
    acts_on: ClassVar[ActsOn] = "level"
    requires: ClassVar[Access] = "structure"
    params_model = CreateDatabaseParams

    def __init__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> None:
        self._session = session

    async def run(self, node_id: str | None, params: CreateDatabaseParams) -> ActionResult:
        if node_id is not None:
            raise ActionRefused(
                "not_applicable", say("Databases are created at the top of the connection")
            )
        await create_database(self._session, params.name)
        return ActionResult(
            message=say("Database {name} created", name=params.name),
            reload_node_ids=[None, database_id(params.name)],
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
        "SELECT count() AS found FROM system.tables WHERE database = {database:String} "
        "AND engine NOT IN ('View', 'MaterializedView', 'Dictionary') AND NOT startsWith(name, '.inner')",
        N_("{count} tables and their rows"),
    ),
    (
        "SELECT count() AS found FROM system.tables WHERE database = {database:String} "
        "AND engine IN ('View', 'MaterializedView')",
        N_("{count} views"),
    ),
    (
        "SELECT count() AS found FROM system.dictionaries WHERE database = {database:String}",
        N_("{count} dictionaries"),
    ),
)

# Materialized views in other databases fed by a table of this one.
_FED_FROM = """
SELECT arrayJoin(arrayZip(dependencies_database, dependencies_table)) AS view, name
FROM system.tables
WHERE database = {database:String}
"""


class DropDatabase(JsonAction[DropDatabaseParams]):
    """Drop a database and everything in it, once it was said what that is."""

    name: ClassVar[str] = "drop_database"
    title: ClassVar[str] = N_("Drop database")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "group"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    params_model = DropDatabaseParams

    def __init__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: DropDatabaseParams) -> ActionResult:
        preview = await self._preview(node_id, params)
        if preview.blocked:
            raise ActionRefused("not_applicable", preview.summary)
        node = await self._target(node_id)
        await _run(self._session, SQL("DROP DATABASE {}").format(Identifier(node.name)))
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
        held: list[str] = []
        for statement, sentence in _HOLDINGS:
            count = int((await self._session.query(statement, {"database": node.name}))[0]["found"])
            if count:
                held.append(say(sentence, count=count))
        fed = [
            say(
                "Materialized view {view} reads {name} and will stop working",
                view=f"{row['view'][0]}.{row['view'][1]}",
                name=f"{node.name}.{row['name']}",
            )
            for row in await self._session.query(_FED_FROM, {"database": node.name})
            if row["view"][0] != node.name
        ]
        if not held:
            return ActionPreview(summary=say("Database {name} is empty", name=node.name))
        if not params.cascade:
            return ActionPreview(summary=say("The database is not empty"), items=held, blocked=True)
        return ActionPreview(
            summary=say("What dropping {name} would do:", name=node.name),
            items=[say("Drop {what}", what=line) for line in held] + fed,
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

    def __init__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: RenameRelationParams) -> ActionResult:
        schema, node = await _relation_target(self._catalog, node_id, say("This relation cannot be renamed"))
        if params.new_name == node.name:
            raise ActionRefused("conflict", say("The relation already has that name"))
        siblings = await self._catalog.list_children(database_id(schema))
        if params.new_name in {sibling.name for sibling in siblings}:
            raise ActionRefused(
                "conflict",
                say('{schema} already has a relation named "{name}"', schema=schema, name=params.new_name),
            )
        await _run(
            self._session,
            SQL("RENAME TABLE {} TO {}").format(
                Identifier(schema, node.name), Identifier(schema, params.new_name)
            ),
        )
        return ActionResult(
            message=say("Renamed to {name}", name=params.new_name),
            reload_node_ids=[database_id(schema)],
            replacement=NodeReplacement(
                old_node_id=node.id,
                new_node_id=relation_id(schema, params.new_name),
                title=params.new_name,
            ),
        )


class MoveRelationParams(BaseModel):
    # One of the source's own database ids, which the form lists.
    target_schema: str = Field(
        title=N_("Target database"), json_schema_extra={"x-ui-purpose": "grouping"}
    )


class MoveRelation(JsonAction[MoveRelationParams]):
    """Move a table or a view to another database, by RENAME TABLE."""

    name: ClassVar[str] = "move_relation"
    title: ClassVar[str] = N_("Move to database")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    bulk: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    params_model = MoveRelationParams

    def __init__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: MoveRelationParams) -> ActionResult:
        schema, node = await _relation_target(self._catalog, node_id, say("This relation cannot be moved"))
        target_schema, relation = parse(params.target_schema)
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
        siblings = await self._catalog.list_children(database_id(target_schema))
        if node.name in {sibling.name for sibling in siblings}:
            raise ActionRefused(
                "conflict",
                say('{schema} already has a relation named "{name}"', schema=target_schema, name=node.name),
            )
        await _run(
            self._session,
            SQL("RENAME TABLE {} TO {}").format(
                Identifier(schema, node.name), Identifier(target_schema, node.name)
            ),
        )
        return ActionResult(
            message=say("{name} moved to {schema}", name=node.name, schema=target_schema),
            reload_node_ids=[database_id(schema), database_id(target_schema)],
            replacement=NodeReplacement(
                old_node_id=node.id,
                new_node_id=relation_id(target_schema, node.name),
                title=node.name,
            ),
        )


class DropRelationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


_FED_BY = """
SELECT arrayJoin(arrayZip(dependencies_database, dependencies_table)) AS view
FROM system.tables
WHERE database = {database:String} AND name = {table:String}
"""


class DropRelation(JsonAction[DropRelationParams]):
    """Drop relations together, once what reads them was named."""

    name: ClassVar[str] = "drop_relation"
    title: ClassVar[str] = N_("Drop")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = True
    params_model = DropRelationParams

    def __init__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> None:
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
        # Views first: a materialized view fed by a table of the set goes
        # before the table it reads.
        ordered = sorted(targets, key=lambda target: not isinstance(target[1], ViewNode))
        await _run(
            self._session,
            *(
                SQL("DROP VIEW {}" if isinstance(node, ViewNode) else "DROP TABLE {}").format(
                    Identifier(schema, node.name)
                )
                for schema, node in ordered
            ),
        )
        name = _one_name(targets)
        return ActionResult(
            message=(
                say("{name} dropped", name=name)
                if name is not None
                else say("{count} relations dropped", count=len(targets))
            ),
            reload_node_ids=[*sorted({database_id(schema) for schema, _ in targets})],
        )

    async def _targets(self, node_ids: Sequence[str | None]) -> list[tuple[str, TableNode | ViewNode]]:
        if len(set(node_ids)) != len(node_ids):
            raise ActionRefused("not_applicable", say("A relation may be dropped only once"))
        return [
            await _relation_target(self._catalog, node_id, say("This relation cannot be dropped"))
            for node_id in node_ids
        ]

    async def _preview(self, targets: Sequence[tuple[str, TableNode | ViewNode]]) -> ActionPreview:
        name = _one_name(targets)
        dropped = {(schema, node.name) for schema, node in targets}
        items: list[str] = []
        for schema, node in targets:
            for row in await self._session.query(_FED_BY, {"database": schema, "table": node.name}):
                view = (str(row["view"][0]), str(row["view"][1]))
                if view not in dropped:
                    items.append(
                        say(
                            "Materialized view {view} reads {name} and will stop working",
                            view=".".join(view),
                            name=node.name,
                        )
                    )
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

    Every column is String: a file states no types, and one read off its rows
    would depend on how many were looked at.
    """

    name: ClassVar[str] = "load_csv"
    title: ClassVar[str] = N_("Load from CSV")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = False
    params_model = LoadCsvParams

    def __init__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> None:
        self._session = session
        self._catalog = catalog
        self._relations = ClickhouseRelationChanges(
            session, catalog, ClickhouseUpdate(session, ClickhouseRelation(session))
        )

    async def run(self, node_id: str | None, params: LoadCsvParams, payload: FilePayload) -> ActionResult:
        if node_id is None:
            raise ActionRefused("not_applicable", say("Choose a database to load into"))
        if params.create_schema:
            await create_database(self._session, params.schema_name)
            database = database_id(params.schema_name)
        else:
            database = params.schema_name or node_id
            databases = await self._catalog.list_children(None)
            if database not in {
                node.id for node in databases if isinstance(node, SchemaNode) and not node.is_system
            }:
                raise ActionRefused(
                    "not_applicable", say('Database "{name}" does not exist', name=parse(database)[0])
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
                    columns=[NewColumn(name=target, type_code="text") for target in targets],
                    rows=rows,
                )
            )
        except ValueError as refused:
            raise ActionRefused("not_applicable", str(refused)) from None
        if not isinstance(result, RelationCreated):
            cell = result.cells[0]
            raise ActionRefused(
                "not_applicable",
                say("Row {row}, column {column}: that value cannot be read", row=cell.row + 1, column=cell.column),
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
    """Design a table, review its statement, then create it (D117, D274)."""

    name: ClassVar[str] = "create_table"
    title: ClassVar[str] = N_("Create table")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = False
    params_model = CreateTableParams

    def __init__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> None:
        self._design = ClickhouseTableDesign(session, catalog)

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

    MySQL's action, over this source's relations: what it gathers is the
    catalog's, and the gathering is short enough that sharing it would cost
    more than it saves.
    """

    name: ClassVar[str] = "describe_model"
    title: ClassVar[str] = N_("Model as code")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema", "table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "read"
    bulk: ClassVar[bool] = True
    params_model = DescribeModelParams

    def __init__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> None:
        self._relation = ClickhouseRelation(session)
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
        stem = (parse(node_ids[0])[1] or parse(node_ids[0])[0]) if len(node_ids) == 1 else "model"
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
            for one in relations:
                if one not in gathered:
                    gathered[one] = await self._relation.relation_model(one)
        return list(gathered.values())


async def _one_chunk(body: bytes) -> AsyncIterator[bytes]:
    yield body


class ClickhouseActionType(ActionType, Protocol):
    def __call__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> Action[Any]: ...


CLICKHOUSE_ACTION_TYPES: tuple[ClickhouseActionType, ...] = (
    CreateDatabase,
    RenameRelation,
    MoveRelation,
    LoadCsv,
    CreateTable,
    DropRelation,
    DropDatabase,
    DescribeModel,
)


class ClickhouseActions:
    def __init__(self, session: ClickhouseSession, catalog: ClickhouseCatalog) -> None:
        self._catalog = catalog
        self._actions = ActionSet([action_type(session, catalog) for action_type in CLICKHOUSE_ACTION_TYPES])

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
        return []
