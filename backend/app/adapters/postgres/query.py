"""Running SQL somebody wrote, inside a transaction the database enforces.

D62: classification chooses the wording and the policy; it is not the defence.
The defence is a PostgreSQL `READ ONLY` transaction with a local statement
timeout and a search path composed from names the server itself confirmed. What
that guarantees is exact — no persistent database change that PostgreSQL
read-only mode admits — and no more: a function may still send mail or reach
outside the database, and restricting that is the database role's job.
"""

import time
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.string import TextLoader
from psycopg_pool import PoolTimeout

from app.adapters.cells import encode_cell
from app.adapters.postgres.column_type import build_column_type
from app.adapters.postgres.effects import effect_of
from app.adapters.postgres.session import PostgresSession, classify
from app.adapters.postgres.statements import bind, prepare
from app.adapters.protocol import AdapterError
from app.adapters.query import (
    MaterialisedResult,
    PreparedScript,
    PreparedStatement,
    QueryDiagnostic,
    QueryEvent,
    QueryExecution,
    QueryLimits,
    QueryNotice,
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

# What a diagnostic's category is, by SQLSTATE. Everything unlisted is
# "unknown", which is honest: a category invented per code would be a guess
# with a confident face.
_CATEGORIES: dict[str, str] = {
    "42601": "syntax",
    "42P01": "missing_object",
    "42703": "missing_object",
    "42883": "missing_object",
    "42P02": "missing_object",
    "3F000": "missing_object",
    "42501": "permission",
    # The server could not work out what a parameter is. The SQL author
    # resolves that with a cast, which the hint below says.
    "42P18": "data",
    "25006": "read_only",
    "0A000": "read_only",
    "57014": "cancelled",
}

# A message from the server is one line of text, not a document.
MAX_MESSAGE_CHARS = 500

# How long one statement may run, and how long a person may ask for. These are
# PostgreSQL's policy rather than the platform's, so the source states them and
# the caller clamps what was asked for against them (D64).
DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300

_UNSAFE = {ord(char): None for char in ("\r", "\n", "\t", "\x00")}


def _safe_text(value: str | None, fallback: str) -> str:
    """One line, bounded, with control characters taken out."""
    if not value:
        return fallback
    return value.translate(_UNSAFE).strip()[:MAX_MESSAGE_CHARS] or fallback


def _category_of(sqlstate: str | None) -> str:
    if sqlstate is None:
        return "unknown"
    named = _CATEGORIES.get(sqlstate)
    if named is not None:
        return named
    if sqlstate.startswith("22"):
        return "data"
    if sqlstate.startswith(("53", "54", "58")):
        return "resource"
    if sqlstate.startswith("42"):
        return "syntax"
    return "unknown"


def diagnostic_of(exc: psycopg.Error, *, cancelled: bool) -> QueryDiagnostic:
    """Reduce a driver error to what may be shown.

    The driver's own text carries the connection string with the password in
    it, and DETAIL and CONTEXT carry values out of the rows. What crosses is
    the code, a category, the primary message and where it happened (D64).

    A statement timeout and a cancellation are both 57014, and the server says
    which in prose only. Whether this application asked for the cancellation is
    a fact it holds, so the answer comes from that rather than from reading the
    message.
    """
    sqlstate = getattr(exc, "sqlstate", None)
    diag = getattr(exc, "diag", None)
    category = _category_of(sqlstate)
    if sqlstate == "57014":
        category = "cancelled" if cancelled else "timeout"
    position: int | None = None
    raw_position = getattr(diag, "statement_position", None)
    if raw_position is not None:
        try:
            # The server counts from one; a caret in an editor counts from nought.
            position = max(0, int(raw_position) - 1)
        except ValueError:
            position = None
    message = _safe_text(
        getattr(diag, "message_primary", None), "The statement could not be run"
    )
    if sqlstate == "57014":
        message = "Cancelled" if cancelled else "The statement ran out of time"
    return QueryDiagnostic(
        code=sqlstate or "unknown",
        category=category,  # type: ignore[arg-type]  # _category_of answers the union
        message=message,
        position=position,
        hint=_HINTS.get(sqlstate or ""),
    )


# Vetted, and only where the server's own message leaves a person stuck. Not
# a place to guess: an unhelpful hint is worse than none.
_HINTS: dict[str, str] = {
    "42P18": "Add a cast to the parameter, for example :name::date",
}


async def set_read_context(
connection: psycopg.AsyncConnection[Any],
*,
search_path: list[str],
statement_timeout_seconds: int,
local: bool = True,
) -> None:
    """Set the timeout and the schema context this run is to see.

    Every schema name is checked against the server before it reaches a
    statement, and then composed as an identifier rather than pasted in: a
    context is client-influenced text, and D2c does not stop applying
    because the statement beside it was written by a user.

    For the transaction, unless there is none: then for the session, and
    whoever set it resets it before the connection goes back to the pool.
    """
    scope = sql.SQL("SET LOCAL" if local else "SET")
    await connection.execute(
        sql.SQL("{} statement_timeout = {}").format(
            scope, sql.Literal(statement_timeout_seconds * 1000)
        )
    )
    wanted = [name for name in search_path if name]
    if not wanted:
        return
    async with connection.cursor() as cursor:
        await cursor.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)", (wanted,)
        )
        known = {str(row[0]) for row in await cursor.fetchall()}
    missing = [name for name in wanted if name not in known]
    if missing:
        raise AdapterError(
            "config",
            f"This connection has no schema called {missing[0]}",
        )
    await connection.execute(
        sql.SQL("{} search_path TO {}").format(
            scope, sql.SQL(", ").join(sql.Identifier(name) for name in wanted)
        )
    )


