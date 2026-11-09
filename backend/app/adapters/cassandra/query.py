"""Running CQL somebody wrote on a Cassandra or ScyllaDB cluster (D62, D343).

Cassandra has no transaction to hold a run together: every statement is kept
the moment it ends. So a run that changes anything holds that one statement
alone — a batch is one statement — and Auto-commit's promise, that a change is
kept when its run succeeds, stays true, as ClickHouse's does (D271). A read is
a run of statements that only read; the class is read from the text, because
the server has no read-only mode to ask for.

A run has a driver session of its own on the connector's cluster, opened on
the keyspace chosen above the editor, so a `USE` in it changes that run and no
page anybody else is reading.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from cassandra import (
    AlreadyExists,
    InvalidRequest,
    OperationTimedOut,
    ReadTimeout,
    Unauthorized,
    Unavailable,
    WriteTimeout,
)
from cassandra.cluster import Session
from cassandra.protocol import ConfigurationException, SyntaxException
from cassandra.query import SimpleStatement

from app.adapters.cassandra.inspection import Inspector
from app.adapters.cassandra.session import (
    Answer,
    CassandraSession,
    classify,
    refusal_text,
    waited,
)
from app.adapters.cassandra.statements import object_of, prepare
from app.adapters.cassandra.types import build_column_type, parse_value, read_cell
from app.adapters.database_ids import database_id, relation_id
from app.adapters.protocol import AdapterError
from app.adapters.query import (
    MaterialisedResult,
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
)
from app.core.translation import N_, say

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 300
MAX_MESSAGE_CHARS = 500
# Rows asked of the server at once while a result is read.
_PAGE = 5000

_ADMITTED: dict[str, frozenset[str]] = {
    "read": frozenset({"read", "session"}),
    "auto_commit": frozenset({"read", "dml", "ddl", "session"}),
}
_CHANGES = frozenset({"dml", "ddl"})

_UNSAFE = {ord(char): None for char in ("\r", "\x00")}

# Words of a server's refusal that say a thing it names is not there. Only the
# category is read from them; the sentence shown is the server's own.
_MISSING = (
    "does not exist",
    "unconfigured table",
    "undefined column",
    "not found",
    "unknown",
)


def _safe_text(value: str, fallback: str) -> str:
    return value.translate(_UNSAFE).strip()[:MAX_MESSAGE_CHARS] or fallback


def diagnostic_of(exc: BaseException) -> QueryDiagnostic | None:
    """A failure the statement caused, reduced to what may be shown (D64).

    None for a failure of the connection rather than of the statement; the
    caller raises that as the source failing.
    """
    if isinstance(exc, SyntaxException):
        category = "syntax"
    elif isinstance(exc, Unauthorized):
        category = "permission"
    elif isinstance(exc, ReadTimeout | WriteTimeout | OperationTimedOut):
        return QueryDiagnostic(
            code="timeout",
            category="timeout",
            message=say("The statement ran out of time"),
        )
    elif isinstance(exc, Unavailable):
        return QueryDiagnostic(
            code="unavailable",
            category="resource",
            message=say("Not enough replicas are up for the consistency level asked"),
        )
    elif isinstance(exc, AlreadyExists):
        category = "data"
    elif isinstance(exc, InvalidRequest | ConfigurationException):
        text = refusal_text(exc).lower()
        category = (
            "missing_object" if any(word in text for word in _MISSING) else "unknown"
        )
    else:
        return None
    code = str(getattr(exc, "code", "") or type(exc).__name__)
    return QueryDiagnostic(
        code=code,
        category=category,  # type: ignore[arg-type]  # each branch names a member of the union
        message=_safe_text(refusal_text(exc), say("The statement could not be run")),
    )


class ResultTooLarge(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _type_text(cql_type: Any) -> str:
    """The CQL spelling of a driver's type class: `map<text, int>`."""
    spelled = getattr(cql_type, "cql_parameterized_type", None)
    return str(spelled()) if callable(spelled) else "blob"


def effect_of(
    statement: PreparedStatement, keyspace: str | None
) -> SchemaEffect | None:
    """What a structure change means for the catalog on screen (D66).

    A keyspace names the root; a new or dropped table, view or type names its
    keyspace; an altered or truncated table, and a new index, name the table.
    A role or a grant changes nothing on screen. What cannot be read with
    certainty is the whole connection.
    """
    verb, kind, named_keyspace, name = object_of(statement.text)
    if verb in ("GRANT", "REVOKE") or kind in ("ROLE", "USER"):
        return None
    if kind in ("KEYSPACE", "SCHEMA"):
        return SchemaEffect(reload_node_ids=[None])
    place = named_keyspace or keyspace
    if name is None or place is None:
        return SchemaEffect(scope="connection")
    if (verb == "ALTER" and kind == "TABLE") or verb == "TRUNCATE":
        return SchemaEffect(relation_node_ids=[relation_id(place, name)])
    if verb == "CREATE" and kind == "INDEX":
        return SchemaEffect(relation_node_ids=[relation_id(place, name)])
    if kind in (
        "TABLE",
        "COLUMNFAMILY",
        "MATERIALIZED VIEW",
        "TYPE",
        "FUNCTION",
        "AGGREGATE",
    ):
        return SchemaEffect(reload_node_ids=[database_id(place)])
    return SchemaEffect(scope="connection")


