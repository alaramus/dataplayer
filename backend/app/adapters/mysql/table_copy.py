"""Both ends of a copy of MySQL tables with their structure (D182, D239).

The source describes a table in the lines `SHOW CREATE TABLE` prints: each
column's definition whole, its keys and indexes, its checks and its options.
That is the only description that keeps everything — ON UPDATE, a character
set, a prefix length, a functional key — and the destination, which speaks the
same dialect, composes its own CREATE TABLE from those lines after checking
that each is one part of a statement and nothing more. Foreign keys travel as
links, because the window decides where each one points.

MySQL commits CREATE TABLE by itself (D233), so the copy is not one
transaction: the rows arrive in one, and if anything fails or is stopped, the
tables this copy made are dropped again.

There is no COPY. The rows travel as JSON lines of text: what the server
prints for a value, which it reads back the same, binary values and shapes as
hexadecimal of the bytes the server keeps, and a BIT as its number.
"""

import json
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

import aiomysql

from app.adapters.mysql import ids
from app.adapters.mysql.catalog import is_system_database
from app.adapters.mysql.definitions import parse, stands_alone
from app.adapters.mysql.inspection import VIEW_TYPES, read_relation
from app.adapters.mysql.relation_changes import MysqlRelationChanges
from app.adapters.mysql.session import MysqlSession, quoted_name
from app.adapters.mysql.sql import SQL, Composable, Identifier
from app.adapters.protocol import NodeNotFound
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

DIALECT = "mysql"
NAME_LIMIT = 64

# Rows read from the source at a time, and how much one INSERT may carry.
READ_BATCH = 500
INSERT_BYTES = 1024 * 1024

COPY_REFUSALS: dict[int, str] = {
    1005: N_("This server cannot make the table as described"),
    1044: N_("This connection may not create a table in that database"),
    1050: N_("Something with that name is already there"),
    1062: N_("Two rows have the same key"),
    1064: N_("This server does not understand part of the table's definition"),
    1142: N_("This connection may not create a table in that database"),
    1215: N_("A link cannot be made: the key it points at is missing"),
    1273: N_("This server does not have a collation the table uses"),
    1286: N_("This server does not have the table's storage engine"),
    1292: N_("A row holds a value this server refuses"),
    1366: N_("A row holds a value this server refuses"),
    1406: N_("A row holds a value too long for its column"),
    1452: N_("Some rows point at rows that were not copied"),
    3780: N_("A link joins columns of different types"),
}

_REF_SQL = {
    "no_action": "NO ACTION",
    "restrict": "RESTRICT",
    "cascade": "CASCADE",
    "set_null": "SET NULL",
    "set_default": "SET DEFAULT",
}

# Read as the hexadecimal of their bytes and written back from it: a shape is
# kept as the server's own bytes, which it takes back as they are.
_BINARY = frozenset(
    {
        "binary",
        "varbinary",
        "tinyblob",
        "blob",
        "mediumblob",
        "longblob",
        "geometry",
        "point",
        "linestring",
        "polygon",
        "multipoint",
        "multilinestring",
        "multipolygon",
        "geometrycollection",
        "geomcollection",
    }
)
# Read as the server prints them: a zero date, a fraction and a negative or
# long TIME survive only that way.
_PRINTED = frozenset({"date", "datetime", "timestamp", "time", "json"})

_TABLES = """
    SELECT TABLE_NAME AS name FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s
"""
_CONSTRAINT_NAMES = """
    SELECT CONSTRAINT_NAME AS name FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = %s AND CONSTRAINT_TYPE IN ('FOREIGN KEY', 'CHECK')
"""
_TRIGGERS = """
    SELECT COUNT(*) AS found FROM information_schema.TRIGGERS
    WHERE EVENT_OBJECT_SCHEMA = %s AND EVENT_OBJECT_TABLE = %s
"""
_REFERENCED_BY = """
    SELECT DISTINCT CONSTRAINT_SCHEMA AS schema_name, TABLE_NAME AS name
    FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE UNIQUE_CONSTRAINT_SCHEMA = %s AND REFERENCED_TABLE_NAME = %s
    ORDER BY schema_name, name
"""
_DATA_TYPES = """
    SELECT COLUMN_NAME AS name, DATA_TYPE AS data_type FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
"""


