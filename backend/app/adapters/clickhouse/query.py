"""Running SQL somebody wrote on a ClickHouse server (D62, D271).

The defence of a read is the server's own: `readonly=2` refuses every write
and every structure change. ClickHouse has no transaction to hold a run
together — each statement is kept the moment it ends — so a run that changes
anything holds that one statement alone, and Auto-commit's promise, that a
change is kept when its run succeeds, stays true (D271). There is no manual
transaction and nothing is rehearsed.

A statement's time limit is the server's `max_execution_time`, with this
module's own clock a little longer behind it. When either runs out, or
somebody presses Stop, the statement is killed by its query id from a request
of its own.
"""

import asyncio
import re
import time
import uuid
from collections.abc import AsyncIterator

import httpx
from sqlglot import exp

from app.adapters.clickhouse.session import (
    ClickhouseSession,
    Encoded,
    Ran,
    ServerError,
    classify,
)
from app.adapters.clickhouse.statements import parse, prepare
from app.adapters.clickhouse.types import build_column_type, read_cell
from app.adapters.database_ids import database_id, relation_id
from app.adapters.protocol import AdapterError
from app.adapters.query import (
    MaterialisedResult,
    ParameterValue,
    PreparedScript,
    PreparedStatement,
    QueryDiagnostic,
    QueryEvent,
    QueryLimits,
    QueryProfile,
    QueryRequest,
    ResultColumn,
    SchemaEffect,
    StatementFinished,
    StatementStarted,
    StatementStatus,
)
from app.core.translation import N_, say

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300
MAX_MESSAGE_CHARS = 500
# How much longer this module waits than the server's own limit before it
# kills the statement itself: the server's limit is checked between blocks.
_GRACE_SECONDS = 5

# The categories of a failure, by the server's error code. Unlisted is `unknown`.
_CATEGORIES: dict[int, str] = {
    62: "syntax",
    16: "missing_object",
    46: "missing_object",
    47: "missing_object",
    60: "missing_object",
    81: "missing_object",
    497: "permission",
    164: "read_only",
    159: "timeout",
    394: "cancelled",
    202: "resource",
    241: "resource",
    396: "resource",
    6: "data",
    27: "data",
    43: "data",
    53: "data",
    69: "data",
    70: "data",
    72: "data",
    349: "data",
    456: "data",
    457: "data",
    469: "data",
}

_ADMITTED: dict[str, frozenset[str]] = {
    "read": frozenset({"read"}),
    "auto_commit": frozenset({"read", "dml", "ddl", "maintenance"}),
}

_CHANGES = frozenset({"dml", "ddl", "maintenance"})

_UNSAFE = {ord(char): None for char in ("\r", "\n", "\t", "\x00")}
# `Code: 62. DB::Exception: Syntax error: … (SYNTAX_ERROR) (version 25.8…)`
_SENTENCE = re.compile(r"DB::Exception: (.*?)(?:\s*\([A-Z_]+\))?(?:\s*\(version .*\))?\s*$", re.S)
_POSITION = re.compile(r"failed at position (\d+)")


