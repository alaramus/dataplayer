"""Both ends of a copy of SQLite tables with their structure (D182, D259).

The source describes a table in the words of its own CREATE TABLE text: each
column's definition as written without the foreign keys inside it, its table
constraints, its indexes and its options. That keeps what the catalog has no
word for — AUTOINCREMENT, a conflict clause, a collation — as D255 keeps it.
Foreign keys travel as links, because the window decides where each points.

SQLite's structure changes are transactional (D253), so the copy is one
transaction: the tables, their rows and their indexes are committed together
or not at all. SQLite adds no foreign key to a table that exists, so the links
are written into each CREATE TABLE and checked at the commit, once every row
has arrived. The rows travel as JSON lines of values tagged with their class,
so an integer, a real, text and a blob each arrive as what they were; inside
one file, the file copies them itself.
"""

import json
import sqlite3
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.relation import RefAction
from app.adapters.sqlite import ids
from app.adapters.sqlite.definition import (
    ClauseKind,
    fragment,
    options_of,
    read_table,
    stands_alone,
    tokenize,
)
from app.adapters.sqlite.design import NAME_LIMIT
from app.adapters.sqlite.inspection import (
    SCHEMA,
    RelationFacts,
    is_system_relation,
    read_relation,
)
from app.adapters.sqlite.relation_changes import SqliteRelationChanges
from app.adapters.sqlite.restructure import constraint_names
from app.adapters.sqlite.rows import Stored, tagged, untagged
from app.adapters.sqlite.session import (
    Handle,
    Reading,
    SqliteSession,
    Undecodable,
    classify,
    sentence,
)
from app.adapters.sqlite.sql import SQL, Identifier, quoted_name
from app.adapters.sqlite.update import CONSTRAINT_DATATYPE
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
)
from app.core.translation import N_, say

DIALECT = "sqlite"
# Rows read from the source and written at the destination at a time.
READ_BATCH = 1000

COPY_REFUSALS: dict[int, str] = {
    sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY: N_(
        "Some rows point at rows that were not copied"
    ),
    sqlite3.SQLITE_CONSTRAINT_UNIQUE: N_("Two rows have the same key"),
    sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY: N_("Two rows have the same key"),
    sqlite3.SQLITE_CONSTRAINT_NOTNULL: N_("A required value is missing"),
    sqlite3.SQLITE_CONSTRAINT_CHECK: N_("A row breaks a check of the table"),
    CONSTRAINT_DATATYPE: N_("A row holds a value its column's type does not take"),
}

_TRIGGERS = "SELECT count(*) FROM sqlite_schema WHERE type = 'trigger' AND tbl_name = ?"
_REFERENCING = """
SELECT DISTINCT m.name FROM sqlite_schema AS m, pragma_foreign_key_list(m.name, 'main') AS k
WHERE m.type = 'table' AND k."table" = ? COLLATE NOCASE
"""
_TAKEN = "SELECT lower(name) FROM sqlite_schema"

_REF_SQL: dict[RefAction, str] = {
    "no_action": "NO ACTION",
    "restrict": "RESTRICT",
    "cascade": "CASCADE",
    "set_null": "SET NULL",
    "set_default": "SET DEFAULT",
}
_KINDS: dict[ClauseKind, Literal["primary_key", "unique", "check"]] = {
    "primary": "primary_key",
    "unique": "unique",
    "check": "check",
}


def _index_body(text: str) -> str | None:
    """What follows `ON <table>` in a CREATE INDEX: the keys and any WHERE."""
    tokens = tokenize(text)
    on = next(
        (index for index, token in enumerate(tokens) if token.is_word("ON")), None
    )
    if on is None:
        return None
    at = on + 2
    if at < len(tokens) and tokens[at].value == ".":
        at += 2
    return fragment(text, tokens[at].start, len(text)) if at < len(tokens) else None