# What each mode admits. The database is still the rule — a read runs in a
# read-only transaction — and this is what lets a refusal name the kind of
# statement rather than leaving the server to answer for it (D66).
#
# `ddl` is admitted by class here and narrowed by vocabulary in `statements`:
# a structure change outside the closed set never reaches this, because it
# arrives already carrying the sentence that refuses it.
_ADMITTED: dict[str, frozenset[str]] = {
    "read": frozenset({"read"}),
    "auto_commit": frozenset({"read", "dml", "ddl", "maintenance"}),
    "manual": frozenset({"read", "dml", "ddl"}),
}

# How long a rehearsal waits for a lock before giving up. Short on purpose: a
# preview that queues behind somebody else's transaction is a preview that
# holds the person looking at it, and the honest answer is that it is blocked
# rather than a spinner (D66).
REHEARSAL_LOCK_TIMEOUT_SECONDS = 3

# A lock could not be taken, and a statement ran out of time. Both mean the
# rehearsal learnt nothing about the change itself.
_LOCK_NOT_AVAILABLE = "55P03"
_QUERY_CANCELLED = "57014"


async def resolve_path(
    connection: psycopg.AsyncConnection[Any], wanted: list[str]
) -> list[str]:
    """The schemas the server would look through, for an unqualified name.

    What the run asked for when it asked for anything; otherwise the server's
    own answer, because where `CREATE TABLE t` lands is a fact about the
    connection and not about the text (D66).
    """
    if wanted:
        return list(wanted)
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT current_schemas(false)")
        row = await cursor.fetchone()
    found = row[0] if row and row[0] else []
    return [str(name) for name in found]