class CassandraExecution:
    """One run: its statements one after another, each kept as it ends."""

    def __init__(
        self, session: CassandraSession, inspector: Inspector, request: QueryRequest
    ) -> None:
        self._session = session
        self._inspector = inspector
        self._request = request
        self._cancelled = False
        self._running: asyncio.Future[Answer] | None = None
        self._run_bytes = 0
        self._run_results = 0
        self._keyspace: str | None = None

    def events(self) -> AsyncIterator[QueryEvent]:
        return self._run()

    async def cancel(self) -> None:
        """Stop waiting for the statement; it reports the outcome itself (D64).

        CQL has no way to stop a statement on the server: what it was doing
        goes on there, and its answer is let go.
        """
        self._cancelled = True
        running = self._running
        if running is not None:
            running.cancel()

    async def _keyspace_of(self) -> str | None:
        wanted = next((name for name in self._request.search_path if name), None)
        if wanted is None:
            return self._session.keyspace() or None
        if await self._inspector.keyspace(wanted) is None:
            raise AdapterError(
                "config",
                say("This connection has no keyspace called {name}", name=wanted),
            )
        return wanted

    async def _run(self) -> AsyncIterator[QueryEvent]:
        script = prepare(self._request.text)
        started = time.monotonic()
        limits = self._request.limits
        self._keyspace = await self._keyspace_of()
        alone = len(script.statements) == 1
        try:
            async with (
                self._session.cluster() as kept,
                kept.own_session(self._keyspace) as session,
            ):
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
                    yield StatementStarted(ordinal=statement.ordinal)
                    finished = await self._one(session, statement, limits, alone=alone)
                    yield finished
                    stopped = finished.status != "succeeded"
        except AdapterError:
            raise
        except Exception as exc:
            error_kind, message = classify(
                exc, fallback_message=N_("The query could not be run")
            )
            raise AdapterError(error_kind, message) from None

    def _refused(
        self, statement: PreparedStatement, alone: bool
    ) -> QueryDiagnostic | None:
        if statement.refused is not None:
            return QueryDiagnostic(
                code="dp_refused", category="syntax", message=statement.refused
            )
        mode = self._request.mode
        if statement.kind not in _ADMITTED.get(mode, frozenset()):
            if mode == "read":
                message = say(
                    "A {kind} statement cannot run in a read", kind=statement.kind
                )
            else:
                message = say("A {kind} statement is not run here", kind=statement.kind)
            return QueryDiagnostic(
                code="dp_not_admitted", category="read_only", message=message
            )
        if statement.kind in _CHANGES and not alone:
            return QueryDiagnostic(
                code="dp_not_admitted",
                category="read_only",
                message=say(
                    "Cassandra keeps a change the moment it is made and cannot undo it, so a "
                    "change cannot share a run with other statements; run it on its own, or "
                    "put the changes in one BATCH"
                ),
            )
        return None

    def _bound(self, session: Session, statement: PreparedStatement) -> Any:
        """The statement as the driver sends it: plain, or prepared and bound."""
        if not statement.parameters:
            return SimpleStatement(statement.text)
        given = {
            parameter.name: parameter.value for parameter in self._request.parameters
        }
        missing = [name for name in statement.parameters if name not in given]
        if missing:
            raise ValueError(say("No value was given for :{name}", name=missing[0]))
        prepared = session.prepare(statement.text)
        values: dict[str, Any] = {}
        for column in prepared.column_metadata or []:
            name = str(column.name)
            text = given.get(name)
            if text is None:
                values[name] = None
                continue
            type_text = _type_text(column.type)
            try:
                values[name] = parse_value(text, type_text)
            except ValueError:
                raise ValueError(
                    say(
                        ":{name} is not a value of type {type}",
                        name=name,
                        type=type_text,
                    )
                ) from None
        return prepared.bind(values)

    async def _one(
        self,
        session: Session,
        statement: PreparedStatement,
        limits: QueryLimits,
        *,
        alone: bool,
    ) -> StatementFinished:
        refused = self._refused(statement, alone)
        if refused is not None:
            return StatementFinished(
                ordinal=statement.ordinal,
                status="failed",
                duration_ms=0,
                diagnostic=refused,
            )
        began = time.monotonic()
        try:
            query = await asyncio.to_thread(self._bound, session, statement)
            answer = await self._read(session, query, limits)
            result = None if not answer.names else self._materialise(answer, limits)
        except ValueError as refusal:
            return StatementFinished(
                ordinal=statement.ordinal,
                status="failed",
                duration_ms=self._since(began),
                diagnostic=QueryDiagnostic(
                    code="dp_parameter", category="data", message=str(refusal)
                ),
            )
        except ResultTooLarge as refusal:
            return StatementFinished(
                ordinal=statement.ordinal,
                status="succeeded",
                duration_ms=self._since(began),
                diagnostic=QueryDiagnostic(
                    code="result_too_large",
                    category="resource",
                    message=refusal.message,
                ),
            )
        except asyncio.CancelledError:
            if not self._cancelled:
                raise
            return self._stopped(statement, began)
        except Exception as exc:
            diagnostic = diagnostic_of(exc)
            if diagnostic is None:
                error_kind, message = classify(
                    exc, fallback_message=N_("The query could not be run")
                )
                raise AdapterError(error_kind, message) from None
            return StatementFinished(
                ordinal=statement.ordinal,
                status="timed_out" if diagnostic.category == "timeout" else "failed",
                duration_ms=self._since(began),
                diagnostic=diagnostic,
            )
        finally:
            self._running = None
        if statement.kind == "session":
            self._keyspace = session.keyspace or self._keyspace
        effect = (
            effect_of(statement, self._keyspace) if statement.kind == "ddl" else None
        )
        return StatementFinished(
            ordinal=statement.ordinal,
            status="succeeded",
            duration_ms=self._since(began),
            row_count=None if result is None else len(result.rows),
            result=result,
            effect=effect,
        )

    async def _read(self, session: Session, query: Any, limits: QueryLimits) -> Answer:
        """Every page of the answer, up to the row ceiling and one row past it."""
        wanted = limits.max_result_rows + 1
        query.fetch_size = min(_PAGE, wanted)
        answer = await self._page(session, query, None, limits)
        while answer.paging_state is not None and len(answer.rows) < wanted:
            more = await self._page(session, query, answer.paging_state, limits)
            answer.rows.extend(more.rows)
            answer.paging_state = more.paging_state
        return answer

    async def _page(
        self, session: Session, query: Any, state: bytes | None, limits: QueryLimits
    ) -> Answer:
        future = session.execute_async(
            query, paging_state=state, timeout=limits.statement_timeout_seconds
        )
        self._running = asyncio.ensure_future(waited(future))
        return await self._running

    def _stopped(self, statement: PreparedStatement, began: float) -> StatementFinished:
        return StatementFinished(
            ordinal=statement.ordinal,
            status="cancelled",
            duration_ms=self._since(began),
            diagnostic=QueryDiagnostic(
                code="cancelled", category="cancelled", message=say("Cancelled")
            ),
        )

    def _materialise(self, answer: Answer, limits: QueryLimits) -> MaterialisedResult:
        """Every row once, within the ceilings D64 states, names kept apart."""
        types = [build_column_type(_type_text(type_)) for type_ in answer.types]
        columns = [
            ResultColumn(
                id=str(position),
                name=name,
                type=types[position]
                if position < len(types)
                else build_column_type("blob"),
            )
            for position, name in enumerate(answer.names)
        ]
        truncated = len(answer.rows) > limits.max_result_rows
        rows: list[list[str | None]] = []
        used = 0
        for raw in answer.rows[: limits.max_result_rows]:
            row: list[str | None] = []
            for column, value in zip(columns, raw, strict=False):
                cell = read_cell(value, column.type)
                size = 0 if cell is None else len(cell.encode())
                if size > limits.max_cell_bytes:
                    raise ResultTooLarge(
                        say(
                            "A value in {column} is larger than one cell may be",
                            column=column.name,
                        )
                    )
                used += size
                if used > limits.max_result_bytes:
                    raise ResultTooLarge(
                        say("This result is larger than one result may be")
                    )
                row.append(cell)
            rows.append(row)
        self._run_bytes += used
        self._run_results += 1
        if self._run_results > limits.max_run_results:
            raise ResultTooLarge(
                say("This run produced more results than one run may hold")
            )
        if self._run_bytes > limits.max_run_bytes:
            raise ResultTooLarge(
                say("This run produced more data than one run may hold")
            )
        return MaterialisedResult(
            columns=columns, rows=rows, truncated=truncated, bytes_used=used
        )

    @staticmethod
    def _since(began: float) -> int:
        return int((time.monotonic() - began) * 1000)


class CassandraQuery:
    """Cassandra and ScyllaDB as sources that accept complete CQL (D62, D343)."""

    def __init__(self, session: CassandraSession, inspector: Inspector) -> None:
        self._session = session
        self._inspector = inspector

    def profile(self) -> QueryProfile:
        return QueryProfile(
            dialect="cql",
            parameter_syntax="named_colon",
            # No manual transaction: Cassandra has none to hold.
            statement_modes=["read", "auto_commit"],
            supports_cancel=True,
            default_timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            max_timeout_seconds=MAX_TIMEOUT_SECONDS,
        )

    def prepare(self, text: str) -> PreparedScript:
        return prepare(text)

    def open(self, request: QueryRequest) -> CassandraExecution:
        return CassandraExecution(self._session, self._inspector, request)