def _columns(facts: RelationFacts) -> list[CopiedColumn]:
    text = read_table(facts.text)
    columns: list[CopiedColumn] = []
    for column in facts.columns:
        said = text.columns.get(column.name.lower())
        definition = None
        if said is not None:
            start, end = text.items[said.item]
            after_name = tokenize(text.text[start:end])[0].end + start
            foreign = [
                clause.span for clause in said.clauses if clause.kind == "foreign"
            ]
            definition = fragment(text.text, after_name, end, foreign)
        columns.append(
            CopiedColumn(
                name=column.name,
                type_sql=column.type.sql,
                not_null=not column.nullable,
                identity="by_default" if column.rowid_alias else None,
                generated=column.generated,
                definition=definition,
            )
        )
    return columns


def _constraints(facts: RelationFacts) -> list[CopiedConstraint]:
    text = read_table(facts.text)
    shown = {id(clause): name for name, clause in constraint_names(text).items()}
    return [
        CopiedConstraint(
            name=shown.get(id(clause), clause.kind),
            kind=_KINDS[clause.kind],
            definition=fragment(text.text, *text.items[clause.item]),
        )
        for clause in text.constraints
        if not clause.inline and clause.kind in _KINDS
    ]


def _describe(reading: Reading, node_id: str) -> CopiedTable:
    schema, name = ids.parse(node_id)
    if schema != SCHEMA or name is None:
        raise NodeNotFound(node_id)
    facts = read_relation(reading, name)
    if facts is None:
        raise NodeNotFound(node_id)
    base = CopiedTable(node_id=node_id, schema_name=SCHEMA, name=facts.name)
    if is_system_relation(facts.name, facts.type):
        return base.model_copy(
            update={"refusal": say('"{name}" belongs to SQLite', name=facts.name)}
        )
    if facts.type != "table" or not facts.text:
        return base.model_copy(
            update={"refusal": say("only tables are copied with their structure")}
        )
    indexes = [
        CopiedIndex(name=index.name, unique=index.unique, body=body)
        for index in facts.indexes
        if index.origin == "c" and (body := _index_body(index.definition)) is not None
    ]
    links = [
        CopiedLink(
            name=key.name,
            columns=key.columns,
            target_node_id=ids.relation_id(key.target_table or ""),
            target_schema=SCHEMA,
            target_name=key.target_table or "",
            target_columns=key.target_columns,
            on_update=key.on_update,
            on_delete=key.on_delete,
        )
        for key in facts.foreign_keys
    ]
    triggers = int(reading.value(_TRIGGERS, (facts.name,)) or 0)
    referencing = [
        ids.relation_id(str(row[0]))
        for row in reading.tuples(_REFERENCING, (facts.name,))
        if str(row[0]).lower() != facts.name.lower()
    ]
    return base.model_copy(
        update={
            "columns": _columns(facts),
            "constraints": _constraints(facts),
            "indexes": indexes,
            "links": links,
            "referenced_by": referencing,
            "left_behind": (
                []
                if not triggers
                else [
                    say("1 trigger")
                    if triggers == 1
                    else say("{count} triggers", count=triggers)
                ]
            ),
            "row_estimate": facts.row_estimate,
            "options": options_of(facts.text),
        }
    )