class MysqlTableCopy:
    """Both ends of a copy of MySQL tables."""

    table_copy_dialect = DIALECT

    def __init__(self, session: MysqlSession, relations: MysqlRelationChanges) -> None:
        self._session = session
        self._relations = relations

    @property
    def table_copy_database(self) -> str:
        """The server, by the address it is reached at: one MySQL server is one
        place a foreign key can reach across, whatever database it is in."""
        options = self._session.options
        # A host seen from an SSH server is not the same host seen from here.
        through = f"ssh:{options.ssh_tunnel}/" if options.ssh_tunnel else ""
        return f"mysql://{through}{options.host.lower()}:{options.port}"

    # The source's half.

    async def describe_for_copy(self, node_ids: list[str]) -> list[CopiedTable]:
        return [await self._describe(node_id) for node_id in node_ids]

    async def _describe(self, node_id: str) -> CopiedTable:
        schema, name = ids.parse(node_id)
        if name is None:
            raise NodeNotFound(node_id)
        facts = await read_relation(self._session, schema, name)
        if facts is None:
            raise NodeNotFound(node_id)
        base = CopiedTable(node_id=node_id, schema_name=schema, name=name)
        if is_system_database(schema):
            return base.model_copy(update={"refusal": say('"{schema}" belongs to the server', schema=schema)})
        if facts.table_type in VIEW_TYPES or facts.table_type != "BASE TABLE":
            return base.model_copy(update={"refusal": say("only tables are copied with their structure")})
        rows = await self._session.query(SQL("SHOW CREATE TABLE {}").format(Identifier(schema, name)).text())
        printed = str(rows[0].get("Create Table") or "")
        if "PARTITION BY" in printed[printed.rfind("\n)") :].upper():
            return base.model_copy(update={"refusal": say("partitioned tables are not copied yet")})
        lines = _body(printed)
        generated = {column.name: column.generated for column in facts.columns}
        columns: list[CopiedColumn] = []
        for column in facts.columns:
            prefix = quoted_name(column.name) + " "
            line = next((one for one in lines if one.startswith(prefix)), None)
            definition = None if line is None else line[len(prefix) :]
            columns.append(
                CopiedColumn(
                    name=column.name,
                    type_sql=_type_of(definition) or column.type.sql,
                    not_null=not column.nullable,
                    identity="by_default" if column.auto_increment else None,
                    generated=generated[column.name],
                    comment=column.comment,
                    definition=definition,
                )
            )
        constraints: list[CopiedConstraint] = []
        indexes: list[CopiedIndex] = []
        for line in lines:
            kind, key_name = _key_line(line)
            if kind == "primary":
                constraints.append(CopiedConstraint(name="PRIMARY", kind="primary_key", definition=line))
            elif kind == "check":
                constraints.append(CopiedConstraint(name=key_name, kind="check", definition=_after_name(line)))
            elif kind in ("unique", "index"):
                indexes.append(CopiedIndex(name=key_name, unique=kind == "unique", body=line))
        links = [
            CopiedLink(
                name=key.name,
                columns=key.columns,
                target_node_id=ids.relation_id(key.target_schema or schema, key.target_table or ""),
                target_schema=key.target_schema or schema,
                target_name=key.target_table or "",
                target_columns=key.target_columns,
                on_update=key.on_update,
                on_delete=key.on_delete,
            )
            for key in facts.keys
            if key.kind == "FOREIGN KEY"
        ]
        triggers = int((await self._session.query(_TRIGGERS, (schema, name)))[0]["found"])
        referencing = await self._session.query(_REFERENCED_BY, (schema, name))
        return base.model_copy(
            update={
                "comment": facts.comment,
                "columns": columns,
                "constraints": constraints,
                "indexes": indexes,
                "links": links,
                "referenced_by": [
                    ids.relation_id(str(row["schema_name"]), str(row["name"]))
                    for row in referencing
                    if (str(row["schema_name"]), str(row["name"])) != (schema, name)
                ],
                "left_behind": (
                    []
                    if not triggers
                    else [say("1 trigger") if triggers == 1 else say("{count} triggers", count=triggers)]
                ),
                "row_estimate": facts.row_estimate,
                "options": _options(printed),
            }
        )

    @asynccontextmanager
    async def reading_tables(self) -> AsyncIterator[_Rows]:
        """Every table read in one consistent snapshot of the source.

        Its own connection, closed afterwards rather than returned: a reader
        that stops in the middle of an unbuffered result leaves it unusable.
        """
        async with self._session.acquire() as connection:
            try:
                async with connection.cursor() as cursor:
                    await cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ", ())
                    await cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY", ())
                yield _Rows(connection)
            finally:
                connection.close()

    # The destination's half.

    async def free_table_names(self, place_node_id: str, wanted: list[str]) -> list[str]:
        taken = await self._taken(place_node_id)
        free: list[str] = []
        for name in wanted:
            chosen = _free(name, taken)
            taken.add(chosen)
            free.append(chosen)
        return free

    async def plan_table_copy(self, request: TableCopyRequest) -> TableCopyPlan:
        return await _Planner(self, request).plan()

    async def carry_table_copy(self, request: TableCopyRequest, rows_of: RowsOf, arrived: Arrived) -> None:
        plan = await self.plan_table_copy(request)
        if plan.problems:
            raise ValueError(plan.problems[0].message)
        schema = _database(request.place_node_id)
        made: list[str] = []
        names = {target.table.node_id: target.name for target in request.tables}
        step = say("Preparing the copy")
        try:
            for statement in plan.statements:
                if statement.stage == "before":
                    step = statement.title
                    async with self._session.altering(refusals=COPY_REFUSALS) as work:
                        await work.execute(_sent(statement.sql))
                    if statement.node_id is not None:
                        made.append(names[statement.node_id])
            if plan.loads:
                async with self._session.writing(refusals=COPY_REFUSALS) as work:
                    # A zero in an AUTO_INCREMENT column is a value of the
                    # source's, not a request for the next number.
                    await work.execute(
                        "SET SESSION sql_mode = CONCAT_WS(',', @@SESSION.sql_mode, 'NO_AUTO_VALUE_ON_ZERO')"
                    )
                    for load in plan.loads:
                        step = say("Rows of {table}", table=load.target_label)
                        kinds = {
                            str(row["name"]): str(row["data_type"]).lower()
                            for row in await work.rows(_DATA_TYPES, (schema, load.name))
                        }
                        await _insert(work, load, [kinds.get(column, "") for column in load.columns], rows_of, arrived)
            for statement in plan.statements:
                if statement.stage == "after":
                    step = statement.title
                    async with self._session.altering(refusals=COPY_REFUSALS) as work:
                        await work.execute(_sent(statement.sql))
        except BaseException as failure:
            await self._undo(schema, made)
            if isinstance(failure, ValueError):
                said = str(failure)
                if said == say("The source rejected the change"):
                    said = say("This database refused it")
                raise ValueError(f"{step}: {said[:1].lower()}{said[1:]}") from None
            raise

    async def _undo(self, schema: str, made: Sequence[str]) -> None:
        """Drop the tables this copy made; nothing else had them yet."""
        if not made:
            return
        async with self._session.altering() as work:
            await work.execute("SET @dp_checks = @@SESSION.foreign_key_checks")
            await work.execute("SET SESSION foreign_key_checks = 0")
            try:
                await work.execute(
                    SQL("DROP TABLE IF EXISTS {}")
                    .format(SQL(", ").join(Identifier(schema, name) for name in made))
                    .text()
                )
            finally:
                await work.execute("SET SESSION foreign_key_checks = @dp_checks")

    async def _taken(self, place_node_id: str) -> set[str]:
        rows = await self._session.query(_TABLES, (_database(place_node_id),))
        return {str(row["name"]) for row in rows}

    async def _constraint_names(self, place_node_id: str) -> set[str]:
        rows = await self._session.query(_CONSTRAINT_NAMES, (_database(place_node_id),))
        return {str(row["name"]) for row in rows}


