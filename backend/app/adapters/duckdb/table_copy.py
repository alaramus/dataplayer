"""Both ends of a copy of DuckDB tables with their structure (D182, D400).

The source describes a table from DuckDB's catalog: each column's type as
DuckDB spells it — an enum's labels included — its requirement, default and
generation, the keys and checks, the indexes' keys and the comments. Foreign
keys travel as links, because the window decides where each points. A
default that takes the next value of a sequence travels as an identity, and
the copy makes a sequence of its own for it (D397).

Rows travel as DuckDB's text and are cast back by the column's type, which is
exact for every type but a union (checked on 2.0.0). DuckDB checks a foreign
key at once and adds none to a table that exists, so the copy is one
transaction in which a table is made and filled after every table of the copy
it points at.
"""

import json
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

import duckdb

from app.adapters import database_ids as ids
from app.adapters.duckdb.design import NAME_LIMIT
from app.adapters.duckdb.inspection import RelationFacts, read_relation
from app.adapters.duckdb.query import redacted
from app.adapters.duckdb.relation_changes import DuckdbRelationChanges
from app.adapters.duckdb.session import DuckdbSession, Handle, Reading, classify
from app.adapters.duckdb.sql import SQL, Identifier, quoted_name
from app.adapters.duckdb.statements import sentence, tokens_of
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.table_copy import (
    MAX_COPIED_TABLES,
    Arrived,
    CopiedColumn,
    CopiedConstraint,
    CopiedIndex,
    CopiedLink,
    CopiedTable,
    CopyLoad,
    CopyProblem,
    CopyStatement,
    RowsOf,
    TableCopyPlan,
    TableCopyRequest,
    TableCopyTarget,
    is_one_fragment,
)
from app.core.translation import N_, say

DIALECT = "duckdb"
# Rows read from the source and written at the destination at a time.
READ_BATCH = 1000

# A default that is the next value of a sequence and nothing else.
_NEXTVAL = re.compile(r"nextval\('((?:[^']|'')+)'\)")

_SEQUENCES = """
SELECT schema_name, sequence_name, start_value, increment_by, last_value
FROM duckdb_sequences() WHERE database_name = current_database()
"""
_REFERENCING = """
SELECT DISTINCT table_name FROM duckdb_constraints()
WHERE database_name = current_database() AND constraint_type = 'FOREIGN KEY'
  AND schema_name = ? AND lower(referenced_table) = lower(?) AND lower(table_name) <> lower(?)
"""
# Every name of a schema: tables, views, indexes and sequences share them.
_TAKEN = """
SELECT lower(table_name) FROM duckdb_tables() WHERE database_name = current_database() AND schema_name = ?
UNION SELECT lower(view_name) FROM duckdb_views() WHERE database_name = current_database() AND schema_name = ?
UNION SELECT lower(index_name) FROM duckdb_indexes() WHERE database_name = current_database() AND schema_name = ?
UNION SELECT lower(sequence_name) FROM duckdb_sequences() WHERE database_name = current_database() AND schema_name = ?
"""

# What DuckDB refuses about the rows or the statements of a copy: said in its
# own sentence, which names the key, the column or the value.
_REFUSED = (
    duckdb.ConstraintException,
    duckdb.ConversionException,
    duckdb.CatalogException,
    duckdb.BinderException,
    duckdb.ParserException,
    duckdb.DependencyException,
    duckdb.NotImplementedException,
    duckdb.InvalidInputException,
)


def _index_body(text: str | None) -> str | None:
    """What follows `ON <table>` in a CREATE INDEX: the parenthesised keys."""
    if not text:
        return None
    tokens = [token for token in tokens_of(text) if token.kind != "comment"]
    on = next((at for at, token in enumerate(tokens) if token.text.upper() == "ON"), None)
    if on is None:
        return None
    opening = next((token for token in tokens[on + 1 :] if token.text == "("), None)
    if opening is None:
        return None
    body = text[opening.start :].strip().rstrip(";").strip()
    return body if is_one_fragment(body) else None