class SqliteTableCopy:
    """Both ends of a copy of SQLite tables."""

    table_copy_dialect = DIALECT

    def __init__(
        self, session: SqliteSession, relations: SqliteRelationChanges
    ) -> None:
        self._session = session
        self._relations = relations

    @property
    def table_copy_database(self) -> str:
        """The file, by where it is on this server's disk: two connections to
        one file are one database, and a link may keep its original there."""
        return f"sqlite:{self._session.place()}"

    # The source's half.

    async def describe_for_copy(self, node_ids: list[str]) -> list[CopiedTable]:
        return await self._session.inspection(
            lambda reading: [_describe(reading, node_id) for node_id in node_ids]
        )

    @asynccontextmanager
    async def reading_tables(self) -> AsyncIterator[_Rows]:
        """Every table read in one transaction, so in one state of the file."""
        async with self._session.transaction(writes=False) as handle:
            yield _Rows(handle)

    # The destination's half.

    async def free_table_names(
        self, place_node_id: str, wanted: list[str]
    ) -> list[str]:
        taken = await self._taken()
        free: list[str] = []
        for name in wanted:
            chosen = _free(name, taken)
            taken.add(chosen.lower())
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
        step = say("Preparing the copy")
        try:
            async with self._session.transaction(writes=True) as handle:
                for statement in plan.statements:
                    if statement.stage == "before":
                        step = statement.title
                        await _run(handle, statement.sql)
                for load in plan.loads:
                    step = say("Rows of {table}", table=load.target_label)
                    if request.same_database:
                        await _insert_in_place(handle, load, arrived)
                    else:
                        await _insert(handle, load, rows_of, arrived)
                for statement in plan.statements:
                    if statement.stage == "after":
                        step = statement.title
                        await _run(handle, statement.sql)
                # Deferred, the foreign keys are checked by the commit.
                step = say("Checking the links")
        except sqlite3.Error as failure:
            # Rolled back: nothing of the copy is left in the file.
            raise ValueError(f"{step}: {_refused(failure)}") from None

    async def _taken(self) -> set[str]:
        return await self._session.inspection(
            lambda reading: {str(row[0]) for row in reading.tuples(_TAKEN)}
        )


async def _insert_in_place(handle: Handle, load: CopyLoad, arrived: Arrived) -> None:
    """The rows of a table in the same file, copied by the file itself.

    Streamed, they would be read under a lock the commit has to wait for:
    in a file without a write-ahead log a reader keeps a writer from
    committing, and here both are this one copy.
    """
    _schema, name = ids.parse(load.node_id)
    if name is None:
        raise NodeNotFound(load.node_id)
    columns = SQL(", ").join(Identifier(column) for column in load.columns)
    statement = (
        SQL("INSERT INTO {} ({}) SELECT {} FROM {}")
        .format(
            Identifier(SCHEMA, load.name), columns, columns, Identifier(SCHEMA, name)
        )
        .text()
    )
    count = await handle.call(lambda connection: connection.execute(statement).rowcount)
    await arrived(load, count, 0)


async def _run(handle: Handle, statement: str) -> None:
    await handle.call(lambda connection: connection.execute(statement))


def _refused(failure: sqlite3.Error) -> str:
    """What SQLite refused, by its result code where the copy has a sentence
    for it, and in SQLite's own sentence otherwise, as D253 says it."""
    extended = getattr(failure, "sqlite_errorcode", None) or 0
    named = COPY_REFUSALS.get(extended)
    if named is not None:
        return say(named)
    if extended & 0xFF in (sqlite3.SQLITE_ERROR, sqlite3.SQLITE_CONSTRAINT):
        said = sentence(str(failure))
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
        if schema != SCHEMA or name is None:
            raise NodeNotFound(node_id)
        statement = (
            SQL("SELECT {} FROM {}")
            .format(
                SQL(", ").join(Identifier(column) for column in columns),
                Identifier(SCHEMA, name),
            )
            .text()
        )
        cursor = await self.handle.call(
            lambda connection: connection.execute(statement)
        )
        while batch := await self.handle.call(
            lambda _connection: cursor.fetchmany(READ_BATCH)
        ):
            yield b"".join(
                json.dumps(
                    [tagged(value) for value in row], ensure_ascii=False
                ).encode()
                + b"\n"
                for row in batch
            )


def _many(
    statement: str, rows: list[tuple[Stored, ...]]
) -> Callable[[sqlite3.Connection], object]:
    return lambda connection: connection.executemany(statement, rows)


