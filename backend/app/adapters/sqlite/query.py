"""Running SQL somebody wrote on a SQLite file (D62, D253).

The defence of a read is SQLite's own `query_only`, set on the connection and
kept there by the authorizer. Structure changes are transactional in SQLite,
so a run is one transaction whatever it holds, a held transaction may change
structure, and a change is rehearsed by carrying it out and rolling it back,
as on PostgreSQL. Only maintenance runs outside a transaction: VACUUM cannot
run inside one.

A statement's time limit and Stop are the session's clock (`Handle`): the
statement is interrupted at its next look at it.
"""

import sqlite3
import time
from collections.abc import AsyncIterator
from functools import partial
from typing import Any

from app.adapters.protocol import AdapterError
from app.adapters.query import (
    MaterialisedResult,
    PreparedScript,
    PreparedStatement,
    QueryDiagnostic,
    QueryEvent,
    QueryLimits,
    QueryProfile,
    QueryRehearsal,
    QueryRequest,
    RehearsedStatement,
    ResultColumn,
    SchemaEffect,
    StatementFinished,
    StatementStarted,
    StatementStatus,
    TransactionContext,
    TransactionState,
)
from app.adapters.relation import ColumnType, TypeCategory
from app.adapters.sqlite.inspection import SCHEMA
from app.adapters.sqlite.session import Handle, SqliteSession, classify
from app.adapters.sqlite.statements import effect_of, prepare
from app.adapters.sqlite.types import read_cell
from app.core.translation import N_, say

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300
MAX_MESSAGE_CHARS = 500
# How long a rehearsal waits for another connection's lock: short, because a
# preview that queues is a preview that holds the person looking at it (D66).
REHEARSAL_BUSY_SECONDS = 3.0

_ADMITTED: dict[str, frozenset[str]] = {
    "read": frozenset({"read"}),
    "auto_commit": frozenset({"read", "dml", "ddl", "maintenance"}),
    "manual": frozenset({"read", "dml", "ddl"}),
}

# Categories of a failure by SQLite's primary result code. SQLITE_ERROR, the
# generic one, is told apart by the start of its sentence below.
_CATEGORIES: dict[int, str] = {
    sqlite3.SQLITE_AUTH: "permission",
    sqlite3.SQLITE_PERM: "permission",
    sqlite3.SQLITE_READONLY: "read_only",
    sqlite3.SQLITE_CONSTRAINT: "data",
    sqlite3.SQLITE_MISMATCH: "data",
    sqlite3.SQLITE_TOOBIG: "resource",
    sqlite3.SQLITE_BUSY: "resource",
    sqlite3.SQLITE_LOCKED: "resource",
    sqlite3.SQLITE_FULL: "resource",
    sqlite3.SQLITE_NOMEM: "resource",
}
_GENERIC_ERRORS = (
    ("no such table", "missing_object"),
    ("no such column", "missing_object"),
    ("no such index", "missing_object"),
    ("no such view", "missing_object"),
    ("no such function", "missing_object"),
    ("no such module", "missing_object"),
    ("near ", "syntax"),
    ("incomplete input", "syntax"),
    ("unrecognized token", "syntax"),
    ("not authorized", "permission"),
)
# Failures after which SQLite has rolled the open transaction back by itself.
_ENDS_TRANSACTION = frozenset(
    {sqlite3.SQLITE_FULL, sqlite3.SQLITE_IOERR, sqlite3.SQLITE_NOMEM, sqlite3.SQLITE_CORRUPT}
)

_UNSAFE = {ord(char): None for char in ("\r", "\n", "\t", "\x00")}


