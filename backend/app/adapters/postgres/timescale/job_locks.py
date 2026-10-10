"""Changing TimescaleDB's jobs without closing a lock cycle with its scheduler (D211).

Up to 2.25 every job has a lock of its own, taken before the job catalogs: a
scheduler starting the job holds it while it reads `bgw_job` and writes
`bgw_job_stat`, and a removal waits for it before deleting. A change that holds
a lock on those catalogs and then removes a job closes a cycle with a scheduler
starting that job. PostgreSQL may then end the scheduler, and most releases
never start it again. The public jobs view cannot be locked without locking
both catalogs, so no change here locks it. What it used to do for DataPlayer —
one job change at a time per database — is done by an advisory lock that
nothing in TimescaleDB takes.
"""

from collections.abc import Sequence
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

# "DPTSJOBS". An application taking this advisory key would wait for a policy change too.
_KEY = 0x445054534A4F4253

JOBS_GUARD = sql.SQL("SELECT pg_catalog.pg_advisory_xact_lock({})").format(sql.Literal(_KEY))

# A third of deadlock_timeout, and never longer than the wait already allowed.
_WAITS = """
SELECT pg_catalog.current_setting('lock_timeout') AS restore,
       GREATEST(1, pg_catalog.floor(LEAST(
           NULLIF(EXTRACT(epoch FROM pg_catalog.current_setting('lock_timeout')::pg_catalog.interval), 0),
           EXTRACT(epoch FROM pg_catalog.current_setting('deadlock_timeout')::pg_catalog.interval) / 3
       ) * 1000))::pg_catalog.int8 AS shorter
"""


async def remove_jobs(
    connection: psycopg.AsyncConnection[Any], calls: Sequence[sql.Composable], arguments: Sequence[object],
) -> None:
    """Several removals as one statement, each lock wait ending before a deadlock check could.

    The first removal leaves `bgw_job` locked, so a scheduler starting a later
    job waits for this transaction while it holds that job's lock. The later
    removal would then close the cycle; giving up first refuses the change
    instead. In one statement the gap between removals is one routine's run.
    """
    cursor = await connection.cursor(row_factory=dict_row).execute(_WAITS)
    waits = await cursor.fetchone()
    if waits is None:
        raise RuntimeError("The lock settings could not be read")
    await connection.execute(sql.SQL("SET LOCAL lock_timeout = {}").format(sql.Literal(f"{int(waits['shorter'])}ms")))
    await connection.execute(sql.SQL("SELECT {}").format(sql.SQL(", ").join(calls)), tuple(arguments))
    await connection.execute("SELECT pg_catalog.set_config('lock_timeout', %s, true)", (waits["restore"],))