async def _insert(
    handle: Handle, load: CopyLoad, rows_of: RowsOf, arrived: Arrived
) -> None:
    """The rows of one table, a chunk of lines at a time.

    sqlite3 binds bytes as a blob, so text stored in no encoding is written
    through a CAST, by a statement of its own for the rows that hold some.
    """
    head = (
        SQL("INSERT INTO {} ({}) VALUES ")
        .format(
            Identifier(SCHEMA, load.name),
            SQL(", ").join(Identifier(column) for column in load.columns),
        )
        .text()
    )
    statements: dict[tuple[bool, ...], str] = {}
    count = 0
    size = 0
    async for chunk in rows_of(load):
        # Runs of rows alike, in their order: a table without a key of its
        # own numbers its rows in the order they arrive.
        runs: list[tuple[tuple[bool, ...], list[tuple[Stored, ...]]]] = []
        for line in chunk.splitlines():
            if line:
                row = tuple(untagged(item) for item in json.loads(line))
                texts = tuple(isinstance(value, Undecodable) for value in row)
                if not runs or runs[-1][0] != texts:
                    runs.append((texts, []))
                runs[-1][1].append(row)
        for texts, rows in runs:
            statement = statements.setdefault(
                texts,
                head
                + "("
                + ", ".join("CAST(? AS TEXT)" if text else "?" for text in texts)
                + ")",
            )
            await handle.call(_many(statement, rows))
            count += len(rows)
        size += len(chunk)
        await arrived(load, count, size)