@dataclass
class _Rows:
    connection: aiomysql.Connection

    def rows(self, node_id: str, columns: list[str]) -> AsyncIterator[bytes]:
        return self._read(node_id, columns)

    async def _read(self, node_id: str, columns: list[str]) -> AsyncIterator[bytes]:
        schema, name = ids.parse(node_id)
        if name is None:
            raise NodeNotFound(node_id)
        async with self.connection.cursor() as cursor:
            await cursor.execute(_DATA_TYPES, (schema, name))
            kinds = {str(row[0]): str(row[1]).lower() for row in await cursor.fetchall()}
        statement = SQL("SELECT {} FROM {}").format(
            SQL(", ").join(_read_expression(column, kinds.get(column, "")) for column in columns),
            Identifier(schema, name),
        )
        async with self.connection.cursor(aiomysql.SSCursor) as cursor:
            await cursor.execute(statement.text(), ())
            while batch := await cursor.fetchmany(READ_BATCH):
                yield b"".join(
                    json.dumps([_text(value) for value in row]).encode() + b"\n" for row in batch
                )


def _read_expression(column: str, kind: str) -> Composable:
    if kind in _BINARY:
        return SQL("HEX({})").format(Identifier(column))
    if kind == "bit":
        return SQL("CAST({} AS UNSIGNED)").format(Identifier(column))
    if kind in _PRINTED:
        return SQL("CAST({} AS CHAR)").format(Identifier(column))
    return Identifier(column)


