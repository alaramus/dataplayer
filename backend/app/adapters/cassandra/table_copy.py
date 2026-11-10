"""Tables copied with their structure between Cassandra connections (D182, D354).

The source describes each table from `system_schema`: its columns as CQL spells
their types, its key, its clustering order, its secondary indexes and the
user-defined types it uses. The destination composes `CREATE TYPE` for a type
it lacks, `CREATE TABLE`, the rows, and only then `CREATE INDEX`, so an index
is built once over the rows rather than row by row.

Rows cross as JSON lines, each an array of the cells as the grid shows them
(D342), and are read back by their column's type and written with a prepared
`INSERT`, as a block of pasted rows is (D345). A counter table is not copied:
a counter takes no `INSERT`. Nothing holds the tables still while they are
read.
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal

from app.adapters.cassandra.cql import SQL, Identifier
from app.adapters.cassandra.inspection import (
    Inspector,
    RelationFacts,
    is_system_keyspace,
)
from app.adapters.cassandra.relation import key_text
from app.adapters.cassandra.session import CassandraSession, quoted_name
from app.adapters.cassandra.types import _SCALARS, parse_value, read_cell
from app.adapters.database_ids import parse
from app.adapters.protocol import NodeNotFound
from app.adapters.table_copy import (
    MAX_COPIED_TABLES,
    Arrived,
    CopiedAttribute,
    CopiedColumn,
    CopiedIndex,
    CopiedTable,
    CopiedType,
    CopyLoad,
    CopyProblem,
    CopyStatement,
    RowsOf,
    TableCopyPlan,
    TableCopyRequest,
    TableCopyTarget,
)
from app.core.translation import say

DIALECT = "cql"
NAME_LIMIT = 48
_PLAIN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BATCH = 500
_PARALLEL = 32
_GENERIC_WORDS = frozenset({"frozen", "list", "set", "map", "tuple", "vector"})

_TYPES = "SELECT type_name, field_names, field_types FROM system_schema.types WHERE keyspace_name = ?"
_TABLES = "SELECT table_name FROM system_schema.tables WHERE keyspace_name = ?"
_VIEWS = "SELECT view_name FROM system_schema.views WHERE keyspace_name = ?"


def _used_types(
    type_text: str, known: dict[str, tuple[list[str], list[str]]]
) -> list[str]:
    """The user-defined types a type names, those they name first."""
    found: list[str] = []

    def visit(text: str) -> None:
        for word in _WORD.findall(text):
            name = word.lower()
            if name in known and name not in found and name not in _SCALARS:
                for field_type in known[name][1]:
                    visit(field_type)
                if name not in found:
                    found.append(name)

    visit(type_text)
    return [name for name in found if name not in _GENERIC_WORDS]


def _clustering_order(facts: RelationFacts) -> str:
    clustering = facts.clustering
    if not clustering or not any(column.descending for column in clustering):
        return ""
    return (
        "CLUSTERING ORDER BY ("
        + ", ".join(
            f"{quoted_name(column.name)} {'DESC' if column.descending else 'ASC'}"
            for column in clustering
        )
        + ")"
    )


@dataclass
class _Rows:
    session: CassandraSession
    inspector: Inspector

    def rows(self, node_id: str, columns: list[str]) -> AsyncIterator[bytes]:
        return self._read(node_id, columns)

    async def _read(self, node_id: str, columns: list[str]) -> AsyncIterator[bytes]:
        keyspace, name = parse(node_id)
        if name is None:
            raise NodeNotFound(node_id)
        facts = await self.inspector.relation(keyspace, name)
        if facts is None:
            raise NodeNotFound(node_id)
        types = {column.name: column.type for column in facts.columns}
        statement = SQL("SELECT {} FROM {}").format(
            SQL(", ").join(Identifier(column) for column in columns),
            Identifier(keyspace, name),
        )
        state: bytes | None = None
        while True:
            answer = await self.session.page(
                statement.text(), None, fetch_size=_BATCH, paging_state=state
            )
            if answer.rows:
                lines = [
                    json.dumps(
                        [
                            read_cell(value, types[column])
                            for value, column in zip(row, columns, strict=True)
                        ],
                        ensure_ascii=False,
                    )
                    for row in answer.rows
                ]
                yield ("\n".join(lines) + "\n").encode("utf-8")
            state = answer.paging_state
            if state is None:
                return


class CassandraTableCopy:
    """Both ends of a copy of Cassandra tables."""

    table_copy_dialect = DIALECT

    def __init__(self, session: CassandraSession, inspector: Inspector) -> None:
        self._session = session
        self._inspector = inspector

    @property
    def table_copy_database(self) -> str:
        """The cluster, by the address it is reached at."""
        options = self._session.options
        through = f"ssh:{options.ssh_tunnel}/" if options.ssh_tunnel else ""
        return f"cassandra://{through}{options.host.lower()}:{options.port}"

    # The source's half.

    async def describe_for_copy(self, node_ids: list[str]) -> list[CopiedTable]:
        return [await self._describe(node_id) for node_id in node_ids]

    async def _describe(self, node_id: str) -> CopiedTable:
        keyspace, name = parse(node_id)
        if name is None:
            raise NodeNotFound(node_id)
        facts = await self._inspector.relation(keyspace, name)
        if facts is None:
            raise NodeNotFound(node_id)
        base = CopiedTable(node_id=node_id, schema_name=keyspace, name=name)
        if facts.is_system or facts.is_virtual:
            return base.model_copy(
                update={
                    "refusal": say(
                        '"{keyspace}" belongs to the server', keyspace=keyspace
                    )
                }
            )
        if facts.is_view:
            return base.model_copy(
                update={"refusal": say("only tables are copied with their structure")}
            )
        if facts.has_counters:
            return base.model_copy(
                update={
                    "refusal": say(
                        "a counter table's counts cannot be written by INSERT"
                    )
                }
            )
        known = {
            str(row["type_name"]): (
                [str(field) for field in row["field_names"] or []],
                [str(field) for field in row["field_types"] or []],
            )
            for row in await self._session.query(_TYPES, [keyspace])
        }
        used: list[str] = []
        for column in facts.columns:
            for type_name in _used_types(column.type_text, known):
                if type_name not in used:
                    used.append(type_name)
        views = await self._inspector.relations(keyspace, False, structure=False)
        return base.model_copy(
            update={
                "comment": facts.comment,
                "columns": [
                    CopiedColumn(
                        name=column.name,
                        type_sql=column.type_text,
                        not_null=column.in_key,
                        definition=column.type_text
                        + (" static" if column.kind == "static" else ""),
                    )
                    for column in facts.columns
                ],
                "indexes": [
                    CopiedIndex(
                        name=index.name,
                        body=json.dumps(
                            {
                                "target": index.target,
                                "using": index.using if index.kind == "CUSTOM" else "",
                            }
                        ),
                    )
                    for index in facts.indexes
                ],
                "types": [
                    CopiedType(
                        schema_name=keyspace,
                        name=type_name,
                        spelled=type_name,
                        kind="composite",
                        attributes=[
                            CopiedAttribute(name=field, type_sql=field_type)
                            for field, field_type in zip(*known[type_name], strict=True)
                        ],
                    )
                    for type_name in used
                ],
                "left_behind": [
                    say("materialized view {view}", view=other.name)
                    for other in views.values()
                    if other.is_view and other.base_table == name
                ],
                # The key, and the clustering order when it is not ascending.
                "options": json.dumps(
                    {"key": key_text(facts), "order": _clustering_order(facts)}
                ),
            }
        )

    @asynccontextmanager
    async def reading_tables(self) -> AsyncIterator[_Rows]:
        """Each table read when its turn comes: Cassandra holds no snapshot."""
        async with self._session.held():
            yield _Rows(self._session, self._inspector)

    # The destination's half.

    async def _taken(self, keyspace: str) -> set[str]:
        tables = {
            str(row["table_name"])
            for row in await self._session.query(_TABLES, [keyspace])
        }
        views = {
            str(row["view_name"])
            for row in await self._session.query(_VIEWS, [keyspace])
        }
        return tables | views

    async def free_table_names(
        self, place_node_id: str, wanted: list[str]
    ) -> list[str]:
        taken = await self._taken(_keyspace(place_node_id))
        free: list[str] = []
        for name in wanted:
            chosen = _free(name, taken)
            taken.add(chosen)
            free.append(chosen)
        return free

    async def plan_table_copy(self, request: TableCopyRequest) -> TableCopyPlan:
        return await _Planner(self, request).plan()

    async def carry_table_copy(
        self, request: TableCopyRequest, rows_of: RowsOf, arrived: Arrived
    ) -> None:
        plan = await self.plan_table_copy(request)
        if plan.problems:
            raise ValueError(plan.problems[0].message)
        keyspace = _keyspace(request.place_node_id)
        made: list[str] = []
        names = {target.table.node_id: target.name for target in request.tables}
        step = say("Preparing the copy")
        async with self._session.held():
            try:
                for statement in (
                    item for item in plan.statements if item.stage == "before"
                ):
                    step = statement.title
                    await self._session.page(statement.sql, wait_seconds=120)
                    if statement.node_id is not None and statement.sql.startswith(
                        "CREATE TABLE"
                    ):
                        made.append(names[statement.node_id])
                for load in plan.loads:
                    step = say("Rows of {table}", table=load.target_label)
                    await self._insert(load, rows_of, arrived)
                for statement in (
                    item for item in plan.statements if item.stage == "after"
                ):
                    step = statement.title
                    await self._session.page(statement.sql, wait_seconds=300)
            except BaseException as failure:
                await self._undo(keyspace, made)
                if isinstance(failure, ValueError):
                    said = str(failure)
                    raise ValueError(f"{step}: {said[:1].lower()}{said[1:]}") from None
                raise

    async def _insert(self, load: CopyLoad, rows_of: RowsOf, arrived: Arrived) -> None:
        """One table's rows, read as their columns' types and written in parallel."""
        facts = await self._inspector.relation(load.schema_name, load.name)
        if facts is None:
            raise ValueError(say("The new table is not there"))
        types = {column.name: column.type_text for column in facts.columns}
        statement = (
            SQL("INSERT INTO {} ({}) VALUES ({})")
            .format(
                Identifier(load.schema_name, load.name),
                SQL(", ").join(Identifier(column) for column in load.columns),
                SQL(", ".join("?" for _ in load.columns)),
            )
            .text()
        )
        gate = asyncio.Semaphore(_PARALLEL)

        async def write(values: list[Any]) -> None:
            async with gate:
                await self._session.page(statement, values)

        rows = 0
        size = 0
        pending = b""
        async for chunk in rows_of(load):
            size += len(chunk)
            pending += chunk
            *lines, pending = pending.split(b"\n")
            parsed: list[list[Any]] = []
            for line in lines:
                if not line.strip():
                    continue
                cells = json.loads(line)
                values: list[Any] = []
                for cell, column in zip(cells, load.columns, strict=True):
                    try:
                        values.append(
                            None if cell is None else parse_value(cell, types[column])
                        )
                    except ValueError:
                        raise ValueError(
                            say(
                                'A value of "{column}" could not be read', column=column
                            )
                        ) from None
                parsed.append(values)
            await asyncio.gather(*(write(values) for values in parsed))
            rows += len(parsed)
            await arrived(load, rows, size)

    async def _undo(self, keyspace: str, made: Sequence[str]) -> None:
        """Drop the tables this copy made; nothing else had them yet."""
        for name in made:
            await self._session.page(
                SQL("DROP TABLE IF EXISTS {}")
                .format(Identifier(keyspace, name))
                .text(),
                wait_seconds=120,
            )


class _Planner:
    """One plan: the checks first, then the statements in the order they run."""

    def __init__(self, copy: CassandraTableCopy, request: TableCopyRequest) -> None:
        self._copy = copy
        self._request = request
        self._keyspace = ""
        self._plan = TableCopyPlan()
        self._taken: set[str] = set()
        self._types_made: set[str] = set()
        self._types_there: set[str] = set()

    async def plan(self) -> TableCopyPlan:
        request = self._request
        if request.dialect != DIALECT:
            self._problem(None, say("These tables are described in another dialect"))
            return self._plan
        keyspace = _keyspace(request.place_node_id)
        place = await self._copy._inspector.keyspace(keyspace)
        profile = await self._copy._inspector.profile()
        if place is None:
            self._problem(None, say("That keyspace is no longer there"))
            return self._plan
        if place[1] or is_system_keyspace(keyspace, scylla=profile.scylla):
            self._problem(
                None, say('"{keyspace}" belongs to the server', keyspace=keyspace)
            )
            return self._plan
        self._keyspace = keyspace
        self._taken = await self._copy._taken(keyspace)
        self._types_there = {
            str(row["type_name"])
            for row in await self._copy._session.query(_TYPES, [keyspace])
        }
        self._names_ok()
        if self._plan.problems:
            return self._plan
        methods = {"": ""}
        for target in request.tables:
            self._table(target, methods)
        return self._plan

    def _names_ok(self) -> None:
        seen: set[str] = set()
        for target in self._request.tables:
            table = target.table
            if table.refusal is not None:
                self._problem(table.node_id, f"{table.label}: {table.refusal}")
                continue
            name = target.name
            if len(name) > NAME_LIMIT or _PLAIN.fullmatch(name) is None:
                self._problem(
                    table.node_id,
                    say(
                        "A table's name is letters, digits and underscores, starting with a "
                        "letter, at most {limit}",
                        limit=NAME_LIMIT,
                    ),
                )
            elif name in seen:
                self._problem(
                    table.node_id,
                    say("Two tables cannot both be called {name}", name=name),
                )
            elif name in self._taken:
                self._problem(
                    table.node_id,
                    say(
                        "{schema}.{name} is already there",
                        schema=self._keyspace,
                        name=name,
                    ),
                    kind="conflict",
                )
            seen.add(name)
        if len(self._request.tables) > MAX_COPIED_TABLES:
            self._problem(
                None,
                say("Copy at most {count} tables at a time", count=MAX_COPIED_TABLES),
            )

    def _table(self, target: TableCopyTarget, methods: dict[str, str]) -> None:
        table = target.table
        label = f"{self._keyspace}.{target.name}"
        for copied in table.types:
            if copied.name in self._types_there or copied.name in self._types_made:
                continue
            if _PLAIN.fullmatch(copied.name) is None or not all(
                _type_ok(attribute.type_sql) for attribute in copied.attributes
            ):
                self._problem(
                    table.node_id,
                    say(
                        "{label}: the type {name} could not be read",
                        label=table.label,
                        name=copied.name,
                    ),
                )
                return
            fields = ", ".join(
                f"{quoted_name(attribute.name)} {attribute.type_sql}"
                for attribute in copied.attributes
            )
            self._plan.statements.append(
                CopyStatement(
                    title=say("Create type {name}", name=copied.name),
                    sql=f"CREATE TYPE {quoted_name(self._keyspace, copied.name)} ({fields})",
                )
            )
            self._types_made.add(copied.name)
        parts: list[str] = []
        for column in table.columns:
            definition = column.definition or ""
            if not _type_ok(definition.removesuffix(" static")):
                self._problem(
                    table.node_id,
                    say(
                        "{label}: the type of {name} could not be read",
                        label=table.label,
                        name=column.name,
                    ),
                )
                return
            parts.append(f"{quoted_name(column.name)} {definition}")
        try:
            options = json.loads(table.options or "{}")
            key = str(options["key"])
            order = str(options.get("order") or "")
        except ValueError, KeyError, TypeError:
            self._problem(
                table.node_id,
                say("{label}: its key could not be read", label=table.label),
            )
            return
        if not _key_ok(key) or (order and not _order_ok(order)):
            self._problem(
                table.node_id,
                say("{label}: its key could not be read", label=table.label),
            )
            return
        parts.append(key)
        statement = (
            SQL("CREATE TABLE {} (\n  ")
            .format(Identifier(self._keyspace, target.name))
            .text()
            + ",\n  ".join(parts)
            + "\n)"
        )
        clauses = [order] if order else []
        if table.comment:
            clauses.append("comment = '" + table.comment.replace("'", "''") + "'")
        if clauses:
            statement += " WITH " + " AND ".join(clauses)
        self._plan.statements.append(
            CopyStatement(
                node_id=table.node_id,
                title=say("Create table {label}", label=label),
                sql=statement,
            )
        )
        for index in table.indexes:
            try:
                body = json.loads(index.body)
                indexed = str(body["target"])
                using = str(body.get("using") or "")
            except ValueError, KeyError, TypeError:
                indexed, using = "", ""
            known = {copied.name for copied in table.columns}
            plain = indexed.strip('"').replace('""', '"')
            if plain not in known or (using and _PLAIN_CLASS.fullmatch(using) is None):
                self._plan.warnings.append(
                    say(
                        "{label}: index {name} could not be read, and is not copied",
                        label=table.label,
                        name=index.name,
                    )
                )
                continue
            sql = (
                SQL("CREATE INDEX ON {} ({})")
                .format(Identifier(self._keyspace, target.name), Identifier(plain))
                .text()
            )
            if using:
                sql += f" USING '{using}'"
            self._plan.statements.append(
                CopyStatement(
                    node_id=table.node_id,
                    title=say("Index {name} of {label}", name=index.name, label=label),
                    sql=sql,
                    stage="after",
                )
            )
        if self._request.rows:
            self._plan.loads.append(
                CopyLoad(
                    node_id=table.node_id,
                    schema_name=self._keyspace,
                    name=target.name,
                    columns=[column.name for column in table.columns],
                )
            )

    def _problem(
        self,
        node_id: str | None,
        message: str,
        kind: Literal["invalid", "conflict"] = "invalid",
    ) -> None:
        self._plan.problems.append(
            CopyProblem(node_id=node_id, message=message, kind=kind)
        )


# A type as `system_schema` prints it: names, `<`, `>`, commas, spaces, digits.
_TYPE_TEXT = re.compile(r"[A-Za-z0-9_<>, ]+")
# `PRIMARY KEY ((a, b), c)` with quoted names.
_KEY_TEXT = re.compile(
    r'PRIMARY KEY \((?:"(?:[^"]|"")+"|\((?:"(?:[^"]|"")+"(?:, )?)+\))(?:, "(?:[^"]|"")+")*\)'
)
_ORDER_TEXT = re.compile(
    r'CLUSTERING ORDER BY \((?:"(?:[^"]|"")+" (?:ASC|DESC)(?:, )?)+\)'
)
_PLAIN_CLASS = re.compile(r"[A-Za-z0-9_.]+")


def _type_ok(text: str) -> bool:
    return _TYPE_TEXT.fullmatch(text) is not None


def _key_ok(text: str) -> bool:
    return _KEY_TEXT.fullmatch(text) is not None


def _order_ok(text: str) -> bool:
    return _ORDER_TEXT.fullmatch(text) is not None


def _keyspace(place_node_id: str) -> str:
    keyspace, relation = parse(place_node_id)
    if relation is not None:
        raise ValueError(say("Paste into a keyspace"))
    return keyspace


def _free(name: str, taken: set[str]) -> str:
    """The name, or the first `…_copy`, `…_copy_2` nothing holds."""
    if name not in taken:
        return name
    number = 1
    while True:
        suffix = "_copy" if number == 1 else f"_copy_{number}"
        candidate = name[: NAME_LIMIT - len(suffix)] + suffix
        if candidate not in taken:
            return candidate
        number += 1
