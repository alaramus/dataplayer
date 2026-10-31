"""Both ends of a copy of MongoDB collections into another MongoDB (D182, D291).

The source describes a collection by what `listCollections` and
`listIndexes` say of it: its options — a validator, a cap, a collation — and
each index's key and options, as canonical Extended JSON. The destination,
which speaks the same dialect, makes the collection with those options, loads
the documents, and builds the indexes over them after. The plan it shows is
written as the `mongosh` lines that would do the same.

The documents travel whole, one canonical Extended JSON document a line, so
every BSON type arrives as itself. Nothing holds the collections still while
they are read, and a failure drops every collection this copy made.
"""

import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal

from bson import json_util

from app.adapters.database_ids import parse
from app.adapters.mongodb.actions import NAMESPACE_BYTES, collection_name
from app.adapters.mongodb.catalog import is_system_collection
from app.adapters.mongodb.inspection import collection_info, collection_type, statistics
from app.adapters.mongodb.rows import canonical, from_canonical
from app.adapters.mongodb.session import (
    DOCUMENT_VALIDATION_FAILURE,
    DUPLICATE_KEY,
    MongodbSession,
)
from app.adapters.protocol import NodeNotFound
from app.adapters.table_copy import (
    MAX_COPIED_TABLES,
    Arrived,
    CopiedIndex,
    CopiedTable,
    CopyLoad,
    CopyProblem,
    CopyStatement,
    RowsOf,
    TableCopyPlan,
    TableCopyRequest,
)
from app.core.translation import N_, say

DIALECT = "mongodb"

COPY_REFUSALS: dict[int, str] = {
    48: N_("Something with that name is already there"),
    DUPLICATE_KEY: N_("Two documents share a value a unique index allows once"),
    DOCUMENT_VALIDATION_FAILURE: N_("A document breaks the collection's validator"),
}
# Documents a batch carries each way.
BATCH = 1000
# Options of a collection a copy carries; a view's source and a time series'
# buckets are not copied, and neither is anything the server sets itself.
_CARRIED = ("validator", "validationLevel", "validationAction", "capped", "size", "max", "collation")
# Index options a copy carries.
_INDEX_OPTIONS = (
    "unique",
    "sparse",
    "partialFilterExpression",
    "expireAfterSeconds",
    "collation",
    "weights",
    "default_language",
    "language_override",
    "textIndexVersion",
    "2dsphereIndexVersion",
    "wildcardProjection",
    "hidden",
)


def _shell(value: Any) -> str:
    return json_util.dumps(value, json_options=json_util.RELAXED_JSON_OPTIONS)


