"""Both ends of a copy of ClickHouse tables with their structure (D182, D277).

The source describes a table from its catalog: each column's type and its
DEFAULT, MATERIALIZED, ALIAS or EPHEMERAL expression, comment and codec; its
skipping indexes and checks; and its engine with keys and settings as
`engine_full` writes them. The destination, which speaks the same dialect,
composes its own CREATE TABLE from those parts after checking that each is one
part of a statement and nothing more. ClickHouse has no foreign keys, so no
link travels.

The rows travel in TabSeparated, the server's own text: every value it writes
it reads back the same — a byte string, a NaN, an array, a moment in UTC with
its `Z` (D268). They are written into the copy as they are read, one INSERT a
table. Nothing holds the tables still while they are read, and a failure
drops every table this copy made.
"""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

from app.adapters.clickhouse.catalog import is_system_database
from app.adapters.clickhouse.columns import ALTERING
from app.adapters.clickhouse.inspection import (
    ColumnFacts,
    RelationFacts,
    read_relation,
)
from app.adapters.clickhouse.relation_changes import ClickhouseRelationChanges
from app.adapters.clickhouse.session import ClickhouseSession, quoted_name
from app.adapters.clickhouse.sql import SQL, Identifier, text_literal
from app.adapters.database_ids import parse
from app.adapters.protocol import NodeNotFound
from app.adapters.table_copy import (
    MAX_COPIED_TABLES,
    Arrived,
    CopiedColumn,
    CopiedConstraint,
    CopiedIndex,
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

DIALECT = "clickhouse"
NAME_LIMIT = 63

COPY_REFUSALS: dict[int, str] = {
    57: N_("Something with that name is already there"),
    497: N_("This connection may not create a table in that database"),
    62: N_("This server does not understand part of the table's definition"),
    36: N_("This server cannot make the table as described"),
    27: N_("A row holds a value this server refuses"),
    6: N_("A row holds a value this server refuses"),
    469: N_("A row breaks a check of the table"),
}

# How a moment in the rows, written in UTC with its `Z` (D268), is read back.
_READING = {"date_time_input_format": "best_effort", "input_format_tsv_empty_as_default": "0"}

# Engines whose rows are the table's own and whose definition names nothing
# else: a replicated table's path in the coordinator would be shared by its
# copy, and a table over a URL, a file or a stream holds no rows to copy.
_LOG_ENGINES = frozenset({"Log", "TinyLog", "StripeLog", "Memory"})

_TABLES = "SELECT name FROM system.tables WHERE database = {database:String}"


def stands_alone(text: str) -> bool:
    """Whether catalog text is one part of a statement and nothing after it.

    `is_one_fragment` with ClickHouse's quoting: a string or a quoted name
    escapes with a backslash as well as by doubling its quote, and a name may
    be quoted with backticks. No statement may end and no comment start outside
    quotes, every quote closes and every parenthesis matches.
    """
    depth = 0
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in ("'", '"', "`"):
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == char:
                    if text[index + 1 : index + 2] == char:
                        index += 2
                        continue
                    break
                index += 1
            if index >= length:
                return False
            index += 1
            continue
        if char in (";", "#") or text.startswith(("--", "/*"), index):
            return False
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
        index += 1
    return depth == 0 and text.strip() != ""


def _copyable(engine: str) -> bool:
    if engine.startswith(("Replicated", "Shared")):
        return False
    return engine.endswith("MergeTree") or engine in _LOG_ENGINES


def _definition(column: ColumnFacts, kind: str) -> str:
    """A column's definition after its name, as CREATE TABLE takes it."""
    parts = [column.type.sql]
    expression = column.generated or column.default
    if expression is not None:
        parts.append(f"{kind} {expression}")
    if column.comment:
        parts.append(f"COMMENT {text_literal(column.comment)}")
    if column.codec:
        parts.append(column.codec)
    return " ".join(parts)


class ClickhouseTableCopy:
    """Both ends of a copy of ClickHouse tables."""

    table_copy_dialect = DIALECT

    def __init__(self, session: ClickhouseSession, relations: ClickhouseRelationChanges) -> None:
        self._session = session
        self._relations = relations

    @property
    def table_copy_database(self) -> str:
        """The server, by the address it is reached at."""
        options = self._session.options
        # A host seen from an SSH server is not the same host seen from here.
        through = f"ssh:{options.ssh_tunnel}/" if options.ssh_tunnel else ""
        return f"clickhouse://{through}{options.host.lower()}:{options.port}"

    # The source's half.

    async def describe_for_copy(self, node_ids: list[str]) -> list[CopiedTable]:
        return [await self._describe(node_id) for node_id in node_ids]

    async def _describe(self, node_id: str) -> CopiedTable:
        schema, name = parse(node_id)
        if name is None:
            raise NodeNotFound(node_id)
        facts = await read_relation(self._session, schema, name)
        if facts is None:
            raise NodeNotFound(node_id)
        base = CopiedTable(node_id=node_id, schema_name=schema, name=name)
        if is_system_database(schema):
            return base.model_copy(update={"refusal": say('"{schema}" belongs to the server', schema=schema)})
        if facts.is_view:
            return base.model_copy(update={"refusal": say("only tables are copied with their structure")})
        if not _copyable(facts.engine):
            return base.model_copy(
                update={"refusal": say("a {engine} table is not copied", engine=facts.engine)}
            )
        kinds = await self._default_kinds(facts)
        return base.model_copy(
            update={
                "comment": facts.comment,
                "columns": [
                    CopiedColumn(
                        name=column.name,
                        type_sql=column.type.sql,
                        not_null=not column.nullable,
                        # An EPHEMERAL column cannot be read, so it travels
                        # as a computed one: in the definition, never in rows.
                        generated=column.generated
                        or (column.default if kinds.get(column.name) == "EPHEMERAL" else None),
                        comment=column.comment,
                        definition=_definition(column, kinds.get(column.name, "DEFAULT")),
                    )
                    for column in facts.columns
                ],
                "constraints": [
                    CopiedConstraint(
                        name=check.name,
                        kind="check",
                        definition=f"{'CHECK' if check.enforced else 'ASSUME'} {check.expression}",
                    )
                    for check in facts.checks
                ],
                "indexes": [
                    CopiedIndex(
                        name=index.name,
                        body=(
                            f"INDEX {quoted_name(index.name)} {index.expression} "
                            f"TYPE {index.type_full or index.type} GRANULARITY {index.granularity}"
                        ),
                    )
                    for index in facts.indexes
                ],
                "left_behind": [
                    say("materialized view {view}", view=view) for view in facts.dependents
                ],
                "row_estimate": facts.row_estimate,
                "options": facts.engine_full,
            }
        )

    async def _default_kinds(self, facts: RelationFacts) -> dict[str, str]:
        rows = await self._session.query(
            "SELECT name, default_kind FROM system.columns "
            "WHERE database = {database:String} AND table = {table:String}",
            {"database": facts.schema, "table": facts.name},
        )
        return {str(row["name"]): str(row["default_kind"]) or "DEFAULT" for row in rows}

    @asynccontextmanager
    async def reading_tables(self) -> AsyncIterator[_Rows]:
        """Each table read when its turn comes: ClickHouse holds no snapshot."""
        yield _Rows(self._session)

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
                step = statement.title
                await self._session.command(statement.sql, {}, settings=ALTERING, refusals=COPY_REFUSALS)
                if statement.node_id is not None:
                    made.append(names[statement.node_id])
            for load in plan.loads:
                step = say("Rows of {table}", table=load.target_label)
                await self._insert(load, rows_of, arrived)
        except BaseException as failure:
            await self._undo(schema, made)
            if isinstance(failure, ValueError):
                said = str(failure)
                if said == say("The source rejected the change"):
                    said = say("This database refused it")
                raise ValueError(f"{step}: {said[:1].lower()}{said[1:]}") from None
            raise

    async def _insert(self, load: CopyLoad, rows_of: RowsOf, arrived: Arrived) -> None:
        """One table's rows, streamed into one INSERT as they are read."""
        counted = {"rows": 0, "bytes": 0}

        async def body() -> AsyncIterator[bytes]:
            async for chunk in rows_of(load):
                counted["rows"] += chunk.count(b"\n")
                counted["bytes"] += len(chunk)
                await arrived(load, counted["rows"], counted["bytes"])
                yield chunk

        statement = SQL("INSERT INTO {} ({}) FORMAT TabSeparated").format(
            Identifier(load.schema_name, load.name),
            SQL(", ").join(Identifier(column) for column in load.columns),
        )
        await self._session.command(
            statement.text(), {}, settings=_READING, refusals=COPY_REFUSALS, data=body()
        )

    async def _undo(self, schema: str, made: Sequence[str]) -> None:
        """Drop the tables this copy made; nothing else had them yet."""
        for name in made:
            await self._session.command(
                SQL("DROP TABLE IF EXISTS {}").format(Identifier(schema, name)).text(),
                {},
                settings=ALTERING,
            )

    async def _taken(self, place_node_id: str) -> set[str]:
        rows = await self._session.query(_TABLES, {"database": _database(place_node_id)})
        return {str(row["name"]) for row in rows}


@dataclass
class _Rows:
    session: ClickhouseSession

    def rows(self, node_id: str, columns: list[str]) -> AsyncIterator[bytes]:
        schema, name = parse(node_id)
        if name is None:
            raise NodeNotFound(node_id)
        statement = SQL("SELECT {} FROM {} FORMAT TabSeparated").format(
            SQL(", ").join(Identifier(column) for column in columns), Identifier(schema, name)
        )
        return self.session.stream_bytes(statement.text(), {}, {})


class _Planner:
    """One plan: the checks first, then the statements in the order they run."""

    def __init__(self, copy: ClickhouseTableCopy, request: TableCopyRequest) -> None:
        self._copy = copy
        self._request = request
        self._schema = ""
        self._plan = TableCopyPlan()
        self._taken: set[str] = set()

    async def plan(self) -> TableCopyPlan:
        request = self._request
        if request.dialect != DIALECT:
            self._problem(None, say("These tables are described in another dialect"))
            return self._plan
        if not await self._place_ok():
            return self._plan
        self._schema = _database(request.place_node_id)
        self._taken = await self._copy._taken(request.place_node_id)
        self._names_ok()
        if self._plan.problems:
            return self._plan
        for target in request.tables:
            self._table(target)
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
                self._problem(table.node_id, say("{name} is too long a name", name=name))
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

    def _table(self, target: TableCopyTarget) -> None:
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
        for index in table.indexes:
            if not stands_alone(index.body):
                self._warn(
                    say("{label}: index {name} could not be read, and is not copied", label=table.label, name=index.name)
                )
                continue
            parts.append(index.body)
        for constraint in table.constraints:
            if not stands_alone(constraint.definition):
                self._warn(
                    say("{label}: {name} could not be read, and is not copied", label=table.label, name=constraint.name)
                )
                continue
            parts.append(f"CONSTRAINT {quoted_name(constraint.name)} {constraint.definition}")
        engine = table.options or ""
        if not engine or not stands_alone(engine):
            self._problem(table.node_id, say("{label}: its engine could not be read", label=table.label))
            return
        statement = (
            SQL("CREATE TABLE {} (\n  ").format(Identifier(self._schema, target.name)).readable()
            + ",\n  ".join(parts)
            + f"\n)\nENGINE = {engine}"
        )
        if table.comment:
            statement += f"\nCOMMENT {text_literal(table.comment)}"
        self._plan.statements.append(
            CopyStatement(node_id=table.node_id, title=say("Create table {label}", label=label), sql=statement)
        )
        if self._request.rows:
            self._plan.loads.append(
                CopyLoad(
                    node_id=table.node_id,
                    schema_name=self._schema,
                    name=target.name,
                    # A computed column takes no value (see `_describe`).
                    columns=[column.name for column in table.columns if column.generated is None],
                )
            )

    def _problem(
        self, node_id: str | None, message: str, kind: Literal["invalid", "conflict"] = "invalid"
    ) -> None:
        self._plan.problems.append(CopyProblem(node_id=node_id, message=message, kind=kind))

    def _warn(self, message: str) -> None:
        self._plan.warnings.append(message)


def _database(place_node_id: str) -> str:
    schema, relation = parse(place_node_id)
    if relation is not None:
        raise ValueError(say("Paste into a database"))
    return schema


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