def _write_placeholder(kind: str) -> str:
    if kind in _BINARY:
        return "UNHEX(%s)"
    if kind == "bit":
        return "CAST(%s AS UNSIGNED)"
    return "%s"


def _text(value: Any) -> str | None:
    """A value as text the server reads back the same."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, set):
        return ",".join(sorted(value))
    return str(value)


async def _insert(
    work: Any, load: CopyLoad, kinds: list[str], rows_of: RowsOf, arrived: Arrived
) -> None:
    """The rows of one table, in INSERTs of many rows each."""
    head = SQL("INSERT INTO {} ({}) VALUES ").format(
        Identifier(load.schema_name, load.name),
        SQL(", ").join(Identifier(column) for column in load.columns),
    ).text()
    row_places = "(" + ", ".join(_write_placeholder(kind) for kind in kinds) + ")"
    count = 0
    size = 0
    pending: list[list[str | None]] = []
    pending_bytes = 0

    async def flush() -> None:
        nonlocal pending, pending_bytes
        if pending:
            await work.execute(
                head + ", ".join([row_places] * len(pending)),
                tuple(value for row in pending for value in row),
            )
        pending, pending_bytes = [], 0

    async for chunk in rows_of(load):
        for line in chunk.splitlines():
            row = json.loads(line)
            pending.append(row)
            pending_bytes += len(line)
            count += 1
            if pending_bytes >= INSERT_BYTES:
                await flush()
        size += len(chunk)
        await arrived(load, count, size)
    await flush()


class _Planner:
    """One plan: the checks first, then the statements in the order they run."""

    def __init__(self, copy: MysqlTableCopy, request: TableCopyRequest) -> None:
        self._copy = copy
        self._request = request
        self._schema = ""
        self._plan = TableCopyPlan()
        self._taken: set[str] = set()
        # Foreign key and check names: MySQL wants each once in a database.
        self._constraints: set[str] = set()
        self._links: list[CopyStatement] = []

    async def plan(self) -> TableCopyPlan:
        request = self._request
        if request.dialect != DIALECT:
            self._problem(None, say("These tables are described in another dialect"))
            return self._plan
        if not await self._place_ok():
            return self._plan
        self._schema = _database(request.place_node_id)
        self._taken = await self._copy._taken(request.place_node_id)
        self._constraints = await self._copy._constraint_names(request.place_node_id)
        self._names_ok()
        if self._plan.problems:
            return self._plan
        new_names = {target.table.node_id: target.name for target in request.tables}
        for target in request.tables:
            self._table(target, new_names)
        self._plan.statements.extend(self._links)
        return self._plan

    async def _place_ok(self) -> bool:
        try:
            options = await self._copy._relations.new_relation_options(self._request.place_node_id)
        except NodeNotFound:
            self._problem(None, say("That database is no longer there"))
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
            if name == "" or name != name.strip():
                self._problem(table.node_id, say("A table name cannot be empty or start or end with spaces"))
            elif len(name) > NAME_LIMIT:
                self._problem(table.node_id, say("{name} is longer than MySQL allows", name=name))
            elif name in seen:
                self._problem(table.node_id, say("Two tables cannot both be called {name}", name=name))
            elif name in self._taken:
                self._problem(
                    table.node_id,
                    say("{schema}.{name} is already there", schema=self._schema, name=name),
                    kind="conflict",
                )
            seen.add(name)
        if len(self._request.tables) > MAX_COPIED_TABLES:
            self._problem(None, say("Copy at most {count} tables at a time", count=MAX_COPIED_TABLES))

    def _table(self, target: TableCopyTarget, new_names: dict[str, str]) -> None:
        table = target.table
        label = f"{self._schema}.{target.name}"
        parts: list[str] = []
        for column in table.columns:
            if column.definition is None or not stands_alone(column.definition):
                self._problem(
                    table.node_id,
                    say("{label}: the type of {name} could not be read", label=table.label, name=column.name),
                )
                return
            parts.append(f"{quoted_name(column.name)} {column.definition}")
        for constraint in table.constraints:
            if not stands_alone(constraint.definition):
                self._warn(say("{label}: {name} could not be read, and is not copied", label=table.label, name=constraint.name))
                continue
            if constraint.kind == "check":
                name = self._free_constraint(constraint.name, table.name, target.name)
                parts.append(f"CONSTRAINT {quoted_name(name)} {constraint.definition}")
            else:
                parts.append(constraint.definition)
        for index in table.indexes:
            # An index's name is its table's own, so the line is kept whole.
            if not stands_alone(index.body):
                self._warn(say("{label}: index {name} could not be read, and is not copied", label=table.label, name=index.name))
                continue
            parts.append(index.body)
        options = table.options or ""
        if options and not stands_alone(options):
            self._warn(say("{label}: its options could not be read, and the server's are used", label=table.label))
            options = ""
        for link in table.links:
            statement = self._link(table, target, link, new_names)
            if statement is not None:
                self._links.append(statement)
        self._plan.statements.append(
            CopyStatement(
                node_id=table.node_id,
                title=say("Create table {label}", label=label),
                # A part to a line: the statement is reviewed before it runs.
                sql=(
                    SQL("CREATE TABLE {} (\n  ").format(Identifier(self._schema, target.name)).readable()
                    + ",\n  ".join(parts)
                    + "\n)"
                    + (f" {options}" if options else "")
                ),
            )
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

    def _link(
        self, table: CopiedTable, target: TableCopyTarget, link: CopiedLink, new_names: dict[str, str]
    ) -> CopyStatement | None:
        decision = target.links.get(link.name, "drop")
        if decision == "drop":
            return None
        if decision == "copy":
            copied = new_names.get(link.target_node_id)
            if copied is None:
                return None
            points_at = Identifier(self._schema, copied)
            label = f"{self._schema}.{copied}"
        else:
            if not self._request.same_database:
                return None
            points_at = Identifier(link.target_schema, link.target_name)
            label = f"{link.target_schema}.{link.target_name}"
        name = self._free_constraint(link.name, table.name, target.name)
        statement = SQL(
            "ALTER TABLE {} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {} ({}) "
            f"ON UPDATE {_REF_SQL[link.on_update]} ON DELETE {_REF_SQL[link.on_delete]}"
        ).format(
            Identifier(self._schema, target.name),
            Identifier(name),
            SQL(", ").join(Identifier(one) for one in link.columns),
            points_at,
            SQL(", ").join(Identifier(one) for one in link.target_columns),
        )
        return CopyStatement(
            node_id=table.node_id,
            title=say("Link {name} to {label}", name=name, label=label),
            sql=statement.readable(),
            stage="after",
        )

    def _free_constraint(self, name: str, old: str, new: str) -> str:
        """A constraint named after its table, named after the copy, and free."""
        renamed = new + name[len(old) :] if name.startswith(old) and old != new else name
        candidate = renamed[:NAME_LIMIT]
        number = 1
        while candidate in self._constraints:
            suffix = f"_{number}"
            candidate = renamed[: NAME_LIMIT - len(suffix)] + suffix
            number += 1
        self._constraints.add(candidate)
        return candidate

    def _problem(
        self, node_id: str | None, message: str, kind: Literal["invalid", "conflict"] = "invalid"
    ) -> None:
        self._plan.problems.append(CopyProblem(node_id=node_id, message=message, kind=kind))

    def _warn(self, message: str) -> None:
        self._plan.warnings.append(message)


def _database(place_node_id: str) -> str:
    schema, relation = ids.parse(place_node_id)
    if relation is not None:
        raise ValueError(say("Paste into a database"))
    return schema


def _body(printed: str) -> list[str]:
    """The lines between the parentheses of CREATE TABLE, without commas."""
    lines = printed.splitlines()
    return [line.strip().rstrip(",") for line in lines[1:] if line.startswith("  ")]


def _options(printed: str) -> str | None:
    """The table's options, without the counter: the copy numbers on from
    what its rows hold, as MySQL does for any table that is given rows."""
    closing = printed.rfind("\n)")
    if closing < 0:
        return None
    words = printed[closing + 2 :].strip().split("\n", 1)[0].split(" ")
    kept = " ".join(word for word in words if not word.upper().startswith("AUTO_INCREMENT="))
    return kept or None


def _key_line(line: str) -> tuple[str, str]:
    """What a line that is not a column is, and its name."""
    upper = line.upper()
    if upper.startswith("PRIMARY KEY"):
        return "primary", "PRIMARY"
    for opening, kind in (
        ("UNIQUE KEY ", "unique"),
        ("KEY ", "index"),
        ("FULLTEXT KEY ", "index"),
        ("SPATIAL KEY ", "index"),
        ("CONSTRAINT ", "constraint"),
    ):
        if upper.startswith(opening):
            name = _first_name(line[len(opening) :])
            if kind == "constraint":
                rest = _after_name(line).upper()
                return ("check", name) if rest.startswith("CHECK") else ("link", name)
            return kind, name
    return "column", ""


def _first_name(text: str) -> str:
    """The backtick-quoted name at the start of `text`."""
    if not text.startswith("`"):
        return ""
    index = 1
    name: list[str] = []
    while index < len(text):
        if text[index] == "`":
            if text[index + 1 : index + 2] == "`":
                name.append("`")
                index += 2
                continue
            break
        name.append(text[index])
        index += 1
    return "".join(name)


def _after_name(line: str) -> str:
    """`CONSTRAINT `name` CHECK (…)` without its first two words."""
    rest = line[len("CONSTRAINT ") :]
    name = _first_name(rest)
    return rest[len(quoted_name(name)) :].strip()


def _sent(readable: str) -> str:
    """A reviewed statement as the driver takes it: every statement is sent
    with parameters, so a `%` in a name, a default or a comment is doubled."""
    return readable.replace("%", "%%")


def _type_of(definition: str | None) -> str | None:
    """The type a definition opens with, for the window; None if unreadable."""
    if definition is None:
        return None
    try:
        parsed = parse(definition)
    except ValueError:
        return None
    return parsed.text[: parsed.type_end].strip() or None


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