class MongodbTableCopy:
    """Both ends of a copy of MongoDB collections."""

    table_copy_dialect = DIALECT

    def __init__(self, session: MongodbSession) -> None:
        self._session = session

    @property
    def table_copy_database(self) -> str:
        """The server, by the address it is reached at."""
        options = self._session.options
        through = f"ssh:{options.ssh_tunnel}/" if options.ssh_tunnel else ""
        return f"mongodb://{through}{options.host.lower()}:{options.port}"

    # The source's half.

    async def describe_for_copy(self, node_ids: list[str]) -> list[CopiedTable]:
        return [await self._describe(node_id) for node_id in node_ids]

    async def _describe(self, node_id: str) -> CopiedTable:
        database, name = parse(node_id)
        if name is None:
            raise NodeNotFound(node_id)
        async with self._session.client() as client:
            with self._session.failures():
                info = await collection_info(client, database, name)
                if info is None:
                    raise NodeNotFound(node_id)
                base = CopiedTable(node_id=node_id, schema_name=database, name=name)
                if is_system_collection(database, name):
                    return base.model_copy(update={"refusal": say('"{name}" belongs to the server', name=name)})
                kind = collection_type(info)
                if kind != "collection":
                    return base.model_copy(
                        update={"refusal": say("only collections are copied with their documents")}
                    )
                indexes = [dict(index) for index in await (await client[database][name].list_indexes()).to_list()]
                count, _ = await statistics(client, database, name)
        options = {key: value for key, value in dict(info.get("options") or {}).items() if key in _CARRIED}
        return base.model_copy(
            update={
                "indexes": [
                    CopiedIndex(
                        name=str(index["name"]),
                        unique=bool(index.get("unique")),
                        body=canonical(
                            {
                                "key": index["key"],
                                **{option: index[option] for option in _INDEX_OPTIONS if option in index},
                            }
                        ),
                    )
                    for index in indexes
                    if index.get("name") != "_id_"
                ],
                "row_estimate": count,
                "options": canonical(options),
            }
        )

    @asynccontextmanager
    async def reading_tables(self) -> AsyncIterator[_Documents]:
        """Each collection read when its turn comes: there is no snapshot to hold."""
        yield _Documents(self._session)

    # The destination's half.

    async def free_table_names(self, place_node_id: str, wanted: list[str]) -> list[str]:
        taken = await self._taken(_database(place_node_id))
        free: list[str] = []
        for name in wanted:
            chosen = _free(name, taken)
            taken.add(chosen)
            free.append(chosen)
        return free

    async def plan_table_copy(self, request: TableCopyRequest) -> TableCopyPlan:
        plan = TableCopyPlan()

        def problem(node_id: str | None, message: str, kind: Literal["invalid", "conflict"] = "invalid") -> None:
            plan.problems.append(CopyProblem(node_id=node_id, message=message, kind=kind))

        if request.dialect != DIALECT:
            problem(None, say("These tables are described in another dialect"))
            return plan
        try:
            database = _database(request.place_node_id)
        except ValueError as refused:
            problem(None, str(refused))
            return plan
        if len(request.tables) > MAX_COPIED_TABLES:
            problem(None, say("Copy at most {count} tables at a time", count=MAX_COPIED_TABLES))
            return plan
        taken = await self._taken(database)
        seen: set[str] = set()
        for target in request.tables:
            table = target.table
            if table.refusal is not None:
                problem(table.node_id, f"{table.label}: {table.refusal}")
                continue
            name = target.name
            try:
                collection_name(name)
            except ValueError as refused:
                problem(table.node_id, str(refused))
                continue
            if len(f"{database}.{name}".encode()) > NAMESPACE_BYTES:
                problem(table.node_id, say("{name} is too long a name", name=name))
                continue
            if name in seen:
                problem(table.node_id, say("Two tables cannot both be called {name}", name=name))
                continue
            seen.add(name)
            if name in taken:
                problem(
                    table.node_id,
                    say("{schema}.{name} is already there", schema=database, name=name),
                    kind="conflict",
                )
                continue
            options = from_canonical(table.options or "{}")
            plan.statements.append(
                CopyStatement(
                    node_id=table.node_id,
                    title=say("Create collection {label}", label=f"{database}.{name}"),
                    sql=f"db.getSiblingDB({json.dumps(database)}).createCollection({json.dumps(name)}, {_shell(options)})",
                )
            )
            for index in table.indexes:
                described = from_canonical(index.body)
                key = described.pop("key")
                plan.statements.append(
                    CopyStatement(
                        node_id=table.node_id,
                        title=say("Index {name} of {label}", name=index.name, label=f"{database}.{name}"),
                        sql=(
                            f"db.getSiblingDB({json.dumps(database)}).getCollection({json.dumps(name)})"
                            f".createIndex({_shell(key)}, {_shell({'name': index.name, **described})})"
                        ),
                        stage="after",
                    )
                )
            if request.rows:
                plan.loads.append(CopyLoad(node_id=table.node_id, schema_name=database, name=name, columns=[]))
        return plan

    async def carry_table_copy(self, request: TableCopyRequest, rows_of: RowsOf, arrived: Arrived) -> None:
        plan = await self.plan_table_copy(request)
        if plan.problems:
            raise ValueError(plan.problems[0].message)
        database = _database(request.place_node_id)
        made: list[str] = []
        step = say("Preparing the copy")
        async with self._session.client() as client:
            place = client[database]
            try:
                with self._session.failures(COPY_REFUSALS):
                    for target in request.tables:
                        step = say("Create collection {label}", label=f"{database}.{target.name}")
                        options = from_canonical(target.table.options or "{}")
                        await place.command({"create": target.name, **options})
                        made.append(target.name)
                    for load in plan.loads:
                        step = say("Rows of {table}", table=load.target_label)
                        await self._load(place[load.name], load, rows_of, arrived)
                    for target in request.tables:
                        for index in target.table.indexes:
                            step = say("Index {name} of {label}", name=index.name, label=f"{database}.{target.name}")
                            described = from_canonical(index.body)
                            key = described.pop("key")
                            await place[target.name].create_index(
                                list(key.items()) if isinstance(key, Mapping) else key, name=index.name, **described
                            )
            except BaseException as failure:
                for name in made:
                    await place.drop_collection(name)
                if isinstance(failure, ValueError):
                    said = str(failure)
                    raise ValueError(f"{step}: {said[:1].lower()}{said[1:]}") from None
                raise

    @staticmethod
    async def _load(collection: Any, load: CopyLoad, rows_of: RowsOf, arrived: Arrived) -> None:
        counted = {"rows": 0, "bytes": 0}
        held = b""
        batch: list[Any] = []
        async for chunk in rows_of(load):
            counted["bytes"] += len(chunk)
            held += chunk
            *lines, held = held.split(b"\n")
            for line in lines:
                if line:
                    batch.append(from_canonical(line.decode()))
            if len(batch) >= BATCH:
                await collection.insert_many(batch, ordered=True)
                counted["rows"] += len(batch)
                batch = []
            await arrived(load, counted["rows"], counted["bytes"])
        if held.strip():
            batch.append(from_canonical(held.decode()))
        if batch:
            await collection.insert_many(batch, ordered=True)
            counted["rows"] += len(batch)
        await arrived(load, counted["rows"], counted["bytes"])

    async def _taken(self, database: str) -> set[str]:
        async with self._session.client() as client:
            with self._session.failures():
                cursor = await client[database].list_collections()
                return {str(info["name"]) for info in await cursor.to_list()}


@dataclass
class _Documents:
    session: MongodbSession

    def rows(self, node_id: str, columns: list[str]) -> AsyncIterator[bytes]:
        return self._read(node_id)

    async def _read(self, node_id: str) -> AsyncIterator[bytes]:
        database, name = parse(node_id)
        if name is None:
            raise NodeNotFound(node_id)
        async with self.session.client() as client:
            with self.session.failures():
                lines: list[bytes] = []
                async for document in client[database][name].find(batch_size=BATCH):
                    lines.append(canonical(document).encode() + b"\n")
                    if len(lines) == BATCH:
                        yield b"".join(lines)
                        lines = []
                if lines:
                    yield b"".join(lines)


def _database(place_node_id: str) -> str:
    database, collection = parse(place_node_id)
    if collection is not None:
        raise ValueError(say("Paste into a database"))
    return database


def _free(name: str, taken: set[str]) -> str:
    """The name, or the first `…_copy`, `…_copy_2` nothing holds."""
    if name not in taken:
        return name
    number = 1
    while True:
        candidate = f"{name}_copy" if number == 1 else f"{name}_copy_{number}"
        if candidate not in taken:
            return candidate
        number += 1