def _sequence_of(
    default: str | None, schema: str, sequences: dict[tuple[str, str], tuple[int, int, int | None]]
) -> tuple[int, int] | None:
    """Where an identity's sequence would go next, and its step, when the
    default is the next value of a sequence of the file and nothing else."""
    if default is None or (found := _NEXTVAL.fullmatch(default.strip())) is None:
        return None
    named = found.group(1).replace("''", "'")
    candidates = [(schema, named)]
    if "." in named:
        owner, _, bare = named.partition(".")
        candidates.append((owner.strip('"'), bare.strip('"')))
    for key in candidates:
        if key in sequences:
            start, step, last = sequences[key]
            return (start if last is None else last + step), step
    return None


def _describe(reading: Reading, node_id: str) -> CopiedTable:
    schema, name = ids.parse(node_id)
    if name is None:
        raise NodeNotFound(node_id)
    facts = read_relation(reading, schema, name)
    if facts is None:
        raise NodeNotFound(node_id)
    base = CopiedTable(node_id=node_id, schema_name=schema, name=facts.name)
    if facts.is_view:
        return base.model_copy(update={"refusal": say("only tables are copied with their structure")})
    unions = [column.name for column in facts.columns if "UNION(" in column.type.sql.upper()]
    if unions:
        return base.model_copy(
            update={
                "refusal": say(
                    "{name} is a union, whose text does not say which member it holds",
                    name=unions[0],
                )
            }
        )
    sequences = {
        (str(row[0]), str(row[1])): (int(row[2]), int(row[3]), None if row[4] is None else int(row[4]))
        for row in reading.tuples(_SEQUENCES)
    }
    referencing = [
        ids.relation_id(schema, str(row[0]))
        for row in reading.tuples(_REFERENCING, [schema, facts.name, facts.name])
    ]
    return base.model_copy(
        update={
            "comment": facts.comment,
            "columns": _columns(facts, sequences),
            "constraints": _constraints(facts),
            "indexes": [
                CopiedIndex(name=index.name, unique=index.unique, body=body)
                for index in facts.indexes
                if not index.primary and (body := _index_body(index.definition)) is not None
            ],
            "links": [
                CopiedLink(
                    name=key.name,
                    columns=key.columns,
                    target_node_id=ids.relation_id(schema, key.target_table or ""),
                    target_schema=schema,
                    target_name=key.target_table or "",
                    target_columns=key.target_columns or [],
                )
                for key in facts.foreign_keys
            ],
            "referenced_by": referencing,
            "row_estimate": facts.row_estimate,
        }
    )


def _columns(
    facts: RelationFacts, sequences: dict[tuple[str, str], tuple[int, int, int | None]]
) -> list[CopiedColumn]:
    columns: list[CopiedColumn] = []
    for column in facts.columns:
        identity = _sequence_of(column.default, facts.schema, sequences)
        columns.append(
            CopiedColumn(
                name=column.name,
                type_sql=column.type.sql,
                not_null=not column.nullable,
                default=None if identity is not None or column.generated is not None else column.default,
                identity="by_default" if identity is not None else None,
                identity_start=None if identity is None else identity[0],
                identity_increment=None if identity is None else identity[1],
                generated=column.generated,
                comment=column.comment,
            )
        )
    return columns


def _constraints(facts: RelationFacts) -> list[CopiedConstraint]:
    """The keys and checks; DuckDB names them itself, so a name only labels."""
    constraints = [
        CopiedConstraint(
            name=key.name,
            kind="primary_key" if key.kind == "PRIMARY KEY" else "unique",
            definition=("PRIMARY KEY" if key.kind == "PRIMARY KEY" else "UNIQUE")
            + f" ({', '.join(quoted_name(column) for column in key.columns)})",
        )
        for key in facts.keys
        if key.kind in ("PRIMARY KEY", "UNIQUE")
    ]
    constraints += [
        CopiedConstraint(name=check.name, kind="check", definition=f"CHECK ({check.expression})")
        for check in facts.checks
    ]
    return constraints


