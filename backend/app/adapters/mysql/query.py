"""Running SQL somebody wrote on a MySQL server (D62, D233).

The defence of a read is MySQL's own: `START TRANSACTION READ ONLY` refuses a
write to any table. It does not stop a structure change, which MySQL commits
by itself before it runs, so the class of a statement is what keeps DDL out of
a read here, and what keeps it alone in a run of its own (D233).

A statement's time limit is kept by this module rather than by the server:
MySQL's `max_execution_time` bounds a SELECT and nothing else. When it runs
out, or somebody presses Stop, the statement is killed from a connection of
its own with `KILL QUERY`.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Any

import aiomysql
import pymysql
from sqlglot import exp

from app.adapters.mysql import ids
from app.adapters.mysql.session import MysqlSession, classify
from app.adapters.mysql.statements import bind, bound_names, parse, prepare
from app.adapters.mysql.types import read_cell
from app.adapters.protocol import AdapterError
from app.adapters.query import (
    MaterialisedResult,
    PreparedScript,
    PreparedStatement,
    QueryDiagnostic,
    QueryEvent,
    QueryLimits,
    QueryNotice,
    QueryProfile,
    QueryRehearsal,
    QueryRequest,
    ResultColumn,
    SchemaEffect,
    StatementFinished,
    StatementStarted,
    StatementStatus,
    TransactionContext,
    TransactionState,
)
from app.adapters.relation import ColumnType, TypeCategory
from app.core.translation import N_, say

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300
MAX_MESSAGE_CHARS = 500

# The categories of a failure, by MySQL's error number. Unlisted is `unknown`.
_CATEGORIES: dict[int, str] = {
    1064: "syntax",
    1149: "syntax",
    1146: "missing_object",
    1054: "missing_object",
    1049: "missing_object",
    1305: "missing_object",
    1051: "missing_object",
    1091: "missing_object",
    1044: "permission",
    1045: "permission",
    1142: "permission",
    1143: "permission",
    1227: "permission",
    1792: "read_only",
    1205: "resource",
    1213: "resource",
    1062: "data",
    1048: "data",
    1264: "data",
    1265: "data",
    1292: "data",
    1366: "data",
    1406: "data",
    1451: "data",
    1452: "data",
    3819: "data",
}
_INTERRUPTED = frozenset({1317, 3024})
# A deadlock rolls the whole transaction back by itself.
_DEADLOCK = 1213

# A server's own error, under 2000; above it the client is speaking, about the
# connection, and its text names the host.
_SERVER_ERRORS = range(1000, 2000)

_ADMITTED: dict[str, frozenset[str]] = {
    "read": frozenset({"read"}),
    "auto_commit": frozenset({"read", "dml", "ddl", "maintenance"}),
    # MySQL commits a structure change, and everything before it, the moment
    # it runs: inside a transaction somebody means to end later it would end
    # that transaction behind their back (D233).
    "manual": frozenset({"read", "dml"}),
}

# Classes MySQL commits on their own, so a run holding one holds nothing else.
_COMMITTED_ALONE = frozenset({"ddl", "maintenance"})

_UNSAFE = {ord(char): None for char in ("\r", "\n", "\t", "\x00")}

# What a result column of each wire type is, as far as a result says.
_WIRE_TYPES: dict[int, tuple[str, TypeCategory]] = {
    0: ("decimal", "number"),
    1: ("tinyint", "number"),
    2: ("smallint", "number"),
    3: ("int", "number"),
    4: ("float", "number"),
    5: ("double", "number"),
    6: ("null", "other"),
    7: ("timestamp", "datetime"),
    8: ("bigint", "number"),
    9: ("mediumint", "number"),
    10: ("date", "datetime"),
    11: ("time", "datetime"),
    12: ("datetime", "datetime"),
    13: ("year", "number"),
    14: ("date", "datetime"),
    15: ("varchar", "string"),
    16: ("bit", "number"),
    245: ("json", "json"),
    246: ("decimal", "number"),
    247: ("enum", "enum"),
    248: ("set", "string"),
    249: ("text", "string"),
    250: ("text", "string"),
    251: ("text", "string"),
    252: ("text", "string"),
    253: ("varchar", "string"),
    254: ("char", "string"),
    255: ("geometry", "binary"),
}


def _safe_text(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    return value.translate(_UNSAFE).strip()[:MAX_MESSAGE_CHARS] or fallback


def diagnostic_of(exc: pymysql.err.MySQLError, *, cancelled: bool) -> QueryDiagnostic:
    """A failure reduced to what may be shown (D64).

    The server's own sentence is passed on, as PostgreSQL's primary message is:
    it is about the statement, and a MySQL server never writes a password into
    it. The client's sentences, about reaching the server, are not.
    """
    code = exc.args[0] if exc.args and isinstance(exc.args[0], int) else 0
    category = _CATEGORIES.get(code, "unknown")
    message = say("The statement could not be run")
    if code in _SERVER_ERRORS and len(exc.args) > 1:
        message = _safe_text(str(exc.args[1]), message)
    if code in _INTERRUPTED:
        category = "cancelled" if cancelled else "timeout"
        message = say("Cancelled") if cancelled else say("The statement ran out of time")
    return QueryDiagnostic(
        code=str(code or "unknown"),
        category=category,  # type: ignore[arg-type]  # the table above holds the union's members
        message=message,
    )


class _Cursor(aiomysql.Cursor):  # type: ignore[misc]  # aiomysql is untyped
    """A cursor that keeps the server's warnings instead of raising Python's.

    aiomysql reads SHOW WARNINGS after a statement that left any and hands each
    to `warnings.warn`, where nobody reading the run would see it.
    """

    notes: list[tuple[Any, ...]] = []

    async def _show_warnings(self, conn: Any) -> None:
        rows = await conn.show_warnings()
        self.notes = list(rows or [])


class ResultTooLarge(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _values(request: QueryRequest, statement: PreparedStatement) -> tuple[str | None, ...] | None:
    """One value per placeholder in the order they stand, or nothing."""
    if not statement.parameters:
        return None
    given = {parameter.name: parameter.value for parameter in request.parameters}
    return tuple(given.get(name) for name in bound_names(statement.text))


async def use_database(
    session: MysqlSession, connection: aiomysql.Connection, search_path: list[str]
) -> bool:
    """Make the first named database the default one, after checking it exists.

    MySQL has one default database rather than a path, so the first entry is
    the one that counts. Answers whether the default was changed, and so has
    to be put back.
    """
    wanted = next((name for name in search_path if name), None)
    if wanted is None or wanted == session.database():
        return False
    async with connection.cursor() as cursor:
        await cursor.execute(
            "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
            (wanted,),
        )
        if await cursor.fetchone() is None:
            raise AdapterError(
                "config", say("This connection has no database called {name}", name=wanted)
            )
    await connection.select_db(wanted)
    return True


async def restore_database(
    session: MysqlSession, connection: aiomysql.Connection, changed: bool
) -> None:
    """Put the default database back before the pool has the connection again.

    A connection that had none cannot be given none again, so it is closed and
    the pool makes a fresh one.
    """
    if not changed:
        return
    if session.database():
        await connection.select_db(session.database())
    else:
        connection.close()


def default_database(session: MysqlSession, search_path: list[str]) -> str | None:
    """What an unqualified name in this run means."""
    return next((name for name in search_path if name), None) or session.database() or None


def effect_of(statement: PreparedStatement, default_database: str | None) -> SchemaEffect:
    """What a structure change means for the catalog on screen (D66).

    A relation's own changes name the relation; making or dropping one names
    its database; a database names the root. What cannot be read with
    certainty — a rename, an unqualified name with no default database — is
    the whole connection.
    """
    node = parse(statement.text)
    tables = [] if node is None else list(node.find_all(exp.Table))
    if node is None or isinstance(node, exp.Command) or not tables:
        if isinstance(node, (exp.Create, exp.Drop)) and str(
            node.args.get("kind") or ""
        ).upper() in ("DATABASE", "SCHEMA"):
            return SchemaEffect(reload_node_ids=[None])
        return SchemaEffect(scope="connection")
    kind = str(node.args.get("kind") or "").upper() if isinstance(node, (exp.Create, exp.Drop)) else ""
    if kind in ("DATABASE", "SCHEMA"):
        return SchemaEffect(reload_node_ids=[None])
    table = tables[0]
    database = table.db or default_database
    if not database:
        return SchemaEffect(scope="connection")
    relation = ids.relation_id(database, table.name)
    if isinstance(node, exp.TruncateTable) or (
        isinstance(node, (exp.Alter, exp.Create, exp.Drop)) and kind == "INDEX"
    ):
        return SchemaEffect(relation_node_ids=[relation])
    if isinstance(node, exp.Alter):
        renamed = any(isinstance(action, exp.AlterRename) for action in node.args.get("actions") or ())
        if renamed:
            return SchemaEffect(reload_node_ids=[ids.database_id(database)])
        return SchemaEffect(relation_node_ids=[relation])
    return SchemaEffect(reload_node_ids=[ids.database_id(database)])


class _Statements:
    """Running the statements of one request on one connection."""

    def __init__(self, session: MysqlSession, request: QueryRequest) -> None:
        self._session = session
        self._request = request
        self._connection: aiomysql.Connection | None = None
        self._cancelled = False
        self._run_bytes = 0
        self._run_results = 0
        self._default_database: str | None = None
        self.mutating = 0
        self.ddl = 0
        self.affected = 0
        self.targets: list[str] = []
        self.effect = SchemaEffect()
        self.failed = False
        # A failure after which the transaction is no longer the one begun.
        self.ended = False

    async def cancel(self) -> None:
        """Kill what this run is running; it reports the outcome itself (D64)."""
        self._cancelled = True
        connection = self._connection
        if connection is not None:
            await self._session.kill_query(connection.thread_id())

    async def _statements(
        self, connection: aiomysql.Connection, script: PreparedScript, started: float
    ) -> AsyncIterator[QueryEvent]:
        limits = self._request.limits
        stopped = False
        for statement in script.statements:
            if stopped:
                yield StatementFinished(ordinal=statement.ordinal, status="not_run", duration_ms=0)
                continue
            if self._cancelled:
                yield StatementFinished(ordinal=statement.ordinal, status="cancelled", duration_ms=0)
                stopped = True
                continue
            if time.monotonic() - started > limits.script_timeout_seconds:
                yield StatementFinished(ordinal=statement.ordinal, status="timed_out", duration_ms=0)
                stopped = True
                continue
            yield StatementStarted(ordinal=statement.ordinal)
            finished = await self._one(connection, statement, limits, alone=len(script.statements) == 1)
            yield finished
            stopped = finished.status != "succeeded"
            self.failed = self.failed or stopped

    def _refused(self, statement: PreparedStatement, alone: bool) -> QueryDiagnostic | None:
        mode = self._request.mode
        if statement.kind not in _ADMITTED[mode]:
            if mode == "read":
                message = say("A {kind} statement cannot run in a read", kind=statement.kind)
            elif mode == "manual" and statement.kind in _COMMITTED_ALONE:
                message = say(
                    "MySQL commits a structure change at once, and the open transaction with it; "
                    "run it outside the transaction"
                )
            else:
                message = say("A {kind} statement is not run here", kind=statement.kind)
            return QueryDiagnostic(code="dp_not_admitted", category="read_only", message=message)
        if statement.kind in _COMMITTED_ALONE and not alone:
            return QueryDiagnostic(
                code="dp_not_admitted",
                category="read_only",
                message=say(
                    "MySQL commits a structure change at once, so it cannot share a run "
                    "with other statements; run it on its own"
                ),
            )
        return None

    async def _one(
        self,
        connection: aiomysql.Connection,
        statement: PreparedStatement,
        limits: QueryLimits,
        *,
        alone: bool,
    ) -> StatementFinished:
        refused = self._refused(statement, alone)
        if refused is not None:
            return StatementFinished(
                ordinal=statement.ordinal, status="failed", duration_ms=0, diagnostic=refused
            )
        began = time.monotonic()
        notices: list[QueryNotice] = []
        try:
            async with connection.cursor(_Cursor) as cursor:
                values = _values(self._request, statement)
                text = statement.text if values is None else bind(statement.text)
                killed = await self._bounded(connection, cursor.execute(text, values), limits)
                if killed or self._cancelled:
                    # A statement made only of SLEEP() answers a KILL QUERY by
                    # returning early rather than by failing; it was stopped
                    # all the same, and is reported as what stopped it.
                    return StatementFinished(
                        ordinal=statement.ordinal,
                        status="cancelled" if self._cancelled else "timed_out",
                        duration_ms=self._since(began),
                        diagnostic=QueryDiagnostic(
                            code="1317",
                            category="cancelled" if self._cancelled else "timeout",
                            message=(
                                say("Cancelled")
                                if self._cancelled
                                else say("The statement ran out of time")
                            ),
                        ),
                    )
                notices = [
                    QueryNotice(
                        severity=_safe_text(str(note[0]), "Warning"),
                        message=_safe_text(str(note[-1]), say("A message was raised")),
                    )
                    for note in cursor.notes[: limits.max_messages]
                ]
                result: MaterialisedResult | None = None
                if cursor.description is not None:
                    result = await self._materialise(cursor, limits)
                affected = (
                    cursor.rowcount
                    if statement.kind in ("dml", "ddl") and cursor.rowcount >= 0
                    else None
                )
        except ResultTooLarge as refusal:
            return StatementFinished(
                ordinal=statement.ordinal,
                status="succeeded",
                duration_ms=self._since(began),
                notices=notices,
                diagnostic=QueryDiagnostic(
                    code="result_too_large", category="resource", message=refusal.message
                ),
            )
        except pymysql.err.MySQLError as exc:
            diagnostic = diagnostic_of(exc, cancelled=self._cancelled)
            if exc.args and exc.args[0] == _DEADLOCK:
                self.ended = True
            status: StatementStatus = "failed"
            if diagnostic.category == "cancelled":
                status = "cancelled"
            elif diagnostic.category == "timeout":
                status = "timed_out"
            return StatementFinished(
                ordinal=statement.ordinal,
                status=status,
                duration_ms=self._since(began),
                notices=notices,
                diagnostic=diagnostic,
            )
        self.mutating += 1 if statement.kind in ("dml", "ddl") else 0
        self.affected += affected or 0
        for target in statement.targets:
            if target not in self.targets:
                self.targets.append(target)
        effect: SchemaEffect | None = None
        if statement.kind == "ddl":
            self.ddl += 1
            effect = effect_of(statement, self._default_database)
            self.effect = self.effect.with_(effect)
        return StatementFinished(
            ordinal=statement.ordinal,
            status="succeeded",
            duration_ms=self._since(began),
            row_count=None if result is None else len(result.rows),
            affected_rows=affected,
            result=result,
            notices=notices,
            effect=effect,
        )

    async def _bounded(
        self, connection: aiomysql.Connection, running: Any, limits: QueryLimits
    ) -> bool:
        """Run the statement, and kill it if it outlives its limit.

        Answers whether it was killed for its time.
        """
        task = asyncio.ensure_future(running)
        done, _ = await asyncio.wait({task}, timeout=limits.statement_timeout_seconds)
        if not done:
            await self._session.kill_query(connection.thread_id())
        await task
        return not done

    async def _materialise(self, cursor: Any, limits: QueryLimits) -> MaterialisedResult:
        """Every row once, within the ceilings D64 states, names kept apart.

        Rows are read as tuples: two columns named `id` are two columns.
        """
        description = cursor.description or []
        fetched = list(await cursor.fetchmany(limits.max_result_rows + 1))
        truncated = len(fetched) > limits.max_result_rows
        fetched = fetched[: limits.max_result_rows]
        columns: list[ResultColumn] = []
        for position, column in enumerate(description):
            sql, category = _WIRE_TYPES.get(int(column[1]), ("unknown", "other"))
            # The wire type of a BLOB and of a TEXT is the same; what the
            # driver handed back says which this one is.
            if category == "string" and any(
                isinstance(row[position], bytes | bytearray) for row in fetched
            ):
                category = "binary"
            columns.append(
                ResultColumn(
                    id=str(position),
                    name=str(column[0]),
                    type=ColumnType(sql=sql, category=category),
                )
            )
        rows: list[list[str | None]] = []
        used = 0
        for raw in fetched:
            row: list[str | None] = []
            for column, value in zip(columns, raw, strict=False):
                cell = read_cell(value, column.type)
                size = 0 if cell is None else len(cell.encode())
                if size > limits.max_cell_bytes:
                    raise ResultTooLarge(
                        say("A value in {column} is larger than one cell may be", column=column.name)
                    )
                used += size
                if used > limits.max_result_bytes:
                    raise ResultTooLarge(say("This result is larger than one result may be"))
                row.append(cell)
            rows.append(row)
        self._run_bytes += used
        self._run_results += 1
        if self._run_results > limits.max_run_results:
            raise ResultTooLarge(say("This run produced more results than one run may hold"))
        if self._run_bytes > limits.max_run_bytes:
            raise ResultTooLarge(say("This run produced more data than one run may hold"))
        return MaterialisedResult(columns=columns, rows=rows, truncated=truncated, bytes_used=used)

    @staticmethod
    def _since(began: float) -> int:
        return int((time.monotonic() - began) * 1000)


class MysqlExecution(_Statements):
    """One run that opens its own transaction and ends it.

    A read runs in a read-only transaction. Auto-commit makes the run one
    transaction committed only when every statement succeeded, except for a
    structure change, which MySQL commits by itself and which therefore runs
    alone with no transaction around it (D233).
    """

    def events(self) -> AsyncIterator[QueryEvent]:
        return self._run()

    async def _run(self) -> AsyncIterator[QueryEvent]:
        script = prepare(self._request.text)
        started = time.monotonic()
        reading = self._request.mode == "read"
        kinds = [statement.kind for statement in script.statements]
        outside = not reading and len(kinds) == 1 and kinds[0] in _COMMITTED_ALONE
        changed = False
        try:
            async with self._session.acquire() as connection:
                self._connection = connection
                try:
                    changed = await use_database(
                        self._session, connection, self._request.search_path
                    )
                    self._default_database = default_database(
                        self._session, self._request.search_path
                    )
                    if not outside:
                        await connection.query(
                            "START TRANSACTION READ ONLY" if reading else "START TRANSACTION"
                        )
                    async for event in self._statements(connection, script, started):
                        yield event
                    if not outside:
                        if self.failed or reading:
                            await connection.rollback()
                        else:
                            await connection.commit()
                finally:
                    self._connection = None
                    if not outside and connection.get_transaction_status():
                        await connection.rollback()
                    await restore_database(self._session, connection, changed)
        except AdapterError:
            raise
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message=N_("The query could not be run"))
            raise AdapterError(error_kind, message) from None


class _BoundExecution(_Statements):
    """One run inside a transaction somebody else opened, and will end."""

    def __init__(
        self,
        session: MysqlSession,
        request: QueryRequest,
        connection: aiomysql.Connection,
        default_database: str | None,
    ) -> None:
        super().__init__(session, request)
        self._held = connection
        self._default_database = default_database

    def events(self) -> AsyncIterator[QueryEvent]:
        return self._run()

    async def _run(self) -> AsyncIterator[QueryEvent]:
        script = prepare(self._request.text)
        started = time.monotonic()
        self._connection = self._held
        try:
            async for event in self._statements(self._held, script, started):
                yield event
        except AdapterError:
            raise
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message=N_("The query could not be run"))
            raise AdapterError(error_kind, message) from None
        finally:
            self._connection = None


class MysqlTransaction:
    """One transaction, open across requests, holding its connection (D66).

    Unlike PostgreSQL, MySQL keeps a transaction usable after a failed
    statement, so a failure does not end it; a deadlock does, because MySQL has
    already rolled it back by then.
    """

    def __init__(self, session: MysqlSession, context: TransactionContext) -> None:
        self._session = session
        self._context = context
        self._stack = AsyncExitStack()
        self._connection: aiomysql.Connection | None = None
        self._changed = False
        self._default_database: str | None = None
        self._open = False
        self._broken = False
        self._statements = 0
        self._mutating = 0
        self._ddl = 0
        self._affected = 0
        self._targets: list[str] = []
        self._effect = SchemaEffect()

    async def begin(self) -> None:
        try:
            connection = await self._stack.enter_async_context(self._session.acquire())
            self._changed = await use_database(
                self._session, connection, self._context.search_path
            )
            self._default_database = default_database(self._session, self._context.search_path)
            await connection.query("START TRANSACTION")
        except AdapterError:
            await self._stack.aclose()
            raise
        except Exception as exc:
            await self._stack.aclose()
            error_kind, message = classify(exc, fallback_message=N_("The transaction could not be opened"))
            raise AdapterError(error_kind, message) from None
        self._connection = connection
        self._open = True

    def execute(self, request: QueryRequest) -> _BoundExecution:
        connection = self._connection
        if connection is None or not self._open:
            raise AdapterError("unknown", say("This transaction is no longer open"))
        if self._broken:
            raise AdapterError("unknown", say("This transaction failed and can only be rolled back"))
        # A statement's time limit is the transaction's, as PostgreSQL's is.
        limits = request.limits.model_copy(
            update={"statement_timeout_seconds": self._context.statement_timeout_seconds}
        )
        return _BoundExecution(
            self._session,
            request.model_copy(update={"limits": limits, "mode": "manual"}),
            connection,
            self._default_database,
        )

    async def rehearse(self, request: QueryRequest) -> QueryRehearsal:
        """Refused: MySQL commits a structure change, so it cannot be undone."""
        raise AdapterError(
            "config", say("MySQL commits a structure change at once, so it cannot be tried out first")
        )

    def absorb(self, run: Any) -> None:
        if not isinstance(run, _Statements):
            return
        self._statements += 1
        self._mutating += run.mutating
        self._ddl += run.ddl
        self._affected += run.affected
        self._effect = self._effect.with_(run.effect)
        for target in run.targets:
            if target not in self._targets:
                self._targets.append(target)
        if run.ended:
            self._broken = True

    def state(self) -> TransactionState:
        return TransactionState(
            open=self._open,
            broken=self._broken,
            statements=self._statements,
            mutating_statements=self._mutating,
            ddl_statements=self._ddl,
            affected_rows=self._affected,
            targets=list(self._targets),
            effect=self._effect,
        )

    async def commit(self) -> None:
        if self._broken:
            raise AdapterError("unknown", say("This transaction failed and can only be rolled back"))
        await self._end(commit=True)

    async def rollback(self) -> None:
        await self._end(commit=False)

    async def aclose(self) -> None:
        await self._end(commit=False)

    async def _end(self, *, commit: bool) -> None:
        if not self._open:
            return
        self._open = False
        connection = self._connection
        self._connection = None
        try:
            if connection is not None:
                if commit:
                    await connection.commit()
                else:
                    await connection.rollback()
                await restore_database(self._session, connection, self._changed)
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message=N_("The transaction could not be ended"))
            raise AdapterError(error_kind, message) from None
        finally:
            await self._stack.aclose()


class MysqlQuery:
    """MySQL as a source that accepts complete SQL (D62)."""

    def __init__(self, session: MysqlSession) -> None:
        self._session = session

    def profile(self) -> QueryProfile:
        return QueryProfile(
            dialect="mysql",
            parameter_syntax="named_colon",
            statement_modes=["read", "auto_commit", "manual"],
            supports_cancel=True,
            default_timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            max_timeout_seconds=MAX_TIMEOUT_SECONDS,
        )

    def prepare(self, text: str) -> PreparedScript:
        return prepare(text)

    def open(self, request: QueryRequest) -> MysqlExecution:
        return MysqlExecution(self._session, request)

    async def begin(self, context: TransactionContext) -> MysqlTransaction:
        transaction = MysqlTransaction(self._session, context)
        await transaction.begin()
        return transaction