class ResultTooLarge(Exception):
    """A statement succeeded and its result cannot be published (D64)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _Statements:
    """Running the statements of one request on a connection.

    What opens the transaction and what ends it is not here: a read opens its
    own and closes it, and a manual transaction was opened before this run and
    outlives it (D66). Cancellation is here, because what has to be reached is
    the connection the statements are on — dropping the task would leave the
    query running on the server.
    """

    def __init__(self, session: PostgresSession, request: QueryRequest) -> None:
        self._session = session
        self._request = request
        self._connection: psycopg.AsyncConnection[Any] | None = None
        self._cancelled = False
        self._notices: list[QueryNotice] = []
        self._run_bytes = 0
        self._run_results = 0
        # The schemas the server would look through, asked for once and only
        # when a structure change needs an unqualified name resolved.
        self._path: list[str] | None = None
        # What this runner has done, for a transaction to report and for a
        # commit preview to list (D66).
        self.mutating = 0
        self.ddl = 0
        self.affected = 0
        self.targets: list[str] = []
        self.effect = SchemaEffect()
        self.failed = False

    async def cancel(self) -> None:
        """Ask the server to stop, and wait for it to say what happened.

        Not optimistic: the state stays `cancelling` until the connection
        reports a terminal outcome, and a query that won the race honestly
        finishes as a success (D64).
        """
        self._cancelled = True
        connection = self._connection
        if connection is None:
            return
        try:
            await connection.cancel_safe()
        except Exception:
            # The connection has already gone, which is the outcome anyway.
            return

    async def _statements(
        self,
        connection: psycopg.AsyncConnection[Any],
        script: PreparedScript,
        started: float,
        limits: QueryLimits,
    ) -> AsyncIterator[QueryEvent]:
        stopped = False
        for statement in script.statements:
            if stopped:
                yield StatementFinished(
                    ordinal=statement.ordinal, status="not_run", duration_ms=0
                )
                continue
            if self._cancelled:
                yield StatementFinished(
                    ordinal=statement.ordinal, status="cancelled", duration_ms=0
                )
                stopped = True
                continue
            if time.monotonic() - started > limits.script_timeout_seconds:
                yield StatementFinished(
                    ordinal=statement.ordinal, status="timed_out", duration_ms=0
                )
                stopped = True
                continue
            finished = await self._one(connection, statement, limits)
            yield StatementStarted(ordinal=statement.ordinal)
            yield finished
            # The first failure stops the script; what ran before it stays
            # visible and the rest is `not_run` rather than silently missing.
            stopped = finished.status != "succeeded"
            self.failed = self.failed or stopped

    async def _one(
        self,
        connection: psycopg.AsyncConnection[Any],
        statement: PreparedStatement,
        limits: QueryLimits,
    ) -> StatementFinished:
        if statement.kind not in _ADMITTED[self._request.mode]:
            # The transaction would refuse most of these anyway; saying which
            # kind it is beats letting the database answer for the ones it
            # cannot see the point of.
            return StatementFinished(
                ordinal=statement.ordinal,
                status="failed",
                duration_ms=0,
                diagnostic=QueryDiagnostic(
                    code="dp_not_admitted",
                    category="read_only",
                    message=(
                        f"A {statement.kind} statement cannot run in a read"
                        if self._request.mode == "read"
                        else f"A {statement.kind} statement is not run here"
                    ),
                ),
            )
        self._notices = []
        began = time.monotonic()
        try:
            async with connection.cursor() as cursor:
                # The one place a statement from a client is executed as it
                # was written. That is what this capability is, and it runs
                # inside the read-only transaction opened above (D62). Its
                # parameters are bound, never written into it — and with no
                # parameters nothing is passed at all, because psycopg reads a
                # literal per-cent sign as a placeholder as soon as anything is.
                values = self._values_for(statement)
                if values is None:
                    await cursor.execute(statement.text)
                else:
                    await cursor.execute(bind(statement.text), values)
                result: MaterialisedResult | None = None
                if cursor.description is not None:
                    result = await self._materialise(connection, cursor, limits)
                # What a change touched, as the source counted it. A statement
                # that returns rows says how many came back instead (D66).
                affected = (
                    cursor.rowcount
                    if statement.kind in ("dml", "ddl") and cursor.rowcount >= 0
                    else None
                )
                self.mutating += 1 if statement.kind in ("dml", "ddl") else 0
                self.affected += affected or 0
                for target in statement.targets:
                    if target not in self.targets:
                        self.targets.append(target)
                # What this changed about the structure, worked out here rather
                # than by whoever reads the answer: only the source knows what
                # one of its node ids is made of (D66).
                effect: SchemaEffect | None = None
                if statement.kind == "ddl":
                    self.ddl += 1
                    effect = effect_of(
                        statement.text,
                        search_path=await self._effective_path(connection),
                    )
                    self.effect = self.effect.with_(effect)
                return StatementFinished(
                    ordinal=statement.ordinal,
                    status="succeeded",
                    duration_ms=self._since(began),
                    command_tag=cursor.statusmessage,
                    row_count=None if result is None else len(result.rows),
                    affected_rows=affected,
                    result=result,
                    notices=self._notices[: limits.max_messages],
                    effect=effect,
                )
        except ResultTooLarge as refusal:
            # The statement ran. Publishing what it produced is what failed,
            # and D64 keeps the two apart.
            return StatementFinished(
                ordinal=statement.ordinal,
                status="succeeded",
                duration_ms=self._since(began),
                notices=self._notices[: limits.max_messages],
                diagnostic=QueryDiagnostic(
                    code="result_too_large",
                    category="resource",
                    message=refusal.message,
                ),
            )
        except psycopg.Error as exc:
            diagnostic = diagnostic_of(exc, cancelled=self._cancelled)
            status: StatementStatus = "failed"
            if diagnostic.category == "cancelled":
                status = "cancelled"
            elif diagnostic.category == "timeout":
                status = "timed_out"
            return StatementFinished(
                ordinal=statement.ordinal,
                status=status,
                duration_ms=self._since(began),
                notices=self._notices[: limits.max_messages],
                diagnostic=diagnostic,
            )

    async def _effective_path(
        self, connection: psycopg.AsyncConnection[Any]
    ) -> list[str]:
        """The schemas the server itself would look through, for this run.

        Asked of the server when the run did not name a context, because that
        is what decides where an unqualified `CREATE TABLE t` lands. Asked once
        and only when a structure change needs it: a read never pays for it.
        """
        if self._path is None:
            self._path = await resolve_path(connection, self._request.search_path)
        return self._path

    def _values_for(self, statement: PreparedStatement) -> dict[str, str | None] | None:
        return _values_of(self._request, statement)

    async def _materialise(
        self,
        connection: psycopg.AsyncConnection[Any],
        cursor: psycopg.AsyncCursor[Any],
        limits: QueryLimits,
    ) -> MaterialisedResult:
        """Read the whole result once, within every ceiling D64 states."""
        description = cursor.description or []
        types = await self._types_of(connection, [column.type_code for column in description])
        columns = [
            ResultColumn(
                id=str(position),
                name=column.name,
                type=types.get(column.type_code, ColumnType(sql="unknown", category="other")),
            )
            for position, column in enumerate(description)
        ]
        # One more than the ceiling: the extra row is how truncation is
        # established rather than guessed from a full page.
        fetched = await cursor.fetchmany(limits.max_result_rows + 1)
        truncated = len(fetched) > limits.max_result_rows
        rows: list[list[str | None]] = []
        used = 0
        for raw in fetched[: limits.max_result_rows]:
            row: list[str | None] = []
            for column, value in zip(columns, raw, strict=False):
                cell = encode_cell(value, column.type)
                size = 0 if cell is None else len(cell.encode())
                if size > limits.max_cell_bytes:
                    raise ResultTooLarge(
                        f"A value in {column.name} is larger than one cell may be"
                    )
                used += size
                if used > limits.max_result_bytes:
                    raise ResultTooLarge("This result is larger than one result may be")
                row.append(cell)
            rows.append(row)
        self._run_bytes += used
        self._run_results += 1
        if self._run_results > limits.max_run_results:
            raise ResultTooLarge("This run produced more results than one run may hold")
        if self._run_bytes > limits.max_run_bytes:
            raise ResultTooLarge("This run produced more data than one run may hold")
        return MaterialisedResult(
            columns=columns, rows=rows, truncated=truncated, bytes_used=used
        )

    async def _types_of(
        self, connection: psycopg.AsyncConnection[Any], oids: list[int]
    ) -> dict[int, ColumnType]:
        """The same type facts a relation's columns are built from, by OID."""
        if not oids:
            return {}
        async with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            await cursor.execute(
                """
                SELECT t.oid AS oid,
                       format_type(t.oid, NULL) AS sql_type,
                       t.typname AS type_name,
                       t.typcategory AS type_category,
                       format_type(t.typelem, NULL) AS element_sql,
                       et.typname AS element_name,
                       et.typcategory AS element_category
                FROM pg_type t
                LEFT JOIN pg_type et ON et.oid = t.typelem
                WHERE t.oid = ANY(%s)
                """,
                (sorted(set(oids)),),
            )
            rows = await cursor.fetchall()
        return {int(row["oid"]): build_column_type(row) for row in rows}

    def _note(self, diagnostic: psycopg.errors.Diagnostic) -> None:
        if len(self._notices) >= self._request.limits.max_messages:
            return
        self._notices.append(
            QueryNotice(
                severity=_safe_text(diagnostic.severity, "NOTICE"),
                message=_safe_text(diagnostic.message_primary, "A message was raised"),
            )
        )

    @staticmethod
    def _since(began: float) -> int:
        return int((time.monotonic() - began) * 1000)