def _refused(failure: duckdb.Error, home_of: Callable[[str], str]) -> str:
    """What DuckDB refused, in its own sentence, as D394 says it."""
    if isinstance(failure, _REFUSED):
        said = home_of(sentence(str(failure)))
        return said[:1].lower() + said[1:]
    error_kind, message = classify(failure, fallback_message=N_("The copy failed"))
    raise AdapterError(error_kind, message) from None


@dataclass
class _Rows:
    handle: Handle

    def rows(self, node_id: str, columns: list[str]) -> AsyncIterator[bytes]:
        return self._read(node_id, columns)

    async def _read(self, node_id: str, columns: list[str]) -> AsyncIterator[bytes]:
        schema, name = ids.parse(node_id)
        if name is None:
            raise NodeNotFound(node_id)
        statement = (
            SQL("SELECT {} FROM {}")
            .format(
                SQL(", ").join(SQL("CAST({} AS VARCHAR)").format(Identifier(column)) for column in columns),
                Identifier(schema, name),
            )
            .text()
        )
        cursor = await self.handle.call(lambda connection: connection.execute(statement))
        while batch := await self.handle.call(lambda _connection: cursor.fetchmany(READ_BATCH)):
            yield b"".join(json.dumps(list(row), ensure_ascii=False).encode() + b"\n" for row in batch)


class DuckdbTableCopy:
    """Both ends of a copy of DuckDB tables."""

    table_copy_dialect = DIALECT

    def __init__(self, session: DuckdbSession, relations: DuckdbRelationChanges) -> None:
        self._session = session
        self._relations = relations

    @property
    def table_copy_database(self) -> str:
        """The file, by where it is on this server's disk: two connections to
        one file are one database, and a link may keep its original there."""
        return f"duckdb:{self._session.place()}"

    # The source's half.

    async def describe_for_copy(self, node_ids: list[str]) -> list[CopiedTable]:
        return await self._session.inspection(
            lambda reading: [_describe(reading, node_id) for node_id in node_ids]
        )

    @asynccontextmanager
    async def reading_tables(self) -> AsyncIterator[_Rows]:
        """Every table read in one transaction, so in one state of the file."""
        handle = await self._session.handle()
        try:
            await handle.call(lambda connection: connection.execute("BEGIN TRANSACTION READ ONLY"))
            yield _Rows(handle)
        finally:
            await handle.close()

    # The destination's half.

    async def free_table_names(self, place_node_id: str, wanted: list[str]) -> list[str]:
        taken = await self._taken(ids.parse(place_node_id)[0])
        free: list[str] = []
        for name in wanted:
            chosen = _free(name, taken)
            taken.add(chosen.lower())
            free.append(chosen)
        return free

    async def plan_table_copy(self, request: TableCopyRequest) -> TableCopyPlan:
        return await _Planner(self, request).plan()

    async def carry_table_copy(self, request: TableCopyRequest, rows_of: RowsOf, arrived: Arrived) -> None:
        plan = await self.plan_table_copy(request)
        if plan.problems:
            raise ValueError(plan.problems[0].message)
        types = {
            target.table.node_id: {column.name: column.type_sql for column in target.table.columns}
            for target in request.tables
        }
        step = say("Preparing the copy")
        handle = await self._session.handle()
        try:
            await handle.call(lambda connection: connection.execute("BEGIN"))
            for statement in plan.statements:
                if statement.stage == "before":
                    step = statement.title
                    await _run(handle, statement.sql)
            for load in plan.loads:
                step = say("Rows of {table}", table=load.target_label)
                if request.same_database:
                    await _insert_in_place(handle, load, arrived)
                else:
                    await _insert(handle, load, types[load.node_id], rows_of, arrived)
            for statement in plan.statements:
                if statement.stage == "after":
                    step = statement.title
                    await _run(handle, statement.sql)
            await handle.call(lambda connection: connection.execute("COMMIT"))
        except duckdb.Error as failure:
            # Closing rolls back: nothing of the copy is left in the file.
            raise ValueError(f"{step}: {_refused(failure, self._home)}") from None
        finally:
            await handle.close()

    def _home(self, text: str) -> str:
        return redacted(text, self._session.home)

    async def _taken(self, schema: str) -> set[str]:
        return await self._session.inspection(
            lambda reading: {str(row[0]) for row in reading.tuples(_TAKEN, [schema] * 4)}
        )


