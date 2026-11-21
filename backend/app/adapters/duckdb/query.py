"""Running SQL somebody wrote on a DuckDB file (D62, D393, D394).

Structure changes are transactional in DuckDB, so a run is one transaction
whatever it holds, a held transaction may change structure, and a change is
rehearsed by carrying it out and rolling it back, as on PostgreSQL. Only
maintenance runs outside a transaction. Any failure aborts a DuckDB
transaction, and there are no savepoints.

A read is its class and a transaction rolled back at the end: DuckDB has no
read-only switch for one connection (D393). Every connection is the catalog's,
locked to the owner's home (D388).
"""

import json
import time
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from datetime import time as clock
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Any
from uuid import UUID

import duckdb

from app.adapters.duckdb.inspection import list_schemas
from app.adapters.duckdb.session import DuckdbSession, Handle, Reading, classify
from app.adapters.duckdb.sql import SQL, quoted_name
from app.adapters.duckdb.statements import (
    DEFAULT_SCHEMA,
    effect_of,
    prepare,
    returns_rows,
    sentence,
    statement_type,
)
from app.adapters.duckdb.types import build_column_type, shown
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
from app.adapters.relation import ColumnType
from app.core.translation import N_, say

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300

_ADMITTED: dict[str, frozenset[str]] = {
    "read": frozenset({"read"}),
    "auto_commit": frozenset({"read", "dml", "ddl", "maintenance"}),
    "manual": frozenset({"read", "dml", "ddl"}),
}

# Categories of a failure by the class DuckDB raises it as.
_CATEGORIES: list[tuple[type[BaseException], str]] = [
    (duckdb.ParserException, "syntax"),
    (duckdb.SyntaxException, "syntax"),
    (duckdb.CatalogException, "missing_object"),
    (duckdb.BinderException, "missing_object"),
    (duckdb.PermissionException, "permission"),
    (duckdb.ConstraintException, "data"),
    (duckdb.ConversionException, "data"),
    (duckdb.OutOfRangeException, "data"),
    (duckdb.InvalidInputException, "data"),
    (duckdb.TypeMismatchException, "data"),
    (duckdb.DependencyException, "data"),
    (duckdb.OutOfMemoryException, "resource"),
    (duckdb.IOException, "resource"),
    (duckdb.TransactionException, "resource"),
]


class _Unreadable(Exception):
    """A result the driver cannot hand over (D394), with the sentence to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ResultTooLarge(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def redacted(text: str, home: Path) -> str:
    """The owner's home written as `~`, the one path a sentence may name (D394)."""
    for spelt in {str(home), home.as_posix()}:
        text = text.replace(spelt, "~")
    return text


def diagnostic_of(
    exc: BaseException, home: Path, *, cancelled: bool, timed_out: bool
) -> QueryDiagnostic:
    """A failure reduced to what may be shown (D64, D394)."""
    if isinstance(exc, duckdb.InterruptException):
        late = timed_out and not cancelled
        return QueryDiagnostic(
            code="INTERRUPT",
            category="timeout" if late else "cancelled",
            message=say("The statement ran out of time") if late else say("Cancelled"),
        )
    category = next((found for kind, found in _CATEGORIES if isinstance(exc, kind)), "unknown")
    return QueryDiagnostic(
        code=type(exc).__name__,
        category=category,  # type: ignore[arg-type]  # the table above holds the union's members
        message=redacted(sentence(str(exc)), home),
    )


def _status(diagnostic: QueryDiagnostic) -> StatementStatus:
    if diagnostic.category == "cancelled":
        return "cancelled"
    if diagnostic.category == "timeout":
        return "timed_out"
    return "failed"


def _values(request: QueryRequest, statement: PreparedStatement) -> dict[str, str | None]:
    """The bindings one statement uses, by name; DuckDB binds `$name` itself."""
    given = {parameter.name: parameter.value for parameter in request.parameters}
    return {name: given.get(name) for name in statement.parameters}


def search_path_statement(reading: Reading, search_path: list[str]) -> str | None:
    """`SET search_path` for the names given, each found among the file's schemas.

    The value is a string DuckDB reads as a list of names, so each name is
    quoted as a name and the whole as a string; no name reaches it unchecked.
    """
    wanted = [name for name in search_path if name]
    if not wanted:
        return None
    known = set(list_schemas(reading))
    for name in wanted:
        if name not in known:
            raise AdapterError(
                "config", say("This connection has no schema called {name}", name=name)
            )
    listed = ",".join(quoted_name(name) for name in wanted)
    return "SET search_path = '" + listed.replace("'", "''") + "'"


def _first_schema(search_path: list[str]) -> str:
    return next((name for name in search_path if name), DEFAULT_SCHEMA)