class _Planner:
    """One plan: the checks first, then the statements in the order they run."""

    def __init__(self, copy: SqliteTableCopy, request: TableCopyRequest) -> None:
        self._copy = copy
        self._request = request
        self._plan = TableCopyPlan()
        # Every name in the file, in lower case: tables and indexes share one
        # namespace, and SQLite compares names without case.
        self._taken: set[str] = set()

    async def plan(self) -> TableCopyPlan:
        request = self._request
        if request.dialect != DIALECT:
            self._problem(None, say("These tables are described in another dialect"))
            return self._plan
        if not await self._place_ok():
            return self._plan
        self._taken = await self._copy._taken()
        self._names_ok()
        if self._plan.problems:
            return self._plan
        new_names = {target.table.node_id: target.name for target in request.tables}
        for target in request.tables:
            self._table(target, new_names)
        return self._plan

    async def _place_ok(self) -> bool:
        try:
            options = await self._copy._relations.new_relation_options(
                self._request.place_node_id
            )
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
                        "A SQLite name is 1 to {limit} characters and does not start or end with spaces",
                        limit=NAME_LIMIT,
                    ),
                )
            elif name.lower().startswith("sqlite_"):
                self._problem(
                    table.node_id, say('A name starting "sqlite_" is SQLite\'s own')
                )
            elif name.lower() in seen:
                self._problem(
                    table.node_id,
                    say("Two tables cannot both be called {name}", name=name),
                )
            elif name.lower() in self._taken:
                self._problem(
                    table.node_id,
                    say("{schema}.{name} is already there", schema=SCHEMA, name=name),
                    kind="conflict",
                )
            seen.add(name.lower())
        self._taken |= seen
        if len(self._request.tables) > MAX_COPIED_TABLES:
            self._problem(
                None,
                say("Copy at most {count} tables at a time", count=MAX_COPIED_TABLES),
            )

    def _table(self, target: TableCopyTarget, new_names: dict[str, str]) -> None:
        table = target.table
        parts: list[str] = []
        for column in table.columns:
            # A column may have no type at all, and then nothing after its name.
            if column.definition is None or (
                column.definition != "" and not stands_alone(column.definition)
            ):
                self._problem(
                    table.node_id,
                    say(
                        "{label}: the type of {name} could not be read",
                        label=table.label,
                        name=column.name,
                    ),
                )
                return
            parts.append(f"{quoted_name(column.name)} {column.definition}".rstrip())
        for constraint in table.constraints:
            # A constraint's name is its table's own here, so it is kept.
            if not stands_alone(constraint.definition):
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
            line
            for link in table.links
            if (line := self._link(target, link, new_names)) is not None
        )
        options = table.options or ""
        if options and not stands_alone(options):
            self._warn(
                say(
                    "{label}: its options could not be read, and are not copied",
                    label=table.label,
                )
            )
            options = ""
        self._plan.statements.append(
            CopyStatement(
                node_id=table.node_id,
                title=say("Create table {label}", label=f"{SCHEMA}.{target.name}"),
                # A part to a line: the statement is reviewed before it runs.
                sql=(
                    f"CREATE TABLE {quoted_name(SCHEMA, target.name)} (\n  "
                    + ",\n  ".join(parts)
                    + "\n)"
                    + (f" {options}" if options else "")
                ),
            )
        )
        for index in table.indexes:
            if not stands_alone(index.body):
                self._warn(
                    say(
                        "{label}: index {name} could not be read, and is not copied",
                        label=table.label,
                        name=index.name,
                    )
                )
                continue
            name = self._index_name(index.name, table.name, target.name)
            self._plan.statements.append(
                CopyStatement(
                    node_id=table.node_id,
                    title=say("Index {name}", name=name),
                    sql=(
                        f"CREATE {'UNIQUE ' if index.unique else ''}INDEX {quoted_name(SCHEMA, name)} "
                        f"ON {quoted_name(target.name)} {index.body}"
                    ),
                    stage="after",
                )
            )
        if self._request.rows:
            self._plan.loads.append(
                CopyLoad(
                    node_id=table.node_id,
                    schema_name=SCHEMA,
                    name=target.name,
                    columns=[
                        column.name
                        for column in table.columns
                        if column.generated is None
                    ],
                )
            )

    def _link(
        self, target: TableCopyTarget, link: CopiedLink, new_names: dict[str, str]
    ) -> str | None:
        decision = target.links.get(link.name, "drop")
        if decision == "drop":
            return None
        if decision == "copy":
            points_at = new_names.get(link.target_node_id)
            if points_at is None:
                return None
        elif self._request.same_database:
            points_at = link.target_name
        else:
            return None
        # An unnamed key is shown by its columns (D249) and stays unnamed.
        head = (
            ""
            if link.name.startswith("FOREIGN KEY (")
            else f"CONSTRAINT {quoted_name(link.name)} "
        )
        return (
            f"{head}FOREIGN KEY ({', '.join(quoted_name(one) for one in link.columns)}) "
            f"REFERENCES {quoted_name(points_at)} ({', '.join(quoted_name(one) for one in link.target_columns)}) "
            f"ON UPDATE {_REF_SQL[link.on_update]} ON DELETE {_REF_SQL[link.on_delete]}"
        )

    def _index_name(self, name: str, old: str, new: str) -> str:
        """An index named after its table, named after the copy, and free in
        the file: an index's name is the schema's, not its table's."""
        renamed = (
            new + name[len(old) :]
            if name.lower().startswith(old.lower()) and old != new
            else name
        )
        chosen = _free(renamed, self._taken, suffix="")
        self._taken.add(chosen.lower())
        return chosen

    def _problem(
        self,
        node_id: str | None,
        message: str,
        kind: Literal["invalid", "conflict"] = "invalid",
    ) -> None:
        self._plan.problems.append(
            CopyProblem(node_id=node_id, message=message, kind=kind)
        )

    def _warn(self, message: str) -> None:
        self._plan.warnings.append(message)


def _free(name: str, taken: set[str], *, suffix: str = "_copy") -> str:
    """The name, or the first `…_copy`, `…_copy_2` the file has nothing by."""
    if name.lower() not in taken:
        return name
    number = 1
    while True:
        candidate = (
            f"{name}{suffix}" if number == 1 and suffix else f"{name}{suffix}_{number}"
        )
        if candidate.lower() not in taken:
            return candidate
        number += 1