async def _run(handle: Handle, statement: str) -> None:
    await handle.call(lambda connection: connection.execute(statement))


async def _insert_in_place(handle: Handle, load: CopyLoad, arrived: Arrived) -> None:
    """The rows of a table in the same file, copied by the file itself."""
    schema, name = ids.parse(load.node_id)
    if name is None:
        raise NodeNotFound(load.node_id)
    columns = SQL(", ").join(Identifier(column) for column in load.columns)
    statement = (
        SQL("INSERT INTO {} ({}) SELECT {} FROM {}")
        .format(Identifier(load.schema_name, load.name), columns, columns, Identifier(schema, name))
        .text()
    )
    row = await handle.call(lambda connection: connection.execute(statement).fetchone())
    await arrived(load, 0 if row is None else int(row[0]), 0)


def _many(statement: str, rows: list[list[str | None]]) -> Callable[[duckdb.DuckDBPyConnection], object]:
    return lambda connection: connection.executemany(statement, rows)


async def _insert(
    handle: Handle, load: CopyLoad, types: dict[str, str], rows_of: RowsOf, arrived: Arrived
) -> None:
    """The rows of one table, a chunk of lines at a time, each value cast
    back from its text by the column's type."""
    head = SQL("INSERT INTO {} ({}) VALUES ").format(
        Identifier(load.schema_name, load.name),
        SQL(", ").join(Identifier(column) for column in load.columns),
    )
    # A type as DuckDB's catalog spells it, checked to be one fragment.
    casts = ", ".join(f"CAST(? AS {types[column]})" for column in load.columns)
    statement = f"{head.text()}({casts})"  # noqa: S608 — names quoted, types checked
    count = 0
    size = 0
    async for chunk in rows_of(load):
        rows = [json.loads(line) for line in chunk.splitlines() if line]
        if rows:
            await handle.call(_many(statement, rows))
        count += len(rows)
        size += len(chunk)
        await arrived(load, count, size)


