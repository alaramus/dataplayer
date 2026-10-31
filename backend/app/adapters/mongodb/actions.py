"""What a MongoDB source can be asked to do from its catalog (D9, D290).

A database exists once something is stored in it, so one is made with its
first collection. Collections are made, renamed, moved to another database
and dropped; a view is dropped and nothing else, since `renameCollection`
refuses one. Nothing here can be rehearsed, so a drop's preview reads the
views that read what it drops, as ClickHouse's does.
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
from app.adapters.csv_load import LoadCsvParams as SharedLoadCsvParams
from app.adapters.csv_load import chosen_rows, read_upload, table_name
from app.adapters.database_ids import database_id, parse, relation_id
from app.adapters.model_code import DIALECT_SUFFIX, DIALECT_TITLE, CodeDialect, render
from app.adapters.mongodb.catalog import MongodbCatalog, is_system_database
from app.adapters.mongodb.relation import MongodbRelation
from app.adapters.mongodb.session import MongodbSession
from app.adapters.relation import RelationModel
from app.core.access import Access
from app.core.translation import N_, say

# What a database's name may not hold, on any platform the server runs on.
_DATABASE_FORBIDDEN = set('/\\. "$*<>:|?\x00')
DATABASE_NAME_BYTES = 63
# A collection's whole name, database and dot included, in bytes.
NAMESPACE_BYTES = 255


def database_name(value: str) -> str:
    if (
        value == ""
        or len(value.encode()) > DATABASE_NAME_BYTES
        or any(character in _DATABASE_FORBIDDEN for character in value)
    ):
        raise ValueError(
            say(
                'A database name is 1 to {limit} bytes, without spaces, dots or any of /\\"$*<>:|?',
                limit=DATABASE_NAME_BYTES,
            )
        )
    return value


def collection_name(value: str) -> str:
    if value == "" or value != value.strip() or "$" in value or "\x00" in value:
        raise ValueError(
            say("A collection name is not empty, holds no $, and does not start or end with spaces")
        )
    if value.startswith("system."):
        raise ValueError(say('A name starting "system." is the server\'s own'))
    return value


def _fits(database: str, collection: str) -> None:
    if len(f"{database}.{collection}".encode()) > NAMESPACE_BYTES:
        raise ActionRefused(
            "not_applicable",
            say("A database and collection name together are at most {limit} bytes", limit=NAMESPACE_BYTES),
        )


async def _collections(session: MongodbSession, database: str) -> list[dict[str, Any]]:
    async with session.client() as client:
        with session.failures():
            cursor = await client[database].list_collections()
            return [dict(info) for info in await cursor.to_list()]


async def _command(session: MongodbSession, database: str, command: dict[str, Any]) -> None:
    async with session.client() as client:
        with session.failures():
            await client[database].command(command)


async def _database_target(catalog: MongodbCatalog, node_id: str | None, refused: str) -> SchemaNode:
    if node_id is None:
        raise ActionRefused("not_applicable", say("Choose a database"))
    node = (await catalog.path_to(node_id))[-1]
    if not isinstance(node, SchemaNode) or node.is_system:
        raise ActionRefused("not_applicable", refused)
    return node


async def _collection_target(
    catalog: MongodbCatalog, node_id: str | None, refused: str, *, views: bool
) -> tuple[str, TableNode | ViewNode]:
    if node_id is None:
        raise ActionRefused("not_applicable", say("Choose a collection"))
    path = await catalog.path_to(node_id)
    node = path[-1]
    wanted = (TableNode, ViewNode) if views else (TableNode,)
    if not isinstance(node, wanted) or node.is_system:
        raise ActionRefused("not_applicable", refused)
    return path[0].name, node


async def _taken(session: MongodbSession, database: str, name: str) -> None:
    if name in {str(info["name"]) for info in await _collections(session, database)}:
        raise ActionRefused(
            "conflict", say('{schema} already has a collection named "{name}"', schema=database, name=name)
        )


async def create_collection(session: MongodbSession, database: str, name: str) -> None:
    _fits(database, name)
    await _taken(session, database, name)
    await _command(session, database, {"create": name})


class CreateDatabaseParams(BaseModel):
    name: str = Field(title=N_("Name"))
    collection: str = Field(
        title=N_("First collection"),
        description=N_("A database exists once it holds something"),
    )

    _database = field_validator("name")(database_name)
    _collection = field_validator("collection")(collection_name)


class CreateDatabase(JsonAction[CreateDatabaseParams]):
    """A database at the top of the connection, made with its first collection."""

    name: ClassVar[str] = "create_database"
    title: ClassVar[str] = N_("New database")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset()
    acts_on: ClassVar[ActsOn] = "level"
    requires: ClassVar[Access] = "structure"
    params_model = CreateDatabaseParams

    def __init__(self, session: MongodbSession, catalog: MongodbCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: CreateDatabaseParams) -> ActionResult:
        if node_id is not None:
            raise ActionRefused("not_applicable", say("Databases are created at the top of the connection"))
        if params.name in await self._catalog.database_names() and await _collections(
            self._session, params.name
        ):
            raise ActionRefused("conflict", say('Database "{name}" already exists', name=params.name))
        await create_collection(self._session, params.name, params.collection)
        return ActionResult(
            message=say("Database {name} created", name=params.name),
            reload_node_ids=[None, database_id(params.name)],
            created_node_id=relation_id(params.name, params.collection),
        )


class CreateCollectionParams(BaseModel):
    name: str = Field(title=N_("Name"), json_schema_extra={"x-ui-purpose": "node-name"})

    _check = field_validator("name")(collection_name)


class CreateCollection(JsonAction[CreateCollectionParams]):
    name: ClassVar[str] = "create_collection"
    title: ClassVar[str] = N_("New collection")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    params_model = CreateCollectionParams

    def __init__(self, session: MongodbSession, catalog: MongodbCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: CreateCollectionParams) -> ActionResult:
        node = await _database_target(self._catalog, node_id, say("Collections are not made here"))
        await create_collection(self._session, node.name, params.name)
        return ActionResult(
            message=say("{name} created", name=params.name),
            reload_node_ids=[node.id],
            created_node_id=relation_id(node.name, params.name),
        )


class DropDatabaseParams(BaseModel):
    cascade: bool = Field(
        default=False,
        title=N_("Also drop everything in it"),
        description=N_("Required when the database still holds anything"),
    )


class DropDatabase(JsonAction[DropDatabaseParams]):
    name: ClassVar[str] = "drop_database"
    title: ClassVar[str] = N_("Drop database")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "group"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    params_model = DropDatabaseParams

    def __init__(self, session: MongodbSession, catalog: MongodbCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: DropDatabaseParams) -> ActionResult:
        preview = await self._preview(node_id, params)
        if preview.blocked:
            raise ActionRefused("not_applicable", preview.summary)
        node = await self._target(node_id)
        async with self._session.client() as client:
            with self._session.failures():
                await client.drop_database(node.name)
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
        infos = [info for info in await _collections(self._session, node.name) if not str(info["name"]).startswith("system.")]
        views = sum(1 for info in infos if info.get("type") == "view")
        held: list[str] = []
        if len(infos) - views:
            held.append(say("{count} collections and their documents", count=len(infos) - views))
        if views:
            held.append(say("{count} views", count=views))
        if not held:
            return ActionPreview(summary=say("Database {name} is empty", name=node.name))
        if not params.cascade:
            return ActionPreview(summary=say("The database is not empty"), items=held, blocked=True)
        return ActionPreview(
            summary=say("What dropping {name} would do:", name=node.name),
            items=[say("Drop {what}", what=line) for line in held],
        )


class RenameCollectionParams(BaseModel):
    new_name: str = Field(title=N_("New name"), json_schema_extra={"x-ui-purpose": "node-name"})

    _check = field_validator("new_name")(collection_name)


class RenameCollection(JsonAction[RenameCollectionParams]):
    """A collection renamed in its database by `renameCollection`.

    A view cannot be renamed: the server refuses, and it is made again from
    its pipeline in mongosh.
    """

    name: ClassVar[str] = "rename_relation"
    title: ClassVar[str] = N_("Rename")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "structure"
    params_model = RenameCollectionParams

    def __init__(self, session: MongodbSession, catalog: MongodbCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: RenameCollectionParams) -> ActionResult:
        database, node = await _collection_target(
            self._catalog, node_id, say("This collection cannot be renamed"), views=False
        )
        if params.new_name == node.name:
            raise ActionRefused("conflict", say("The collection already has that name"))
        _fits(database, params.new_name)
        await _taken(self._session, database, params.new_name)
        await _command(
            self._session,
            "admin",
            {"renameCollection": f"{database}.{node.name}", "to": f"{database}.{params.new_name}"},
        )
        return ActionResult(
            message=say("Renamed to {name}", name=params.new_name),
            reload_node_ids=[database_id(database)],
            replacement=NodeReplacement(
                old_node_id=node.id, new_node_id=relation_id(database, params.new_name), title=params.new_name
            ),
        )


class MoveCollectionParams(BaseModel):
    # One of the source's own database ids, which the form lists.
    target_schema: str = Field(title=N_("Target database"), json_schema_extra={"x-ui-purpose": "grouping"})


class MoveCollection(JsonAction[MoveCollectionParams]):
    """A collection moved to another database of the server, documents and indexes."""

    name: ClassVar[str] = "move_relation"
    title: ClassVar[str] = N_("Move to database")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table"})
    acts_on: ClassVar[ActsOn] = "node"
    bulk: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    params_model = MoveCollectionParams

    def __init__(self, session: MongodbSession, catalog: MongodbCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: MoveCollectionParams) -> ActionResult:
        database, node = await _collection_target(
            self._catalog, node_id, say("This collection cannot be moved"), views=False
        )
        target, rest = parse(params.target_schema)
        if rest is not None or target not in await self._catalog.database_names():
            raise ActionRefused("not_applicable", say('Database "{name}" does not exist', name=target))
        if is_system_database(target):
            raise ActionRefused("not_applicable", say("Collections cannot be moved into the server's own databases"))
        if target == database:
            raise ActionRefused("conflict", say("The collection is already in {schema}", schema=database))
        _fits(target, node.name)
        await _taken(self._session, target, node.name)
        await _command(
            self._session,
            "admin",
            {"renameCollection": f"{database}.{node.name}", "to": f"{target}.{node.name}"},
        )
        return ActionResult(
            message=say("{name} moved to {schema}", name=node.name, schema=target),
            reload_node_ids=[database_id(database), database_id(target)],
            replacement=NodeReplacement(
                old_node_id=node.id, new_node_id=relation_id(target, node.name), title=node.name
            ),
        )


class DropCollectionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DropCollection(JsonAction[DropCollectionParams]):
    """Collections and views dropped together, after saying which views read them."""

    name: ClassVar[str] = "drop_relation"
    title: ClassVar[str] = N_("Drop")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = True
    params_model = DropCollectionParams

    def __init__(self, session: MongodbSession, catalog: MongodbCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: DropCollectionParams) -> ActionResult:
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
            raise ActionRefused("not_applicable", say("A collection may be dropped only once"))
        return [
            await _collection_target(self._catalog, node_id, say("This collection cannot be dropped"), views=True)
            for node_id in node_ids
        ]

    async def _drop(self, node_ids: Sequence[str | None]) -> ActionResult:
        targets = await self._targets(node_ids)
        async with self._session.client() as client:
            with self._session.failures():
                for database, node in targets:
                    await client[database].drop_collection(node.name)
        databases = sorted({database for database, _ in targets})
        return ActionResult(
            message=(
                say("{name} dropped", name=targets[0][1].name)
                if len(targets) == 1
                else say("{count} collections dropped", count=len(targets))
            ),
            reload_node_ids=[database_id(database) for database in databases],
        )

    async def _preview(self, targets: Sequence[tuple[str, TableNode | ViewNode]]) -> ActionPreview:
        dropped = {(database, node.name) for database, node in targets}
        items: list[str] = []
        for database in sorted({database for database, _ in targets}):
            for info in await _collections(self._session, database):
                source = info.get("options", {}).get("viewOn")
                name = str(info["name"])
                if info.get("type") == "view" and (database, source) in dropped and (database, name) not in dropped:
                    items.append(say("View {view} reads {name} and will stop working", view=name, name=source))
        for _, node in targets:
            if isinstance(node, TableNode) and node.row_count_estimate:
                items.append(
                    say("{name} holds {count} documents", name=node.name, count=node.row_count_estimate)
                )
        one = targets[0][1].name if len(targets) == 1 else None
        return ActionPreview(
            summary=(
                say("What dropping {name} would do:", name=one)
                if one is not None
                else say("What dropping {count} collections would do:", count=len(targets))
            ),
            items=items,
        )


class LoadCsvParams(SharedLoadCsvParams):
    @field_validator("name")
    @classmethod
    def named_or_empty(cls, value: str) -> str:
        return value if value == "" else collection_name(value)


class LoadCsv(FileAction[LoadCsvParams]):
    """A delimited file, uploaded, becomes a collection of documents.

    Every value is a string, as every column of a loaded table is text
    elsewhere: a file states no types. An empty value is no field.
    """

    name: ClassVar[str] = "load_csv"
    title: ClassVar[str] = N_("Load from CSV")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema"})
    acts_on: ClassVar[ActsOn] = "destination"
    requires: ClassVar[Access] = "structure"
    bulk: ClassVar[bool] = False
    params_model = LoadCsvParams

    def __init__(self, session: MongodbSession, catalog: MongodbCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def run(self, node_id: str | None, params: LoadCsvParams, payload: FilePayload) -> ActionResult:
        node = await _database_target(self._catalog, node_id, say("Choose a database to load into"))
        if params.create_schema or params.schema_name not in ("", node.name):
            raise ActionRefused("not_applicable", say("A file is loaded into the database it was dropped on"))
        name = table_name(params, payload, collection_name)
        _fits(node.name, name)
        await _taken(self._session, node.name, name)
        targets, rows = chosen_rows(await read_upload(payload), params, collection_name)
        documents = [
            {target: value for target, value in zip(targets, row, strict=True) if value not in (None, "")}
            for row in rows
        ]
        async with self._session.client() as client:
            with self._session.failures():
                await client[node.name].create_collection(name)
                if documents:
                    await client[node.name][name].insert_many(documents)
        return ActionResult(
            message=say("{name} created with {count} documents", name=name, count=len(documents)),
            reload_node_ids=[node.id],
            created_node_id=relation_id(node.name, name),
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
    """The fields found in what was selected, written as code (D73)."""

    name: ClassVar[str] = "describe_model"
    title: ClassVar[str] = N_("Model as code")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"schema", "table", "view"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "read"
    bulk: ClassVar[bool] = True
    params_model = DescribeModelParams

    def __init__(self, session: MongodbSession, catalog: MongodbCatalog) -> None:
        self._relation = MongodbRelation(session)
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
        first = parse(node_ids[0])
        stem = (first[1] or first[0]) if len(node_ids) == 1 else "model"
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
                    if isinstance(child, TableNode | ViewNode) and not child.is_system
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


class MongodbActionType(ActionType, Protocol):
    def __call__(self, session: MongodbSession, catalog: MongodbCatalog) -> Action[Any]: ...


MONGODB_ACTION_TYPES: tuple[MongodbActionType, ...] = (
    CreateDatabase,
    CreateCollection,
    RenameCollection,
    MoveCollection,
    LoadCsv,
    DropCollection,
    DropDatabase,
    DescribeModel,
)


class MongodbActions:
    def __init__(self, session: MongodbSession, catalog: MongodbCatalog) -> None:
        self._catalog = catalog
        self._actions = ActionSet([action_type(session, catalog) for action_type in MONGODB_ACTION_TYPES])

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        if node_id is None:
            return [self._actions.get(CreateDatabase.name)]
        node = (await self._catalog.path_to(node_id))[-1]
        if isinstance(node, SchemaNode | TableNode | ViewNode):
            if node.is_system:
                return [self._actions.get(DescribeModel.name)]
            return self._actions.for_kind(node.kind)
        return []
