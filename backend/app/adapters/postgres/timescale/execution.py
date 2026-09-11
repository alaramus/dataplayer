"""Locked re-planning for reviewed Timescale metadata changes (D123).

Execution repeats planning after the strategy's locks and compares the reviewed
fingerprint before any mutation; nothing is retried. The interval strategy
keeps its own copy of this sequence, which its real-source evidence covers.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import psycopg
from psycopg import sql

from app.adapters.actions import ActionRefused
from app.adapters.postgres.inspection import InspectionReader, PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.plans import ReviewedPlan
from app.adapters.protocol import AdapterError

# Lock waits, deadlocks, serialization failures and objects gone since planning.
_CHANGED = frozenset({"55P03", "40P01", "40001", "42P01", "42704"})


async def run_reviewed[P: ReviewedPlan](
    session: PostgresSession,
    replan: Callable[[PostgresReader], Awaitable[P]],
    locks: Callable[[P], Sequence[sql.SQL | sql.Composed]],
    apply: Callable[[psycopg.AsyncConnection[Any], P], Awaitable[None]],
    reviewed_fingerprint: str,
    subject: str,
) -> P:
    unconfirmed = f"The {subject} could not be confirmed; reload the source before reviewing again"
    mutation_started = False
    try:
        async with asyncio.timeout(5):
            async with session.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE")
                    await connection.execute("SET LOCAL lock_timeout = '2s'")
                    await connection.execute("SET LOCAL statement_timeout = '5s'")
                    reader = InspectionReader(connection)
                    preliminary = await replan(reader)
                    preliminary.require_unchanged(reviewed_fingerprint)
                    for statement in locks(preliminary):
                        await connection.execute(statement)
                    current = await replan(reader)
                    current.require_unchanged(reviewed_fingerprint)
                    mutation_started = True
                    await apply(connection, current)
        return current
    except TimeoutError:
        if mutation_started:
            raise AdapterError("unknown", unconfirmed) from None
        raise ActionRefused("conflict", "Validation timed out; review the plan again") from None
    except psycopg.Error as exc:
        if exc.sqlstate in _CHANGED:
            raise ActionRefused("conflict", "The source changed or is busy; review the plan again") from None
        if exc.sqlstate == "42501":
            raise ActionRefused(
                "not_applicable", f"This connection may not make this {subject} or lock its metadata",
            ) from None
        if exc.sqlstate and exc.sqlstate[:2] not in {"08", "57", "58"}:
            raise ActionRefused("not_applicable", f"The source refused the {subject}") from None
        raise AdapterError("unknown", unconfirmed) from None