class _Planner:
    """One plan: the checks first, then the statements in the order they run."""

    def __init__(self, copy: DuckdbTableCopy, request: TableCopyRequest) -> None:
        self._copy = copy
        self._request = request
        self._plan = TableCopyPlan()
        self._schema = ids.parse(request.place_node_id)[0]
        # Every name of the schema, in lower case: DuckDB compares names
        # without case, and tables, indexes and sequences share them.
        self._taken: set[str] = set()

    async def plan(self) -> TableCopyPlan:
        request = self._request
        if request.dialect != DIALECT:
            self._problem(None, say("These tables are described in another dialect"))
            return self._plan
        if not await self._place_ok():
            return self._plan
        self._taken = await self._copy._taken(self._schema)
        self._names_ok()
        if self._plan.problems:
            return self._plan
        new_names = {target.table.node_id: target.name for target in request.tables}
        for target in _parents_first(request.tables, new_names):
            self._table(target, new_names)
        return self._plan

    async def _place_ok(self) -> bool:
        try:
            options = await self._copy._relations.new_relation_options(self._request.place_node_id)
        except NodeNotFound:
            self._problem(None, say("That schema is no longer there"))
            return False
        if not options.supported:
            self._problem(None, options.reason or say("Tables cannot be made here"))
            return False
        return True

    def _names_ok(self) -> None:
        seen: set[str] = set()
        for target in self._request.tables:
            table = target.table
            if table.refusal is not None:
                self._problem(table.node_id, f"{table.label}: {table.refusal}")
                continue
            name = target.name
            if name == "" or name != name.strip() or len(name) > NAME_LIMIT:
                self._problem(
                    table.node_id,
                    say(
                        "A DuckDB name is 1 to {limit} characters and does not start or end with spaces",
                        limit=NAME_LIMIT,
                    ),
                )
            elif name.lower() in seen:
                self._problem(table.node_id, say("Two tables cannot both be called {name}", name=name))
            elif name.lower() in self._taken:
                self._problem(
                    table.node_id,
                    say("{schema}.{name} is already there", schema=self._schema, name=name),
                    kind="conflict",
                )
            seen.add(name.lower())
        self._taken |= seen
        if len(self._request.tables) > MAX_COPIED_TABLES:
            self._problem(None, say("Copy at most {count} tables at a time", count=MAX_COPIED_TABLES))

    def _table(self, target: TableCopyTarget, new_names: dict[str, str]) -> None:
        table = target.table
        label = f"{self._schema}.{target.name}"
        parts: list[str] = []
        for column in table.columns:
            if not is_one_fragment(column.type_sql):
                self._problem(
                    table.node_id,
                    say("{label}: the type of {name} could not be read", label=table.label, name=column.name),
                )
                return
            line = f"{quoted_name(column.name)} {column.type_sql}"
            if column.identity is not None:
                sequence = self._free_name(f"{target.name}_{column.name}_seq")
                self._plan.statements.append(
                    CopyStatement(
                        node_id=table.node_id,
                        title=say("Sequence {name}", name=sequence),
                        sql=(
                            f"CREATE SEQUENCE {quoted_name(self._schema, sequence)} "
                            f"START {column.identity_start or 1} INCREMENT BY {column.identity_increment or 1}"
                        ),
                    )
                )
                # nextval takes the sequence's name as a string.
                qualified = quoted_name(self._schema, sequence).replace("'", "''")
                line += f" DEFAULT nextval('{qualified}')"
            elif column.default is not None:
                if is_one_fragment(column.default):
                    line += f" DEFAULT {column.default}"
                else:
                    self._warn(
                        say(
                            "{label}: the default of {name} could not be read, and is not copied",
                            label=table.label,
                            name=column.name,
                        )
                    )
            if column.generated is not None:
                if not is_one_fragment(column.generated):
                    self._problem(
                        table.node_id,
                        say("{label}: the type of {name} could not be read", label=table.label, name=column.name),
                    )
                    return
                line += f" GENERATED ALWAYS AS ({column.generated}) VIRTUAL"
            elif column.not_null:
                line += " NOT NULL"
            parts.append(line)
        for constraint in table.constraints:
            if constraint.kind == "check" and not is_one_fragment(constraint.definition):
                self._warn(
                    say(
                        "{label}: {name} could not be read, and is not copied",
                        label=table.label,
                        name=constraint.name,
                    )
                )
                continue
            parts.append(constraint.definition)
        parts.extend(
            key for link in table.links if (key := self._link(target, link, new_names)) is not None
        )
        self._plan.statements.append(
            CopyStatement(
                node_id=table.node_id,
                title=say("Create table {label}", label=label),
                # A part to a line: the statement is reviewed before it runs.
                sql=f"CREATE TABLE {quoted_name(self._schema, target.name)} (\n  " + ",\n  ".join(parts) + "\n)",
            )
        )
        for index in table.indexes:
            name = self._index_name(index.name, table.name, target.name)
            self._plan.statements.append(
                CopyStatement(
                    node_id=table.node_id,
                    title=say("Index {name}", name=name),
                    sql=(
                        f"CREATE {'UNIQUE ' if index.unique else ''}INDEX {quoted_name(name)} "
                        f"ON {quoted_name(self._schema, target.name)} {index.body}"
                    ),
                    stage="after",
                )
            )
        if table.comment:
            self._comment(table.node_id, f"TABLE {quoted_name(self._schema, target.name)}", table.comment)
        for column in table.columns:
            if column.comment:
                self._comment(
                    table.node_id,
                    f"COLUMN {quoted_name(self._schema, target.name, column.name)}",
                    column.comment,
                )
        if self._request.rows:
            self._plan.loads.append(
                CopyLoad(
                    node_id=table.node_id,
                    schema_name=self._schema,
                    name=target.name,
                    columns=[column.name for column in table.columns if column.generated is None],
                )
            )

    def _comment(self, node_id: str, subject: str, text: str) -> None:
        literal = "'" + text.replace("'", "''") + "'"
        self._plan.statements.append(
            CopyStatement(
                node_id=node_id,
                title=say("Comment on {subject}", subject=subject),
                sql=f"COMMENT ON {subject} IS {literal}",
                stage="after",
            )
        )

    def _link(self, target: TableCopyTarget, link: CopiedLink, new_names: dict[str, str]) -> str | None:
        decision = target.links.get(link.name, "drop")
        if decision == "drop":
            return None
        if decision == "copy":
            points_at = new_names.get(link.target_node_id)
            if points_at is None:
                return None
        # A key reaches no other schema (D389).
        elif self._request.same_database and link.target_schema == self._schema:
            points_at = link.target_name
        else:
            self._warn(
                say(
                    "{label}: {name} cannot point into another schema, and is not copied",
                    label=target.table.label,
                    name=link.name,
                )
            )
            return None
        return (
            f"FOREIGN KEY ({', '.join(quoted_name(one) for one in link.columns)}) "
            f"REFERENCES {quoted_name(points_at)} ({', '.join(quoted_name(one) for one in link.target_columns)})"
        )

    def _index_name(self, name: str, old: str, new: str) -> str:
        """An index named after its table, named after the copy, and free in
        the schema: an index's name is the schema's, not its table's."""
        renamed = new + name[len(old) :] if name.lower().startswith(old.lower()) and old != new else name
        return self._free_name(renamed, suffix="")

    def _free_name(self, name: str, *, suffix: str = "") -> str:
        chosen = _free(name, self._taken, suffix=suffix)
        self._taken.add(chosen.lower())
        return chosen

    def _problem(
        self, node_id: str | None, message: str, kind: Literal["invalid", "conflict"] = "invalid"
    ) -> None:
        self._plan.problems.append(CopyProblem(node_id=node_id, message=message, kind=kind))

    def _warn(self, message: str) -> None:
        self._plan.warnings.append(message)


