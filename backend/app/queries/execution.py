"""Starting a run, watching it, stopping it, and picking up after a restart.

D64: the HTTP request validates and records; a task executes. Nothing here
waits for SQL to finish before answering, and closing a panel or losing a
socket does not stop anything — a run belongs to the server.
"""

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlmodel import col, select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.protocol import AdapterError
from app.adapters.query import (
    PreparedScript,
    QueryExecution,
    QueryLimits,
    StatementFinished,
)
from app.core.config import settings
from app.core.db import async_session_maker
from app.core.schemas import get_datetime_utc
from app.queries.content import encrypted
from app.queries.results import QueryResults
from app.queries.runs import (
    TERMINAL,
    ExecutionRun,
    ParameterMetadata,
    RunStart,
    StatementRun,
)
from app.queries.sessions import Lease, QuerySessions
from app.queries.topic import RunEvent, announce
from app.realtime.topics import TopicSet

logger = logging.getLogger(__name__)

# A separator no part of a command can contain, so two different commands
# cannot hash to one fingerprint by running into each other.
SEPARATOR = "\u0000"


def limits(*, statement_timeout_seconds: int) -> QueryLimits:
    """Every ceiling one run is held to, read from settings in one place.

    The per-statement timeout is not among them: it is the source's policy and
    what the caller asked for, clamped against the profile, so it arrives here
    already decided.
    """
    return QueryLimits(
        statement_timeout_seconds=statement_timeout_seconds,
        script_timeout_seconds=settings.QUERY_SCRIPT_TIMEOUT_SECONDS,
        max_statements=settings.QUERY_MAX_STATEMENTS,
        max_statement_bytes=settings.QUERY_STATEMENT_MAX_BYTES,
        max_result_rows=settings.QUERY_RESULT_MAX_ROWS,
        max_result_bytes=settings.QUERY_RESULT_MAX_BYTES,
        max_cell_bytes=settings.QUERY_CELL_MAX_BYTES,
        max_run_results=settings.QUERY_RUN_MAX_RESULTS,
        max_run_bytes=settings.QUERY_RUN_MAX_BYTES,
        max_messages=settings.QUERY_RUN_MAX_MESSAGES,
    )


def fingerprint(body: RunStart) -> str:
    """What this command asked for, as one value that can be compared.

    Idempotency needs to know whether two commands with one id are the same
    command. Hashed rather than kept: the text is encrypted in the row beside
    it, and a plaintext copy to compare against would undo that (D63).
    """
    parts = [
        str(body.connector_id),
        str(body.document_id),
        str(body.document_revision),
        body.mode,
        body.scope,
        str(body.timeout_seconds),
        str(body.range_start),
        str(body.range_end),
        body.text,
        *(f"{one.name}={one.value}" for one in body.parameters),
    ]
    return hashlib.sha256(SEPARATOR.join(parts).encode()).hexdigest()


def admit(
    script: PreparedScript,
    bounds: QueryLimits,
    *,
    scope: str = "script",
    given: Iterable[str] = (),
    mode: str = "read",
) -> list[tuple[int, str]]:
    """Check what was asked for before a run exists, and say what is wrong.

    Input bounds first, then the shape, then the classes, then the bindings. A
    statement this slice cannot run is named by its place in the text rather
    than reported as a failure after the run has been recorded — nothing has
    happened yet, so this is a refusal and not an outcome (D62).
    """
    if not script.statements:
        raise RunRefused(422, "There is nothing to run")
    if scope == "statement" and len(script.statements) > 1:
        # Ordinary Run is one statement. Several of them is the other command,
        # and falling back to it silently is how a selection nobody checked
        # becomes a script nobody meant to run (D65).
        raise RunRefused(
            422,
            "This is more than one statement; run it as a script to run them all",
        )
    if len(script.statements) > bounds.max_statements:
        raise RunRefused(
            422, f"A script may hold at most {bounds.max_statements} statements"
        )
    for statement in script.statements:
        if len(statement.text.encode()) > bounds.max_statement_bytes:
            raise RunRefused(
                422,
                f"Statement {statement.ordinal + 1} is larger than one statement may be",
            )
    admitted = _ADMITTED.get(mode, frozenset({"read"}))
    for statement in script.statements:
        if statement.kind in admitted:
            continue
        if statement.kind == "ddl":
            # A closed vocabulary of schema changes is a slice of its own, with
            # its own preview and its own invalidation (D66).
            raise RunRefused(
                422,
                f"Statement {statement.ordinal + 1} changes the structure of the "
                "source, which is not run here yet",
            )
        raise RunRefused(
            422,
            f"Statement {statement.ordinal + 1} is a {statement.kind} statement, "
            + (
                "and this run is a read"
                if mode == "read"
                else "and statements of that kind are not run here"
            ),
        )
    supplied = set(given)
    missing = [name for name in script.parameters if name not in supplied]
    if missing:
        # Named rather than bound to null: a parameter nobody filled in is a
        # question, and answering it with SQL null on the user's behalf is a
        # different query from the one they meant.
        raise RunRefused(
            422, f"No value was given for {', '.join(missing)}"
        )
    return [(statement.ordinal, statement.kind) for statement in script.statements]