def _safe_text(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    return value.translate(_UNSAFE).strip()[:MAX_MESSAGE_CHARS] or fallback


def diagnostic_of(exc: ServerError, *, cancelled: bool, timed_out: bool) -> QueryDiagnostic:
    """A failure reduced to what may be shown (D64).

    The server's own sentence is passed on, as PostgreSQL's primary message
    is: it is about the statement. Its error name and version are left off.
    """
    category = _CATEGORIES.get(exc.code, "unknown")
    text = str(exc.args[0]) if exc.args else ""
    found = _SENTENCE.search(text)
    message = _safe_text(found.group(1) if found else None, say("The statement could not be run"))
    position = _POSITION.search(text)
    if cancelled or category == "cancelled":
        category, message = "cancelled", say("Cancelled")
    elif timed_out or category == "timeout":
        category, message = "timeout", say("The statement ran out of time")
    return QueryDiagnostic(
        code=str(exc.code or "unknown"),
        category=category,  # type: ignore[arg-type]  # the table above holds the union's members
        message=message,
        # The server counts from one, and from the start of the statement.
        position=None if position is None else max(int(position.group(1)) - 1, 0),
    )


class ResultTooLarge(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def values_of(
    parameters: list[ParameterValue], statement: PreparedStatement
) -> dict[str, str]:
    """Each parameter the statement names, as the server's text; NULL is `\\N`."""
    given = {parameter.name: parameter.value for parameter in parameters}
    return {
        name: Encoded("\\N") if given[name] is None else Encoded(str(given[name]))
        for name in statement.parameters
        if name in given
    }


_DATABASE = "SELECT name FROM system.databases WHERE name = {database:String}"


async def database_of(session: ClickhouseSession, search_path: list[str]) -> str | None:
    """The database an unqualified name means in this run, checked to exist.

    ClickHouse has one default database rather than a path, so the first entry
    is the one that counts.
    """
    wanted = next((name for name in search_path if name), None)
    if wanted is None:
        return session.database() or None
    if not await session.query(_DATABASE, {"database": wanted}):
        raise AdapterError(
            "config", say("This connection has no database called {name}", name=wanted)
        )
    return wanted


def effect_of(statement: PreparedStatement, default_database: str | None) -> SchemaEffect:
    """What a structure change means for the catalog on screen (D66).

    The same reading MySQL's is: a relation's own changes name the relation,
    making or dropping one names its database, a database names the root, and
    what cannot be read with certainty is the whole connection.
    """
    node = parse(statement.text)
    tables = [] if node is None else list(node.find_all(exp.Table))
    kind = (
        str(node.args.get("kind") or "").upper()
        if isinstance(node, (exp.Create, exp.Drop))
        else ""
    )
    if kind in ("DATABASE", "SCHEMA"):
        return SchemaEffect(reload_node_ids=[None])
    if node is None or isinstance(node, exp.Command) or not tables:
        return SchemaEffect(scope="connection")
    table = tables[0]
    database = table.db or default_database or "default"
    relation = relation_id(database, table.name)
    if isinstance(node, (exp.TruncateTable, exp.Alter)):
        return SchemaEffect(relation_node_ids=[relation])
    return SchemaEffect(reload_node_ids=[database_id(database)])


class ClickhouseExecution:
    """One run: its statements one after another, each kept as it ends."""

    def __init__(self, session: ClickhouseSession, request: QueryRequest) -> None:
        self._session = session
        self._request = request
        self._running: str | None = None
        self._cancelled = False
        self._run_bytes = 0
        self._run_results = 0
        self._database: str | None = None

    def events(self) -> AsyncIterator[QueryEvent]:
        return self._run()

    async def cancel(self) -> None:
        """Kill what this run is running; it reports the outcome itself (D64)."""
        self._cancelled = True
        running = self._running
        if running is not None:
            await self._session.kill_query(running)

    async def _run(self) -> AsyncIterator[QueryEvent]:
        script = prepare(self._request.text)
        started = time.monotonic()
        limits = self._request.limits
        try:
            self._database = await database_of(self._session, self._request.search_path)
        except AdapterError:
            raise
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message=N_("The query could not be run"))
            raise AdapterError(error_kind, message) from None
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
            finished = await self._one(statement, limits, alone=len(script.statements) == 1)
            yield finished
            stopped = finished.status != "succeeded"

    def _refused(self, statement: PreparedStatement, alone: bool) -> QueryDiagnostic | None:
        mode = self._request.mode
        if statement.kind not in _ADMITTED.get(mode, frozenset()):
            if mode == "read":
                message = say("A {kind} statement cannot run in a read", kind=statement.kind)
            else:
                message = say("A {kind} statement is not run here", kind=statement.kind)
            return QueryDiagnostic(code="dp_not_admitted", category="read_only", message=message)
        if statement.kind in _CHANGES and not alone:
            return QueryDiagnostic(
                code="dp_not_admitted",
                category="read_only",
                message=say(
                    "ClickHouse keeps a change the moment it is made and cannot undo it, "
                    "so a change cannot share a run with other statements; run it on its own"
                ),
            )
        return None

    async def _one(
        self, statement: PreparedStatement, limits: QueryLimits, *, alone: bool
    ) -> StatementFinished:
        refused = self._refused(statement, alone)
        if refused is not None:
            return StatementFinished(
                ordinal=statement.ordinal, status="failed", duration_ms=0, diagnostic=refused
            )
        began = time.monotonic()
        query_id = str(uuid.uuid4())
        settings = {
            "max_execution_time": str(limits.statement_timeout_seconds),
            # A mutation is otherwise only queued, and its statement would
            # say it succeeded before anything had changed.
            "mutations_sync": "1",
        }
        if self._database is not None:
            settings["database"] = self._database
        self._running = query_id
        timed_out = False
        try:
            running = asyncio.ensure_future(
                self._session.run_statement(
                    statement.text,
                    values_of(self._request.parameters, statement),
                    settings,
                    read=self._request.mode == "read",
                    query_id=query_id,
                    row_limit=limits.max_result_rows,
                )
            )
            done, _ = await asyncio.wait(
                {running}, timeout=limits.statement_timeout_seconds + _GRACE_SECONDS
            )
            if not done:
                timed_out = True
                await self._session.kill_query(query_id)
            ran = await running
            if ran.truncated and self._request.mode != "read":
                # Closing the request stops only a read; anything else is
                # stopped by name once enough of its answer is in.
                await self._session.kill_query(query_id)
            result = None if not ran.names else self._materialise(ran, limits)
        except ResultTooLarge as refusal:
            return StatementFinished(
                ordinal=statement.ordinal,
                status="succeeded",
                duration_ms=self._since(began),
                diagnostic=QueryDiagnostic(
                    code="result_too_large", category="resource", message=refusal.message
                ),
            )
        except ServerError as exc:
            diagnostic = diagnostic_of(exc, cancelled=self._cancelled, timed_out=timed_out)
            status: StatementStatus = "failed"
            if diagnostic.category == "cancelled":
                status = "cancelled"
            elif diagnostic.category == "timeout":
                status = "timed_out"
            return StatementFinished(
                ordinal=statement.ordinal,
                status=status,
                duration_ms=self._since(began),
                diagnostic=diagnostic,
            )
        except (httpx.TransportError, OSError) as exc:
            if self._cancelled or timed_out:
                return self._stopped(statement, began, timed_out)
            error_kind, message = classify(exc, fallback_message=N_("The query could not be run"))
            raise AdapterError(error_kind, message) from None
        finally:
            self._running = None
        if self._cancelled or timed_out:
            return self._stopped(statement, began, timed_out)
        effect: SchemaEffect | None = None
        if statement.kind == "ddl":
            effect = effect_of(statement, self._database)
        return StatementFinished(
            ordinal=statement.ordinal,
            status="succeeded",
            duration_ms=self._since(began),
            row_count=None if result is None else len(result.rows),
            affected_rows=ran.written_rows if statement.kind == "dml" else None,
            result=result,
            effect=effect,
        )

    def _stopped(
        self, statement: PreparedStatement, began: float, timed_out: bool
    ) -> StatementFinished:
        cancelled = self._cancelled and not timed_out
        return StatementFinished(
            ordinal=statement.ordinal,
            status="cancelled" if cancelled else "timed_out",
            duration_ms=self._since(began),
            diagnostic=QueryDiagnostic(
                code="394" if cancelled else "159",
                category="cancelled" if cancelled else "timeout",
                message=say("Cancelled") if cancelled else say("The statement ran out of time"),
            ),
        )

    def _materialise(self, ran: Ran, limits: QueryLimits) -> MaterialisedResult:
        """Every row once, within the ceilings D64 states, names kept apart."""
        columns = [
            ResultColumn(
                id=str(position),
                name=name,
                type=build_column_type(ran.types[position] if position < len(ran.types) else "String"),
            )
            for position, name in enumerate(ran.names)
        ]
        rows: list[list[str | None]] = []
        used = 0
        for raw in ran.rows:
            row: list[str | None] = []
            for column, value in zip(columns, raw, strict=False):
                cell = read_cell(value)
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
        return MaterialisedResult(
            columns=columns, rows=rows, truncated=ran.truncated, bytes_used=used
        )

    @staticmethod
    def _since(began: float) -> int:
        return int((time.monotonic() - began) * 1000)


class ClickhouseQuery:
    """ClickHouse as a source that accepts complete SQL (D62)."""

    def __init__(self, session: ClickhouseSession) -> None:
        self._session = session

    def profile(self) -> QueryProfile:
        return QueryProfile(
            dialect="clickhouse",
            parameter_syntax="named_braces",
            # No manual transaction: ClickHouse has none to hold (D271).
            statement_modes=["read", "auto_commit"],
            supports_cancel=True,
            default_timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            max_timeout_seconds=MAX_TIMEOUT_SECONDS,
        )

    def prepare(self, text: str) -> PreparedScript:
        return prepare(text)

    def open(self, request: QueryRequest) -> ClickhouseExecution:
        return ClickhouseExecution(self._session, request)
