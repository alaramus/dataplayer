"""Running SQL somebody wrote, inside a transaction the database enforces.

D62: classification chooses the wording and the policy; it is not the defence.
The defence is a PostgreSQL `READ ONLY` transaction with a local statement
timeout and a search path composed from names the server itself confirmed. What
that guarantees is exact — no persistent database change that PostgreSQL
read-only mode admits — and no more: a function may still send mail or reach
outside the database, and restricting that is the database role's job.
"""

import time
from collections.abc import AsyncIterator
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.string import TextLoader
from psycopg_pool import PoolTimeout

from app.adapters.cells import encode_cell
from app.adapters.postgres.column_type import build_column_type
from app.adapters.postgres.session import PostgresSession, classify
from app.adapters.postgres.statements import bind, prepare
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
    QueryRequest,
    ResultColumn,
    StatementFinished,
    StatementStarted,
    StatementStatus,
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


class ResultTooLarge(Exception):
    """A statement succeeded and its result cannot be published (D64)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class PostgresExecution:
    """One run, holding the connection it is running on.

    Cancellation reaches the connection rather than the task: dropping the task
    would leave the query running on the server, which is the mistake the
    lifecycle in D64 exists to prevent.
    """

    def __init__(self, session: PostgresSession, request: QueryRequest) -> None:
        self._session = session
        self._request = request
        self._connection: psycopg.AsyncConnection[Any] | None = None
        self._cancelled = False
        self._notices: list[QueryNotice] = []
        self._run_bytes = 0
        self._run_results = 0

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

    def events(self) -> AsyncIterator[QueryEvent]:
        return self._run()

    async def _run(self) -> AsyncIterator[QueryEvent]:
        limits = self._request.limits
        script = prepare(self._request.text)
        started = time.monotonic()
        try:
            async with self._session.acquire() as connection:
                self._connection = connection
                connection.add_notice_handler(self._note)
                # jsonb arrives as the server wrote it: letting the driver
                # parse it would round a number through a float, and D23 says
                # a cell crosses as its canonical text.
                for name in ("json", "jsonb"):
                    connection.adapters.register_loader(name, TextLoader)
                await connection.set_read_only(True)
                try:
                    async with connection.transaction():
                        await self._set_context(connection)
                        async for event in self._statements(
                            connection, script, started, limits
                        ):
                            yield event
                finally:
                    self._connection = None
                    connection.remove_notice_handler(self._note)
                    await connection.set_read_only(None)
        except PoolTimeout:
            raise AdapterError("timeout", "No connection was free for this query") from None
        except AdapterError:
            raise
        except Exception as exc:
            error_kind, message = classify(exc, fallback_message="The query could not be run")
            raise AdapterError(error_kind, message) from None

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

    async def _one(
        self,
        connection: psycopg.AsyncConnection[Any],
        statement: PreparedStatement,
        limits: QueryLimits,
    ) -> StatementFinished:
        if statement.kind != "read":
            # The transaction would refuse most of these anyway; saying which
            # kind it is beats letting the database answer for the ones it
            # cannot see the point of.
            return StatementFinished(
                ordinal=statement.ordinal,
                status="failed",
                duration_ms=0,
                diagnostic=QueryDiagnostic(
                    code="dp_not_read",
                    category="read_only",
                    message=f"A {statement.kind} statement cannot run in a read",
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
                return StatementFinished(
                    ordinal=statement.ordinal,
                    status="succeeded",
                    duration_ms=self._since(began),
                    command_tag=cursor.statusmessage,
                    row_count=None if result is None else len(result.rows),
                    result=result,
                    notices=self._notices[: limits.max_messages],
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

    def _values_for(self, statement: PreparedStatement) -> dict[str, str | None] | None:
        """The bindings this statement uses, or nothing when it uses none."""
        if not statement.parameters:
            return None
        given = {parameter.name: parameter.value for parameter in self._request.parameters}
        return {name: given.get(name) for name in statement.parameters}

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

    async def _set_context(self, connection: psycopg.AsyncConnection[Any]) -> None:
        """Set the timeout and the schema context this run is to see.

        Every schema name is checked against the server before it reaches a
        statement, and then composed as an identifier rather than pasted in: a
        context is client-influenced text, and D2c does not stop applying
        because the statement beside it was written by a user.
        """
        limits = self._request.limits
        await connection.execute(
            sql.SQL("SET LOCAL statement_timeout = {}").format(
                sql.Literal(limits.statement_timeout_seconds * 1000)
            )
        )
        wanted = [name for name in self._request.search_path if name]
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
            sql.SQL("SET LOCAL search_path TO {}").format(
                sql.SQL(", ").join(sql.Identifier(name) for name in wanted)
            )
        )

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


class PostgresQuery:
    """PostgreSQL as a source that accepts complete SQL (D62)."""

    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    def profile(self) -> QueryProfile:
        return QueryProfile(
            dialect="postgres",
            parameter_syntax="named_colon",
            statement_modes=["read"],
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