class PostgresExecution(_Statements):
    """One run that opens its own transaction and ends it.

    A read runs read-only and the transaction is closed either way.
    Auto-commit makes the whole run one transaction and commits only when
    every statement succeeded — the first failure rolls the lot back, which is
    what "the complete run is one transaction" means (D66).
    """

    def events(self) -> AsyncIterator[QueryEvent]:
        return self._run()

    async def _run(self) -> AsyncIterator[QueryEvent]:
        limits = self._request.limits
        script = prepare(self._request.text)
        started = time.monotonic()
        reading = self._request.mode == "read"
        if not reading and [one.kind for one in script.statements] == ["maintenance"]:
            async for event in self._outside_transaction(script, started):
                yield event
            return
        try:
            async with self._session.acquire() as connection:
                self._connection = connection
                _prepare_connection(connection, self._note)
                await connection.set_read_only(reading)
                try:
                    async with connection.transaction():
                        await set_read_context(
                            connection,
                            search_path=self._request.search_path,
                            statement_timeout_seconds=(
                                limits.statement_timeout_seconds
                            ),
                        )
                        async for event in self._statements(
                            connection, script, started, limits
                        ):
                            yield event
                        if self.failed and not reading:
                            # Leaving the block by an exception is how psycopg
                            # is told to roll back; the caller never sees it.
                            raise _RollBack
                finally:
                    self._connection = None
                    connection.remove_notice_handler(self._note)
                    await connection.set_read_only(None)
        except _RollBack:
            return
        except PoolTimeout:
            raise AdapterError("timeout", "No connection was free for this query") from None
        except AdapterError:
            raise
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message="The query could not be run")
            raise AdapterError(error_kind, message) from None

    async def _outside_transaction(
        self, script: PreparedScript, started: float
    ) -> AsyncIterator[QueryEvent]:
        """One maintenance command, kept by the server as it finishes.

        VACUUM, CLUSTER and a concurrent REINDEX refuse to run inside a
        transaction block, so this runs with none; the run's admission made
        sure nothing else shares it (D206). The pool keeps a connection's
        session as it was left, so what was set is reset before it goes back.
        """
        limits = self._request.limits
        try:
            async with self._session.acquire() as connection:
                self._connection = connection
                _prepare_connection(connection, self._note)
                await connection.set_autocommit(True)
                try:
                    await set_read_context(
                        connection,
                        search_path=self._request.search_path,
                        statement_timeout_seconds=limits.statement_timeout_seconds,
                        local=False,
                    )
                    async for event in self._statements(
                        connection, script, started, limits
                    ):
                        yield event
                finally:
                    self._connection = None
                    connection.remove_notice_handler(self._note)
                    try:
                        await connection.execute("RESET statement_timeout")
                        await connection.execute("RESET search_path")
                        await connection.set_autocommit(False)
                    except psycopg.Error:
                        # A connection that cannot be put back as it was is
                        # not put back: the pool discards a closed one.
                        await connection.close()
        except PoolTimeout:
            raise AdapterError("timeout", "No connection was free for this query") from None
        except AdapterError:
            raise
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message="The query could not be run")
            raise AdapterError(error_kind, message) from None