# What each mode will carry out. DDL waits for the slice that gives it a
# preview and an invalidation; everything else is refused by class.
_ADMITTED: dict[str, frozenset[str]] = {
    "read": frozenset({"read"}),
    "auto_commit": frozenset({"read", "dml"}),
    "manual": frozenset({"read", "dml"}),
}


class RunRefused(Exception):
    """The run will not be accepted, and the answer says exactly why."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass
class _Active:
    task: asyncio.Task[None]
    execution: QueryExecution
    owner_id: uuid.UUID
    document_id: uuid.UUID | None


class QueryRunner:
    """The runs this process is carrying out.

    Process-local, exactly as the result store is, and for the same reason:
    what is held is a connection and a task, neither of which crosses a
    process. A run recorded by another process is still readable — it is a row
    — and a restart marks whatever was left non-terminal as interrupted.
    """

    def __init__(self, *, results: QueryResults) -> None:
        self._results = results
        self._active: dict[uuid.UUID, _Active] = {}
        self._lock = asyncio.Lock()

    async def active_count(self, owner_id: uuid.UUID) -> int:
        async with self._lock:
            return sum(1 for run in self._active.values() if run.owner_id == owner_id)

    async def is_running_document(self, document_id: uuid.UUID) -> bool:
        async with self._lock:
            return any(
                run.document_id == document_id for run in self._active.values()
            )

    async def launch(
        self,
        *,
        run_id: uuid.UUID,
        owner_id: uuid.UUID,
        document_id: uuid.UUID | None,
        execution: QueryExecution,
        topics: TopicSet,
        lease: Lease | None = None,
        sessions: QuerySessions | None = None,
        mode: str = "read",
    ) -> None:
        """Carry out one run, on its own or inside an open transaction.

        The execution is made by whoever knows where the statements belong —
        the source for a read or an auto-commit, the transaction for a manual
        run — and this only watches it (D66).
        """
        task = asyncio.create_task(
            self._carry_out(
                run_id,
                owner_id,
                document_id,
                execution,
                topics,
                lease,
                sessions,
                mode,
            )
        )
        async with self._lock:
            self._active[run_id] = _Active(
                task=task,
                execution=execution,
                owner_id=owner_id,
                document_id=document_id,
            )

    async def cancel(self, run_id: uuid.UUID) -> bool:
        """Ask a run this process is carrying out to stop. False if it is not."""
        async with self._lock:
            active = self._active.get(run_id)
        if active is None:
            return False
        await active.execution.cancel()
        return True

    async def aclose(self) -> None:
        async with self._lock:
            active = list(self._active.values())
        for run in active:
            run.task.cancel()
        for run in active:
            try:
                await run.task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                # Shutting down: a run that cannot finish tidily is left to the
                # startup sweep, which marks it interrupted.
                continue

    async def _carry_out(
        self,
        run_id: uuid.UUID,
        owner_id: uuid.UUID,
        document_id: uuid.UUID | None,
        execution: QueryExecution,
        topics: TopicSet,
        lease: Lease | None = None,
        sessions: QuerySessions | None = None,
        mode: str = "read",
    ) -> None:
        """Read the source's events and write down what happened.

        Its own session: the request that started this has long since answered,
        and a session belongs to the task using it.
        """
        finished = 0
        status = "succeeded"
        error: str | None = None
        try:
            async with async_session_maker() as session:
                await _mark(session, run_id, status="running", started=True)
                await _publish(topics, owner_id, session, run_id)
                try:
                    async for event in execution.events():
                        if not isinstance(event, StatementFinished):
                            continue
                        finished += 1
                        await self._record(session, run_id, owner_id, event)
                        await _publish(
                            topics, owner_id, session, run_id, finished=finished
                        )
                        if event.status in {"failed", "cancelled", "timed_out"}:
                            status = event.status
                except AdapterError as failure:
                    # The run could not be carried out at all: the source was
                    # unreachable, or refused the context. Statement failures
                    # are not this.
                    status = "failed"
                    error = failure.message
                await _mark(
                    session,
                    run_id,
                    status=status,
                    finished=True,
                    error=error,
                    # A manual run's changes are pending until somebody ends
                    # the transaction; an auto-commit run settled with it.
                    write_state=_settled(mode, status),
                )
                await _publish(topics, owner_id, session, run_id, finished=finished)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never a traceback into the caller and never SQL into the log: the
            # run is marked failed with a sentence, and the exception is logged
            # by type through the standard handler.
            logger.exception("A query run could not be completed")
            async with async_session_maker() as session:
                await _mark(
                    session,
                    run_id,
                    status="failed",
                    finished=True,
                    error="This run could not be completed",
                )
        finally:
            # What the run did belongs to the transaction it ran in, and the
            # lease is free again either way.
            if lease is not None:
                lease.transaction.absorb(execution)
                if sessions is not None:
                    await sessions.mark_busy(lease.id, False)
            await self._results.release(run_id)
            async with self._lock:
                self._active.pop(run_id, None)

    async def _record(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        owner_id: uuid.UUID,
        event: StatementFinished,
    ) -> None:
        statement = await session.get(StatementRun, (run_id, event.ordinal))
        if statement is None:
            return
        statement.status = event.status
        statement.duration_ms = event.duration_ms
        statement.command_tag = event.command_tag
        statement.row_count = event.row_count
        statement.affected_rows = event.affected_rows
        statement.notices = [notice.model_dump() for notice in event.notices]
        diagnostic = event.diagnostic
        if event.result is not None:
            statement.truncated = event.result.truncated
            result_id = await self._results.put(
                owner_id=owner_id, run_id=run_id, result=event.result
            )
            statement.result_id = result_id
            if result_id is None and diagnostic is None:
                # The statement succeeded and its rows could not be kept. D64
                # keeps store exhaustion apart from statement failure, so the
                # status stays as it was and the reason is said here.
                diagnostic = _no_room()
        statement.diagnostic = None if diagnostic is None else diagnostic.model_dump()
        session.add(statement)
        await session.commit()


def _no_room() -> Any:
    from app.adapters.query import QueryDiagnostic

    return QueryDiagnostic(
        code="result_store_full",
        category="resource",
        message="There was no room to keep this result",
    )


def _settled(mode: str, status: str) -> str:
    """What became of what a run changed, by the mode it ran in (D66).

    A read changed nothing. An auto-commit run is one transaction: it either
    committed as a whole or was rolled back as a whole. A manual run waits for
    the person to say.
    """
    if mode == "read":
        return "none"
    if mode == "manual":
        return "pending"
    return "committed" if status == "succeeded" else "rolled_back"


async def _mark(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    status: str,
    started: bool = False,
    finished: bool = False,
    error: str | None = None,
    write_state: str | None = None,
) -> None:
    run = await session.get(ExecutionRun, run_id)
    if run is None:
        return
    # A run asked to stop is `cancelling` until the source answers; a statement
    # that finished as cancelled is what makes it `cancelled`.
    if run.status == "cancelling" and status == "succeeded":
        status = "cancelled"
    run.status = status
    if started:
        run.started_at = get_datetime_utc()
    if finished:
        run.finished_at = get_datetime_utc()
    if error is not None:
        run.error = error[:500]
    if write_state is not None:
        run.write_state = write_state
    session.add(run)
    await session.commit()


async def _publish(
    topics: TopicSet,
    owner_id: uuid.UUID,
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    finished: int = 0,
) -> None:
    run = await session.get(ExecutionRun, run_id)
    if run is None:
        return
    await announce(
        topics,
        owner_id,
        RunEvent(
            run_id=run.id,
            document_id=run.document_id,
            status=run.status,  # type: ignore[arg-type]  # the column holds the union
            finished_statements=finished,
            statement_count=run.statement_count,
        ),
    )


async def record(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    body: RunStart,
    statements: Iterable[tuple[int, str]],
    timeout_seconds: int,
    search_path: list[str],
) -> ExecutionRun:
    """Write the run and its statements down before anything is executed.

    The order matters: a run that exists is a run that can be asked about, and
    a run that is executing without a row would be invisible to the route that
    is supposed to be the authority.
    """
    run = ExecutionRun(
        id=body.run_id,
        owner_id=owner_id,
        connector_id=body.connector_id,
        document_id=body.document_id,
        document_revision=body.document_revision,
        text=encrypted(body.text),
        range_start=body.range_start,
        range_end=body.range_end,
        search_path=search_path,
        mode=body.mode,
        scope=body.scope,
        transaction_id=body.transaction_id,
        write_state="pending" if body.mode == "manual" else "none",
        # Names and shape. The values were used and are not kept (D63).
        parameters=[
            ParameterMetadata(
                name=one.name, is_null=one.value is None, secret=one.secret
            ).model_dump()
            for one in body.parameters
        ],
        timeout_seconds=timeout_seconds,
        status="accepted",
        fingerprint=fingerprint(body),
    )
    ordered = list(statements)
    run.statement_count = len(ordered)
    session.add(run)
    for ordinal, kind in ordered:
        session.add(StatementRun(run_id=run.id, ordinal=ordinal, kind=kind))
    await session.commit()
    await session.refresh(run)
    return run


async def settle(
    session: AsyncSession, *, transaction_id: str, committed: bool
) -> None:
    """Say what became of every run that went through this transaction.

    A run's own row is where somebody looks afterwards, so "pending" must not
    outlive the transaction it was pending on (D66).
    """
    await session.exec(
        update(ExecutionRun)
        .where(
            col(ExecutionRun.transaction_id) == transaction_id,
            col(ExecutionRun.write_state) == "pending",
        )
        .values(write_state="committed" if committed else "rolled_back")
    )
    await session.commit()


async def recover_interrupted(session: AsyncSession) -> int:
    """Mark what a stopped process left behind, at startup.

    A run in `accepted`, `running` or `cancelling` after a restart is not
    running anywhere: the task and the connection went with the process. It
    becomes `interrupted`, and SQL is never replayed automatically (D64).
    """
    stranded = (
        await session.exec(
            select(ExecutionRun).where(
                col(ExecutionRun.status).in_(["accepted", "running", "cancelling"])
            )
        )
    ).all()
    if not stranded:
        return 0
    moment = datetime.now(UTC)
    for run in stranded:
        run.status = "interrupted"
        run.finished_at = moment
        session.add(run)
    await session.exec(
        update(StatementRun)
        .where(
            col(StatementRun.run_id).in_([run.id for run in stranded]),
            col(StatementRun.status).in_(["pending", "running"]),
        )
        .values(status="not_run")
    )
    await session.commit()
    return len(stranded)


def get_runner(request: Request) -> QueryRunner:
    runner = request.app.state.query_runner
    if not isinstance(runner, QueryRunner):
        raise RuntimeError("The application has no runner; is the lifespan running?")
    return runner


RunnerDep = Annotated[QueryRunner, Depends(get_runner)]


def is_terminal(status: str) -> bool:
    return status in TERMINAL
