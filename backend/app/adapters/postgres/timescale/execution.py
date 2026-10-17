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
from app.core.translation import say

# Lock waits, deadlocks, serialization failures and objects gone since planning.
_CHANGED = frozenset({"55P03", "40P01", "40001", "42P01", "42704"})


async def run_reviewed[P: ReviewedPlan](
    session: PostgresSession,
    replan: Callable[[PostgresReader], Awaitable[P]],
    locks: Callable[[P], Sequence[sql.SQL | sql.Composed]],
    apply: Callable[[psycopg.AsyncConnection[Any], P], Awaitable[None]],
    reviewed_fingerprint: str,
    *,
    seconds: int = 5,
    lock_seconds: int = 2,
) -> P:
    """Re-plan under the strategy's locks and apply, all in one transaction.

    A longer `seconds` is for work that moves rows (D207): the statement timeout
    is then the source rolling back on its own, so it is a refusal that changed
    nothing rather than an unknown outcome.
    """
    mutation_started = False
    try:
        # A little past the statement timeout, so the source's own rollback is what is reported.
        async with asyncio.timeout(seconds + (0 if seconds <= 5 else 60)):
            async with session.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE")
                    await connection.execute(f"SET LOCAL lock_timeout = '{int(lock_seconds)}s'")
                    await connection.execute(f"SET LOCAL statement_timeout = '{int(seconds)}s'")
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
            raise AdapterError("unknown", _unconfirmed()) from None
        raise ActionRefused("conflict", say("Validation timed out; review the plan again")) from None
    except psycopg.Error as exc:
        if exc.sqlstate in _CHANGED:
            raise ActionRefused("conflict", say("The source changed or is busy; review the plan again")) from None
        if exc.sqlstate == "57014" and seconds > 5:
            raise ActionRefused(
                "not_applicable", say("The change ran past its {seconds} seconds and was rolled back", seconds=seconds),
            ) from None
        if exc.sqlstate == "42501":
            raise ActionRefused(
                "not_applicable", say("This connection may not make this change or lock its metadata"),
            ) from None
        if exc.sqlstate and exc.sqlstate[:2] not in {"08", "57", "58"}:
            raise ActionRefused("not_applicable", say("The source refused the change")) from None
        raise AdapterError("unknown", _unconfirmed()) from None


def _unconfirmed() -> str:
    return say("The change could not be confirmed; reload the source before reviewing again")