class _BoundExecution(_Statements):
    """One run inside a transaction somebody else opened, and will end."""

    def __init__(
        self,
        session: PostgresSession,
        request: QueryRequest,
        connection: psycopg.AsyncConnection[Any],
    ) -> None:
        super().__init__(session, request)
        self._connection = connection

    def events(self) -> AsyncIterator[QueryEvent]:
        return self._run()

    async def _run(self) -> AsyncIterator[QueryEvent]:
        connection = self._connection
        if connection is None:
            raise AdapterError("unknown", "This transaction is no longer open")
        limits = self._request.limits
        script = prepare(self._request.text)
        started = time.monotonic()
        connection.add_notice_handler(self._note)
        try:
            async for event in self._statements(connection, script, started, limits):
                yield event
        except PoolTimeout:
            raise AdapterError("timeout", "No connection was free for this query") from None
        except AdapterError:
            raise
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message="The query could not be run")
            raise AdapterError(error_kind, message) from None
        finally:
            connection.remove_notice_handler(self._note)


class _Rehearsal:
    """A change carried out on a real connection and then undone (D66).

    The point is that nothing here is a guess. PostgreSQL is asked to do the
    thing: it names the objects a cascade would take with it, refuses a drop
    whose dependants are still there, and says how long it waited for a lock.
    Then the transaction is rolled back and none of it happened.
    """

    def __init__(self, request: QueryRequest) -> None:
        self._request = request
        self._notices: list[QueryNotice] = []
        self._path: list[str] | None = None
        self.rehearsal = QueryRehearsal()

    def note(self, diagnostic: psycopg.errors.Diagnostic) -> None:
        if len(self._notices) >= self._request.limits.max_messages:
            return
        self._notices.append(
            QueryNotice(
                severity=_safe_text(diagnostic.severity, "NOTICE"),
                message=_safe_text(diagnostic.message_primary, "A message was raised"),
            )
        )

    async def carry_out(self, connection: psycopg.AsyncConnection[Any]) -> None:
        """Run every statement, keep what the server said, change nothing.

        The caller opens the transaction — its own, or a savepoint inside the
        one somebody is already holding — and rolls it back afterwards. A
        rehearsal that opened a second connection would queue behind the
        person's own locks and call their own transaction a blocker.
        """
        script = prepare(self._request.text)
        await connection.execute(
            sql.SQL("SET LOCAL lock_timeout = {}").format(
                sql.Literal(REHEARSAL_LOCK_TIMEOUT_SECONDS * 1000)
            )
        )
        rehearsed: list[RehearsedStatement] = []
        effect = SchemaEffect()
        blocked = False
        stopped = False
        for statement in script.statements:
            if stopped or statement.kind not in ("dml", "ddl"):
                # A read is left out rather than carried out: it changes
                # nothing, so it says nothing about the change, and running it
                # here would spend a whole result set to learn that.
                rehearsed.append(
                    RehearsedStatement(ordinal=statement.ordinal, outcome="not_run")
                )
                continue
            self._notices = []
            try:
                async with connection.cursor() as cursor:
                    values = _values_of(self._request, statement)
                    if values is None:
                        await cursor.execute(statement.text)
                    else:
                        await cursor.execute(bind(statement.text), values)
                    # Rows are not read: a rehearsal is about what a change
                    # would do, and materialising a SELECT in the middle of one
                    # would only spend the ceilings a real run is held to.
                    rehearsed.append(
                        RehearsedStatement(
                            ordinal=statement.ordinal,
                            outcome="ok",
                            command_tag=cursor.statusmessage,
                            affected_rows=(
                                cursor.rowcount if cursor.rowcount >= 0 else None
                            ),
                            notices=list(self._notices),
                        )
                    )
                if statement.kind == "ddl":
                    if self._path is None:
                        self._path = await resolve_path(
                            connection, self._request.search_path
                        )
                    effect = effect.with_(
                        effect_of(statement.text, search_path=self._path)
                    )
            except psycopg.Error as exc:
                sqlstate = getattr(exc, "sqlstate", None)
                waited = sqlstate in (_LOCK_NOT_AVAILABLE, _QUERY_CANCELLED)
                blocked = blocked or waited
                rehearsed.append(
                    RehearsedStatement(
                        ordinal=statement.ordinal,
                        outcome="blocked" if waited else "failed",
                        notices=list(self._notices),
                        diagnostic=(
                            _blocked_diagnostic(sqlstate)
                            if waited
                            else diagnostic_of(exc, cancelled=False)
                        ),
                    )
                )
                stopped = True
        self.rehearsal = QueryRehearsal(
            statements=rehearsed,
            blocked=blocked,
            runnable=not blocked and not stopped,
            effect=effect,
        )