def _parents_first(tables: list[TableCopyTarget], new_names: dict[str, str]) -> list[TableCopyTarget]:
    """The tables in an order where one comes after every table of the copy
    its kept links point at: DuckDB checks a key at once, against a table that
    must exist. A cycle cannot be made in DuckDB, so none is copied."""
    by_id = {target.table.node_id: target for target in tables}
    waiting = {
        target.table.node_id: {
            link.target_node_id
            for link in target.table.links
            if target.links.get(link.name, "drop") == "copy"
            and link.target_node_id in new_names
            and link.target_node_id != target.table.node_id
        }
        for target in tables
    }
    ordered: list[TableCopyTarget] = []
    while waiting:
        ready = [node_id for node_id, parents in waiting.items() if not parents & waiting.keys()]
        for node_id in ready or list(waiting):
            ordered.append(by_id[node_id])
            waiting.pop(node_id)
    return ordered


def _free(name: str, taken: set[str], *, suffix: str = "_copy") -> str:
    """The name, or the first `…_copy`, `…_copy_2` the schema has nothing by."""
    if name.lower() not in taken:
        return name
    number = 1
    while True:
        candidate = f"{name}{suffix}" if number == 1 and suffix else f"{name}{suffix}_{number}"
        if candidate.lower() not in taken:
            return candidate
        number += 1