def _python_text(value: Any) -> str | None:
    """A value the driver handed over, as text: a result that is not a read (D394)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes | bytearray | memoryview):
        return "0x" + bytes(value).hex().upper()
    if isinstance(value, datetime | date | clock | timedelta | UUID):
        return str(value)
    if isinstance(value, list | tuple | dict):
        return json.dumps(_jsonable(value), ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, bool | int | str):
        return value
    return _python_text(value)


class _Outcome:
    """What one statement did, read inside the worker thread."""

    def __init__(self) -> None:
        self.types: list[ColumnType] = []
        self.names: list[str] | None = None
        self.rows: list[list[str | None]] = []
        self.truncated = False
        self.affected: int | None = None


def _execute(
    connection: duckdb.DuckDBPyConnection,
    statement: PreparedStatement,
    values: dict[str, str | None],
    max_rows: int,
) -> _Outcome:
    outcome = _Outcome()
    params = values or None
    if statement.kind == "read" and statement_type(statement.text) == "SELECT":
        # Bound once for its columns, which does not run it, then run wrapped
        # so that every value is DuckDB's own text (D394).
        bound = connection.sql(statement.text, params=params)
        outcome.names = list(bound.columns)
        outcome.types = [build_column_type(str(kind)) for kind in bound.types]
        listed = SQL(", ").join(
            shown(SQL(f"#{position + 1}"), kind) for position, kind in enumerate(outcome.types)
        )
        # The person's own complete statement (D62); only the wrapper is ours.
        head = SQL("SELECT {} FROM (\n").format(listed).text()
        wrapped = f"{head}{statement.text}\n) AS dp_result LIMIT {max_rows + 1}"  # noqa: S608
        fetched = connection.execute(wrapped, params).fetchall()
        outcome.truncated = len(fetched) > max_rows
        outcome.rows = [list(row) for row in fetched[:max_rows]]
        return outcome
    cursor = connection.execute(statement.text, params)
    description = cursor.description
    if description is None:
        return outcome
    names = [str(column[0]) for column in description]
    if statement.kind in ("dml", "ddl", "maintenance") and not returns_rows(statement.text):
        # DuckDB answers a change with one `Count`: its affected rows.
        row = cursor.fetchone()
        if statement.kind == "dml" and names == ["Count"] and row is not None:
            outcome.affected = int(row[0])
        return outcome
    try:
        fetched = cursor.fetchmany(max_rows + 1)
    except duckdb.InvalidInputException as exc:
        if "pytz" in str(exc):
            raise _Unreadable(
                say("This result holds a moment with a time zone; select it with SELECT to see it")
            ) from None
        raise
    outcome.names = names
    outcome.types = [build_column_type(str(column[1])) for column in description]
    outcome.truncated = len(fetched) > max_rows
    outcome.rows = [[_python_text(value) for value in row] for row in fetched[:max_rows]]
    return outcome


class _Statements:
    """Running the statements of one request on one handle."""

    def __init__(self, request: QueryRequest, home: Path) -> None:
        self._request = request
        self._home = home
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
        # A statement failed against DuckDB, which aborts the transaction (D393).
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

    def _not_admitted(self, statement: PreparedStatement) -> StatementFinished | None:
        if statement.refused is not None:
            message = statement.refused
        elif statement.kind not in _ADMITTED[self._request.mode]:
            message = (
                say("A {kind} statement cannot run in a read", kind=statement.kind)
                if self._request.mode == "read"
                else say("A {kind} statement is not run here", kind=statement.kind)
            )
        else:
            return None
        return StatementFinished(
            ordinal=statement.ordinal,
            status="failed",
            duration_ms=0,
            diagnostic=QueryDiagnostic(code="dp_not_admitted", category="read_only", message=message),
        )

    async def _one(
        self, handle: Handle, statement: PreparedStatement, limits: QueryLimits
    ) -> StatementFinished:
        refused = self._not_admitted(statement)
        if refused is not None:
            return refused
        began = time.monotonic()
        values = _values(self._request, statement)
        try:
            outcome = await handle.call(
                partial(
                    _execute, statement=statement, values=values, max_rows=limits.max_result_rows
                ),
                seconds=limits.statement_timeout_seconds,
            )
            result = None if outcome.names is None else self._materialise(outcome, limits)
        except (ResultTooLarge, _Unreadable) as refusal:
            return StatementFinished(
                ordinal=statement.ordinal,
                status="succeeded",
                duration_ms=self._since(began),
                diagnostic=QueryDiagnostic(
                    code="result_too_large", category="resource", message=refusal.message
                ),
            )
        except duckdb.Error as exc:
            self.ended = True
            diagnostic = diagnostic_of(
                exc, self._home, cancelled=self._cancelled, timed_out=handle.timed_out
            )
            return StatementFinished(
                ordinal=statement.ordinal,
                status=_status(diagnostic),
                duration_ms=self._since(began),
                diagnostic=diagnostic,
            )
        affected = outcome.affected if statement.kind == "dml" else None
        self.mutating += 1 if statement.kind in ("dml", "ddl") else 0
        self.affected += affected or 0
        for target in statement.targets:
            if target not in self.targets:
                self.targets.append(target)
        effect: SchemaEffect | None = None
        if statement.kind == "ddl":
            self.ddl += 1
            effect = effect_of(statement.text, _first_schema(self._request.search_path))
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
        names = outcome.names or []
        columns = [
            ResultColumn(id=str(position), name=name, type=outcome.types[position])
            for position, name in enumerate(names)
        ]
        used = 0
        for row in outcome.rows:
            for column, cell in zip(columns, row, strict=True):
                size = 0 if cell is None else len(cell.encode())
                if size > limits.max_cell_bytes:
                    raise ResultTooLarge(
                        say("A value in {column} is larger than one cell may be", column=column.name)
                    )
                used += size
                if used > limits.max_result_bytes:
                    raise ResultTooLarge(say("This result is larger than one result may be"))
        self._run_bytes += used
        self._run_results += 1
        if self._run_results > limits.max_run_results:
            raise ResultTooLarge(say("This run produced more results than one run may hold"))
        if self._run_bytes > limits.max_run_bytes:
            raise ResultTooLarge(say("This run produced more data than one run may hold"))
        return MaterialisedResult(
            columns=columns, rows=outcome.rows, truncated=outcome.truncated, bytes_used=used
        )

    @staticmethod
    def _since(began: float) -> int:
        return int((time.monotonic() - began) * 1000)


def _run(connection: duckdb.DuckDBPyConnection, statement: str) -> None:
    connection.execute(statement)


def _prepare_session(connection: duckdb.DuckDBPyConnection, search_path: list[str]) -> None:
    statement = search_path_statement(Reading(connection), search_path)
    if statement is not None:
        connection.execute(statement)


def _end(connection: duckdb.DuckDBPyConnection, *, commit: bool) -> None:
    try:
        connection.execute("COMMIT" if commit else "ROLLBACK")
    except duckdb.TransactionException:
        # Nothing was open: a failed statement may have ended it already.
        pass


async def opened(session: DuckdbSession, search_path: list[str], fallback: str) -> Handle:
    """A handle with the search path set, closed again if setting it fails."""
    handle = await session.handle()
    try:
        await handle.call(partial(_prepare_session, search_path=search_path))
    except BaseException as exc:
        await handle.close()
        if isinstance(exc, duckdb.Error):
            error_kind, message = classify(exc, fallback_message=fallback)
            raise AdapterError(error_kind, message) from None
        raise
    return handle


class DuckdbExecution(_Statements):
    """One run that opens its own transaction and ends it.

    A read is rolled back whatever it did; auto-commit makes the run one
    transaction, structure changes included, committed only when every
    statement succeeded; a maintenance command runs alone with none (D206).
    """

    def __init__(self, session: DuckdbSession, request: QueryRequest) -> None:
        super().__init__(request, session.home)
        self._session = session

    def events(self) -> AsyncIterator[QueryEvent]:
        return self._events()

    async def _events(self) -> AsyncIterator[QueryEvent]:
        script = prepare(self._request.text)
        started = time.monotonic()
        reading = self._request.mode == "read"
        kinds = [statement.kind for statement in script.statements]
        outside = not reading and kinds == ["maintenance"]
        handle = await opened(
            self._session, self._request.search_path, N_("The query could not be run")
        )
        self._handle = handle
        try:
            if not outside:
                await handle.call(lambda connection: _run(connection, "BEGIN"))
            async for event in self._statements(handle, script, started):
                yield event
            if not outside:
                commit = not self.failed and not reading
                # A Stop stops statements; ending the transaction is ours.
                handle.resume()
                await handle.call(lambda connection: _end(connection, commit=commit))
        except AdapterError:
            raise
        except duckdb.Error as exc:
            error_kind, message = classify(exc, fallback_message=N_("The query could not be run"))
            raise AdapterError(error_kind, message) from None
        finally:
            self._handle = None
            # Closing rolls back whatever was left open.
            await handle.close()


class _BoundExecution(_Statements):
    """One run inside a transaction somebody else opened, and will end."""

    def __init__(self, request: QueryRequest, handle: Handle, home: Path) -> None:
        super().__init__(request, home)
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
        finally:
            self._handle = None


class _Rehearsal:
    """A change carried out and undone, described in DuckDB's own terms (D66)."""

    def __init__(self, request: QueryRequest, home: Path) -> None:
        self._request = request
        self._home = home

    async def carry_out(self, handle: Handle) -> QueryRehearsal:
        script = prepare(self._request.text)
        rehearsed: list[RehearsedStatement] = []
        effect = SchemaEffect()
        blocked = False
        stopped = False
        schema = _first_schema(self._request.search_path)
        for statement in script.statements:
            if stopped or statement.kind not in ("dml", "ddl") or statement.refused is not None:
                # A read changes nothing and so says nothing about the change.
                rehearsed.append(RehearsedStatement(ordinal=statement.ordinal, outcome="not_run"))
                continue
            values = _values(self._request, statement)
            try:
                outcome = await handle.call(
                    partial(_execute, statement=statement, values=values, max_rows=0),
                    seconds=self._request.limits.statement_timeout_seconds,
                )
            except duckdb.Error as exc:
                waited = isinstance(exc, duckdb.TransactionException) and "onflict" in str(exc)
                blocked = blocked or waited
                rehearsed.append(
                    RehearsedStatement(
                        ordinal=statement.ordinal,
                        outcome="blocked" if waited else "failed",
                        diagnostic=diagnostic_of(
                            exc, self._home, cancelled=False, timed_out=handle.timed_out
                        ),
                    )
                )
                stopped = True
                continue
            rehearsed.append(
                RehearsedStatement(
                    ordinal=statement.ordinal,
                    outcome="ok",
                    affected_rows=outcome.affected if statement.kind == "dml" else None,
                )
            )
            if statement.kind == "ddl":
                effect = effect.with_(effect_of(statement.text, schema))
        return QueryRehearsal(
            statements=rehearsed,
            blocked=blocked,
            runnable=not blocked and not stopped,
            effect=effect,
        )