def _blocked_diagnostic(sqlstate: str | None) -> QueryDiagnostic:
    """Why the rehearsal gave up, without pretending it read the statement."""
    return QueryDiagnostic(
        code=sqlstate or _LOCK_NOT_AVAILABLE,
        category="resource",
        message=(
            "Something else is holding this open; the change was not rehearsed"
        ),
    )


def _values_of(
    request: QueryRequest, statement: PreparedStatement
) -> dict[str, str | None] | None:
    """The bindings one statement uses, or nothing when it uses none."""
    if not statement.parameters:
        return None
    given = {parameter.name: parameter.value for parameter in request.parameters}
    return {name: given.get(name) for name in statement.parameters}


class PostgresTransaction:
    """One transaction, open across requests, holding its connection.

    PostgreSQL makes a transaction unusable after a statement error, so a
    failure marks it broken here too and the only honest way out is to end it.
    Nothing is committed by accident: it ends when somebody says so, or when
    the lease does (D66).
    """

    def __init__(self, session: PostgresSession, context: TransactionContext) -> None:
        self._session = session
        self._context = context
        self._stack = AsyncExitStack()
        self._connection: psycopg.AsyncConnection[Any] | None = None
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
            _prepare_connection(connection)
            await connection.set_read_only(False)
            await self._stack.enter_async_context(connection.transaction())
            await set_read_context(
                connection,
                search_path=self._context.search_path,
                statement_timeout_seconds=self._context.statement_timeout_seconds,
            )
        except PoolTimeout:
            await self._stack.aclose()
            raise AdapterError("timeout", "No connection was free for this query") from None
        except AdapterError:
            await self._stack.aclose()
            raise
        except Exception as exc:
            await self._stack.aclose()
            error_kind, message = classify(
                exc, fallback_message="The transaction could not be opened"
            )
            raise AdapterError(error_kind, message) from None
        self._connection = connection
        self._open = True

    def execute(self, request: QueryRequest) -> _BoundExecution:
        connection = self._connection
        if connection is None or not self._open:
            raise AdapterError("unknown", "This transaction is no longer open")
        if self._broken:
            raise AdapterError(
                "unknown",
                "This transaction failed and can only be rolled back",
            )
        run = _BoundExecution(self._session, request, connection)
        self._pending = run
        return run

    async def rehearse(self, request: QueryRequest) -> QueryRehearsal:
        """Try the change inside this transaction, and undo just that much.

        Inside rather than beside: a rehearsal on a second connection would
        wait for the locks this transaction is already holding and report the
        person's own work as the thing blocking them. psycopg turns a nested
        block into a savepoint, so what the rehearsal did is undone and
        everything before it stays (D66).
        """
        connection = self._connection
        if connection is None or not self._open:
            raise AdapterError("unknown", "This transaction is no longer open")
        if self._broken:
            raise AdapterError(
                "unknown", "This transaction failed and can only be rolled back"
            )
        rehearsal = _Rehearsal(request)
        connection.add_notice_handler(rehearsal.note)
        try:
            try:
                async with connection.transaction():
                    await rehearsal.carry_out(connection)
                    raise _RollBack
            except _RollBack:
                pass
        except PoolTimeout:
            raise AdapterError("timeout", "No connection was free for this query") from None
        except AdapterError:
            raise
        except Exception as exc:
            error_kind, message = classify(
                exc, fallback_message="The change could not be rehearsed"
            )
            raise AdapterError(error_kind, message) from None
        finally:
            connection.remove_notice_handler(rehearsal.note)
        return rehearsal.rehearsal

    def absorb(self, run: QueryExecution) -> None:
        """Take what a finished run did into the transaction's own state.

        Typed by the protocol rather than by this module's own class: what
        comes back is whatever was handed out, and only a runner ever calls
        this.
        """
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
        if run.failed:
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
            raise AdapterError(
                "unknown", "This transaction failed and can only be rolled back"
            )
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
            if not commit and connection is not None:
                # Leaving psycopg's transaction block by an exception is what
                # rolls it back; the exception itself goes no further.
                await self._stack.__aexit__(_RollBack, _RollBack(), None)
                return
            await self._stack.aclose()
        except _RollBack:
            return
        except Exception as exc:
            error_kind, message = classify(
                exc, fallback_message="The transaction could not be ended"
            )
            raise AdapterError(error_kind, message) from None
        finally:
            if connection is not None:
                try:
                    await connection.set_read_only(None)
                except Exception:
                    # The connection is going back to the pool, which resets
                    # it; failing to tidy is not worth an error here.
                    pass