def _safe_text(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    return value.translate(_UNSAFE).strip()[:MAX_MESSAGE_CHARS] or fallback


def _code(exc: BaseException) -> int:
    return (getattr(exc, "sqlite_errorcode", None) or 0) & 0xFF


def diagnostic_of(exc: sqlite3.Error, *, cancelled: bool, timed_out: bool) -> QueryDiagnostic:
    """A failure reduced to what may be shown (D64).

    SQLite's own sentence is passed on, as a server's is: it is about the
    statement, and a file has no password for it to give away.
    """
    code = _code(exc)
    if code == sqlite3.SQLITE_INTERRUPT:
        return QueryDiagnostic(
            code="SQLITE_INTERRUPT",
            category="timeout" if timed_out and not cancelled else "cancelled",
            message=say("The statement ran out of time")
            if timed_out and not cancelled
            else say("Cancelled"),
        )
    text = str(exc)
    category = _CATEGORIES.get(code)
    if category is None:
        lowered = text.lower()
        category = next(
            (found for start, found in _GENERIC_ERRORS if lowered.startswith(start)), "unknown"
        )
    return QueryDiagnostic(
        code=getattr(exc, "sqlite_errorname", None) or type(exc).__name__,
        category=category,  # type: ignore[arg-type]  # the tables above hold the union's members
        message=_safe_text(text, say("The statement could not be run")),
    )


def _status(diagnostic: QueryDiagnostic) -> StatementStatus:
    if diagnostic.category == "cancelled":
        return "cancelled"
    if diagnostic.category == "timeout":
        return "timed_out"
    return "failed"


def _values(request: QueryRequest, statement: PreparedStatement) -> dict[str, str | None]:
    """The bindings one statement uses, by name; SQLite binds `:name` itself."""
    given = {parameter.name: parameter.value for parameter in request.parameters}
    return {name: given.get(name) for name in statement.parameters}


def check_search_path(search_path: list[str]) -> None:
    """A file has one schema here (D248); naming another is a mistake to say."""
    for name in search_path:
        if name and name != SCHEMA:
            raise AdapterError(
                "config", say("This connection has no schema called {name}", name=name)
            )


def _category_of(values: list[Any]) -> tuple[str, TypeCategory]:
    """What a result column holds, by the classes of what came back (D250)."""
    classes = {type(value) for value in values if value is not None}
    if not classes:
        return "", "other"
    if classes <= {int}:
        return "INTEGER", "number"
    if classes <= {int, float}:
        return "REAL", "number"
    if classes <= {str}:
        return "TEXT", "string"
    if all(issubclass(kind, bytes) for kind in classes):
        return "BLOB", "binary"
    return "", "other"


class ResultTooLarge(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _Outcome:
    """What one statement did, read inside the worker thread."""

    def __init__(self) -> None:
        self.description: list[str] | None = None
        self.rows: list[tuple[Any, ...]] = []
        self.truncated = False
        self.rowcount = -1


def _execute(
    connection: sqlite3.Connection, text: str, values: dict[str, str | None], max_rows: int
) -> _Outcome:
    outcome = _Outcome()
    cursor = connection.execute(text, values)
    if cursor.description is not None:
        outcome.description = [str(column[0]) for column in cursor.description]
        fetched = cursor.fetchmany(max_rows + 1)
        outcome.truncated = len(fetched) > max_rows
        outcome.rows = fetched[:max_rows]
        # Rows past the ceiling are not read, and the statement is finished
        # with: a write with RETURNING is carried out whole by SQLite either way.
        cursor.close()
    outcome.rowcount = cursor.rowcount
    return outcome


class _Statements:
    """Running the statements of one request on one handle."""

    def __init__(self, request: QueryRequest) -> None:
        self._request = request
        self._handle: Handle | None = None
        self._cancelled = False
        self._run_bytes = 0
        self._run_results = 0
        self.mutating = 0
        self.ddl = 0
        self.affected = 0
        self.targets: list[str] = []
        self.effect = SchemaEffect()
        self.failed = False
        # A failure after which the transaction is no longer the one begun.
        self.ended = False

    async def cancel(self) -> None:
        """Stop what this run is running; it reports the outcome itself (D64)."""
        self._cancelled = True
        if self._handle is not None:
            self._handle.stop()

    async def _statements(
        self, handle: Handle, script: PreparedScript, started: float
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
            finished = await self._one(handle, statement, limits)
            yield finished
            stopped = finished.status != "succeeded"
            self.failed = self.failed or stopped

    async def _one(
        self, handle: Handle, statement: PreparedStatement, limits: QueryLimits
    ) -> StatementFinished:
        if statement.kind not in _ADMITTED[self._request.mode]:
            message = (
                say("A {kind} statement cannot run in a read", kind=statement.kind)
                if self._request.mode == "read"
                else say("A {kind} statement is not run here", kind=statement.kind)
            )
            return StatementFinished(
                ordinal=statement.ordinal,
                status="failed",
                duration_ms=0,
                diagnostic=QueryDiagnostic(
                    code="dp_not_admitted", category="read_only", message=message
                ),
            )
        began = time.monotonic()
        values = _values(self._request, statement)
        try:
            outcome = await handle.call(
                partial(
                    _execute, text=statement.text, values=values, max_rows=limits.max_result_rows
                ),
                seconds=limits.statement_timeout_seconds,
            )
            result = None if outcome.description is None else self._materialise(outcome, limits)
        except ResultTooLarge as refusal:
            return StatementFinished(
                ordinal=statement.ordinal,
                status="succeeded",
                duration_ms=self._since(began),
                diagnostic=QueryDiagnostic(
                    code="result_too_large", category="resource", message=refusal.message
                ),
            )
        except sqlite3.Error as exc:
            diagnostic = diagnostic_of(
                exc, cancelled=self._cancelled, timed_out=handle.timed_out
            )
            if _code(exc) in _ENDS_TRANSACTION:
                self.ended = True
            return StatementFinished(
                ordinal=statement.ordinal,
                status=_status(diagnostic),
                duration_ms=self._since(began),
                diagnostic=diagnostic,
            )
        affected = outcome.rowcount if statement.kind == "dml" and outcome.rowcount >= 0 else None
        self.mutating += 1 if statement.kind in ("dml", "ddl") else 0
        self.affected += affected or 0
        for target in statement.targets:
            if target not in self.targets:
                self.targets.append(target)
        effect: SchemaEffect | None = None
        if statement.kind == "ddl":
            self.ddl += 1
            effect = effect_of(statement.text)
            self.effect = self.effect.with_(effect)
        return StatementFinished(
            ordinal=statement.ordinal,
            status="succeeded",
            duration_ms=self._since(began),
            row_count=None if result is None else len(result.rows),
            affected_rows=affected,
            result=result,
            effect=effect,
        )

    def _materialise(self, outcome: _Outcome, limits: QueryLimits) -> MaterialisedResult:
        """Every row once, within the ceilings D64 states, names kept apart."""
        names = outcome.description or []
        columns: list[ResultColumn] = []
        for position, name in enumerate(names):
            sql, category = _category_of([row[position] for row in outcome.rows])
            columns.append(
                ResultColumn(
                    id=str(position), name=name, type=ColumnType(sql=sql, category=category)
                )
            )
        rows: list[list[str | None]] = []
        used = 0
        for raw in outcome.rows:
            row: list[str | None] = []
            for column, value in zip(columns, raw, strict=True):
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
        return MaterialisedResult(
            columns=columns, rows=rows, truncated=outcome.truncated, bytes_used=used
        )

    @staticmethod
    def _since(began: float) -> int:
        return int((time.monotonic() - began) * 1000)


def _run(connection: sqlite3.Connection, statement: str) -> None:
    connection.execute(statement)


def _end(connection: sqlite3.Connection, *, commit: bool) -> None:
    if connection.in_transaction:
        connection.execute("COMMIT" if commit else "ROLLBACK")


class SqliteExecution(_Statements):
    """One run that opens its own transaction and ends it.

    A read runs on a connection that cannot write, in a transaction so that its
    statements see one state of the file. Auto-commit makes the run one
    transaction, structure changes included, committed only when every
    statement succeeded; a maintenance command runs alone with none (D206).
    """

    def __init__(self, session: SqliteSession, request: QueryRequest) -> None:
        super().__init__(request)
        self._session = session

    def events(self) -> AsyncIterator[QueryEvent]:
        return self._events()

    async def _events(self) -> AsyncIterator[QueryEvent]:
        script = prepare(self._request.text)
        started = time.monotonic()
        reading = self._request.mode == "read"
        kinds = [statement.kind for statement in script.statements]
        outside = not reading and kinds == ["maintenance"]
        check_search_path(self._request.search_path)
        handle = await self._session.handle(
            writes=not reading, fallback_message=N_("The query could not be run")
        )
        self._handle = handle
        try:
            if not outside:
                await handle.call(lambda connection: _run(connection, "BEGIN"))
            async for event in self._statements(handle, script, started):
                yield event
            if not outside:
                commit = not self.failed and not reading
                await handle.call(lambda connection: _end(connection, commit=commit))
        except AdapterError:
            raise
        except sqlite3.Error as exc:
            error_kind, message = classify(exc, fallback_message=N_("The query could not be run"))
            raise AdapterError(error_kind, message) from None
        finally:
            self._handle = None
            # Closing rolls back whatever was left open.
            await handle.close()


class _BoundExecution(_Statements):
    """One run inside a transaction somebody else opened, and will end."""

    def __init__(self, request: QueryRequest, handle: Handle) -> None:
        super().__init__(request)
        self._held = handle

    def events(self) -> AsyncIterator[QueryEvent]:
        return self._events()

    async def _events(self) -> AsyncIterator[QueryEvent]:
        script = prepare(self._request.text)
        started = time.monotonic()
        # A Stop pressed during the previous run is not this one's.
        self._held.resume()
        self._handle = self._held
        try:
            async for event in self._statements(self._held, script, started):
                yield event
            ended = not await self._held.call(lambda connection: connection.in_transaction)
            self.ended = self.ended or ended
        except AdapterError:
            raise
        except sqlite3.Error as exc:
            error_kind, message = classify(exc, fallback_message=N_("The query could not be run"))
            raise AdapterError(error_kind, message) from None
        finally:
            self._handle = None


class _Rehearsal:
    """A change carried out and undone, described in SQLite's own terms (D66).

    The caller opens the transaction — its own, or a savepoint inside the one
    somebody is holding — and rolls it back afterwards.
    """

    def __init__(self, request: QueryRequest) -> None:
        self._request = request

    async def carry_out(self, handle: Handle) -> QueryRehearsal:
        script = prepare(self._request.text)
        rehearsed: list[RehearsedStatement] = []
        effect = SchemaEffect()
        blocked = False
        stopped = False
        for statement in script.statements:
            if stopped or statement.kind not in ("dml", "ddl"):
                # A read changes nothing and so says nothing about the change.
                rehearsed.append(RehearsedStatement(ordinal=statement.ordinal, outcome="not_run"))
                continue
            values = _values(self._request, statement)
            try:
                outcome = await handle.call(
                    partial(_execute, text=statement.text, values=values, max_rows=0),
                    seconds=self._request.limits.statement_timeout_seconds,
                )
            except sqlite3.Error as exc:
                waited = _code(exc) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
                blocked = blocked or waited
                rehearsed.append(
                    RehearsedStatement(
                        ordinal=statement.ordinal,
                        outcome="blocked" if waited else "failed",
                        diagnostic=QueryDiagnostic(
                            code="SQLITE_BUSY",
                            category="resource",
                            message=say(
                                "Something else is holding this open; the change was not rehearsed"
                            ),
                        )
                        if waited
                        else diagnostic_of(exc, cancelled=False, timed_out=handle.timed_out),
                    )
                )
                stopped = True
                continue
            rehearsed.append(
                RehearsedStatement(
                    ordinal=statement.ordinal,
                    outcome="ok",
                    affected_rows=outcome.rowcount if statement.kind == "dml" else None,
                )
            )
            if statement.kind == "ddl":
                effect = effect.with_(effect_of(statement.text))
        return QueryRehearsal(
            statements=rehearsed,
            blocked=blocked,
            runnable=not blocked and not stopped,
            effect=effect,
        )


class SqliteTransaction:
    """One transaction, open across requests, holding its connection (D66).

    A failed statement leaves a SQLite transaction open and usable; a failure
    after which SQLite rolled it back by itself breaks it.
    """

    def __init__(self, session: SqliteSession, context: TransactionContext) -> None:
        self._session = session
        self._context = context
        self._handle: Handle | None = None
        self._open = False
        self._broken = False
        self._statements = 0
        self._mutating = 0
        self._ddl = 0
        self._affected = 0
        self._targets: list[str] = []
        self._effect = SchemaEffect()

    async def begin(self) -> None:
        check_search_path(self._context.search_path)
        handle = await self._session.handle(
            writes=True, fallback_message=N_("The transaction could not be opened")
        )
        try:
            await handle.call(lambda connection: _run(connection, "BEGIN"))
        except BaseException as exc:
            await handle.close()
            if isinstance(exc, sqlite3.Error):
                error_kind, message = classify(
                    exc, fallback_message=N_("The transaction could not be opened")
                )
                raise AdapterError(error_kind, message) from None
            raise
        self._handle = handle
        self._open = True

    def execute(self, request: QueryRequest) -> _BoundExecution:
        handle = self._handle
        if handle is None or not self._open:
            raise AdapterError("unknown", say("This transaction is no longer open"))
        if self._broken:
            raise AdapterError("unknown", say("This transaction failed and can only be rolled back"))
        # A statement's time limit is the transaction's, as PostgreSQL's is.
        limits = request.limits.model_copy(
            update={"statement_timeout_seconds": self._context.statement_timeout_seconds}
        )
        return _BoundExecution(request.model_copy(update={"limits": limits, "mode": "manual"}), handle)

    async def rehearse(self, request: QueryRequest) -> QueryRehearsal:
        """Inside a savepoint of the open transaction, rolled back to it.

        Inside rather than beside: a rehearsal on a second connection would
        wait behind this transaction's own lock on the file.
        """
        handle = self._handle
        if handle is None or not self._open:
            raise AdapterError("unknown", say("This transaction is no longer open"))
        try:
            await handle.call(lambda connection: _run(connection, "SAVEPOINT dp_rehearsal"))
            try:
                return await _Rehearsal(request).carry_out(handle)
            finally:
                handle.resume()
                await handle.call(lambda connection: _run(connection, "ROLLBACK TO dp_rehearsal"))
                await handle.call(lambda connection: _run(connection, "RELEASE dp_rehearsal"))
        except sqlite3.Error as exc:
            error_kind, message = classify(
                exc, fallback_message=N_("The change could not be rehearsed")
            )
            raise AdapterError(error_kind, message) from None

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
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            handle.resume()
            await handle.call(lambda connection: _end(connection, commit=commit))
        except sqlite3.Error as exc:
            error_kind, message = classify(
                exc, fallback_message=N_("The transaction could not be ended")
            )
            raise AdapterError(error_kind, message) from None
        finally:
            await handle.close()


class SqliteQuery:
    """A SQLite file as a source that accepts complete SQL (D62)."""

    def __init__(self, session: SqliteSession) -> None:
        self._session = session

    def profile(self) -> QueryProfile:
        return QueryProfile(
            dialect="sqlite",
            parameter_syntax="named_colon",
            statement_modes=["read", "auto_commit", "manual"],
            supports_cancel=True,
            default_timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            max_timeout_seconds=MAX_TIMEOUT_SECONDS,
        )

    def prepare(self, text: str) -> PreparedScript:
        return prepare(text)

    def open(self, request: QueryRequest) -> SqliteExecution:
        return SqliteExecution(self._session, request)

    async def rehearse(self, request: QueryRequest) -> QueryRehearsal:
        """Carry the change out on a connection of its own, and undo it (D66)."""
        check_search_path(request.search_path)
        handle = await self._session.handle(
            writes=True,
            busy_seconds=REHEARSAL_BUSY_SECONDS,
            fallback_message=N_("The change could not be rehearsed"),
        )
        try:
            await handle.call(lambda connection: _run(connection, "BEGIN"))
            return await _Rehearsal(request).carry_out(handle)
        except sqlite3.Error as exc:
            error_kind, message = classify(
                exc, fallback_message=N_("The change could not be rehearsed")
            )
            raise AdapterError(error_kind, message) from None
        finally:
            # Closing a connection rolls back what it left open.
            await handle.close()

    async def begin(self, context: TransactionContext) -> SqliteTransaction:
        transaction = SqliteTransaction(self._session, context)
        await transaction.begin()
        return transaction