class DuckdbTransaction:
    """One transaction, open across requests, holding its connection (D66, D393).

    Holding the connection holds the file: no other program can open it until
    the transaction ends. Any failed statement aborts a DuckDB transaction, so
    it is then broken and can only be rolled back.
    """

    def __init__(self, session: DuckdbSession, context: TransactionContext) -> None:
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
        fallback = N_("The transaction could not be opened")
        handle = await opened(self._session, self._context.search_path, fallback)
        try:
            await handle.call(lambda connection: _run(connection, "BEGIN"))
        except BaseException as exc:
            await handle.close()
            if isinstance(exc, duckdb.Error):
                error_kind, message = classify(exc, fallback_message=fallback)
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
        bound = request.model_copy(
            update={
                "limits": limits,
                "mode": "manual",
                "search_path": self._context.search_path,
            }
        )
        return _BoundExecution(bound, handle, self._session.home)

    async def rehearse(self, request: QueryRequest) -> QueryRehearsal:
        """Refused: DuckDB has no savepoints to undo a change back to (D393)."""
        raise AdapterError(
            "config",
            say(
                "DuckDB has no savepoints, so a change cannot be tried out inside a held "
                "transaction; run it in auto-commit, where it is tried out first"
            ),
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
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            handle.resume()
            await handle.call(lambda connection: _end(connection, commit=commit))
        except duckdb.Error as exc:
            error_kind, message = classify(
                exc, fallback_message=N_("The transaction could not be ended")
            )
            raise AdapterError(error_kind, message) from None
        finally:
            await handle.close()


class DuckdbQuery:
    """A DuckDB file as a source that accepts complete SQL (D62)."""

    def __init__(self, session: DuckdbSession) -> None:
        self._session = session

    def profile(self) -> QueryProfile:
        return QueryProfile(
            dialect="duckdb",
            parameter_syntax="named_dollar",
            statement_modes=["read", "auto_commit", "manual"],
            supports_cancel=True,
            default_timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            max_timeout_seconds=MAX_TIMEOUT_SECONDS,
        )

    def prepare(self, text: str) -> PreparedScript:
        return prepare(text)

    def open(self, request: QueryRequest) -> DuckdbExecution:
        return DuckdbExecution(self._session, request)

    async def rehearse(self, request: QueryRequest) -> QueryRehearsal:
        """Carry the change out on a connection of its own, and undo it (D66)."""
        fallback = N_("The change could not be rehearsed")
        handle = await opened(self._session, request.search_path, fallback)
        try:
            await handle.call(lambda connection: _run(connection, "BEGIN"))
            return await _Rehearsal(request, self._session.home).carry_out(handle)
        except duckdb.Error as exc:
            error_kind, message = classify(exc, fallback_message=fallback)
            raise AdapterError(error_kind, message) from None
        finally:
            # Closing a connection rolls back what it left open.
            await handle.close()

    async def begin(self, context: TransactionContext) -> DuckdbTransaction:
        transaction = DuckdbTransaction(self._session, context)
        await transaction.begin()
        return transaction