class _RollBack(Exception):
    """Leaving a transaction block the way psycopg reads as "roll this back"."""


def _prepare_connection(
    connection: psycopg.AsyncConnection[Any],
    notice: Callable[[psycopg.errors.Diagnostic], None] | None = None,
) -> None:
    """What every connection running somebody's SQL is set up with.

    jsonb arrives as the server wrote it: letting the driver parse it would
    round a number through a float, and D23 says a cell crosses as its
    canonical text.
    """
    if notice is not None:
        connection.add_notice_handler(notice)
    for name in ("json", "jsonb"):
        connection.adapters.register_loader(name, TextLoader)


class PostgresQuery:
    """PostgreSQL as a source that accepts complete SQL (D62)."""

    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    def profile(self) -> QueryProfile:
        return QueryProfile(
            dialect="postgres",
            parameter_syntax="named_colon",
            statement_modes=["read", "auto_commit", "manual"],
            supports_cancel=True,
            # What else this source can do is derived from what it implements,
            # by whoever answers the profile. Restating it here would be the
            # second handwritten capability list D62 refuses.
            default_timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            max_timeout_seconds=MAX_TIMEOUT_SECONDS,
        )

    def prepare(self, text: str) -> PreparedScript:
        return prepare(text)

    def open(self, request: QueryRequest) -> PostgresExecution:
        return PostgresExecution(self._session, request)

    async def rehearse(self, request: QueryRequest) -> QueryRehearsal:
        """Carry the change out on its own connection, and undo it (D66)."""
        rehearsal = _Rehearsal(request)
        try:
            async with self._session.acquire() as connection:
                _prepare_connection(connection, rehearsal.note)
                await connection.set_read_only(False)
                try:
                    try:
                        async with connection.transaction():
                            await set_read_context(
                                connection,
                                search_path=request.search_path,
                                statement_timeout_seconds=(
                                    request.limits.statement_timeout_seconds
                                ),
                            )
                            await rehearsal.carry_out(connection)
                            raise _RollBack
                    except _RollBack:
                        pass
                finally:
                    connection.remove_notice_handler(rehearsal.note)
                    await connection.set_read_only(None)
        except PoolTimeout:
            raise AdapterError("timeout", "No connection was free for this query") from None
        except AdapterError:
            raise
        except Exception as exc:
            error_kind, message = classify(
                exc, fallback_message="The change could not be rehearsed"
            )
            raise AdapterError(error_kind, message) from None
        return rehearsal.rehearsal

    async def begin(self, context: TransactionContext) -> PostgresTransaction:
        """Open a transaction that outlives this request (D66)."""
        transaction = PostgresTransaction(self._session, context)
        await transaction.begin()
        return transaction

