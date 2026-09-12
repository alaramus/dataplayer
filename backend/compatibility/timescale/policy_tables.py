"""Disposable hypertables and helpers shared by the policy mutation scenarios."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from psycopg import sql

from app.adapters.actions import Previews
from app.adapters.postgres.actions import PostgresActions
from app.adapters.postgres.catalog import PostgresCatalog
from compatibility.timescale.source import TimescaleSource

# What discovery settled on for one routine OID, so a scenario can check the
# leading arguments without naming the release's own total.
DISCOVERED = """
SELECT proname, proargtypes::text AS arguments, pronargs - pronargdefaults AS required
FROM pg_catalog.pg_proc WHERE oid = %s::pg_catalog.oid
"""

_JOBS = """
    SELECT job_id, scheduled FROM timescaledb_information.jobs
    WHERE hypertable_schema = %s AND hypertable_name = %s AND proc_name = %s
    ORDER BY job_id
"""


@dataclass(frozen=True)
class PolicyTable:
    schema: str
    table: str = 'readings"quoted'

    @property
    def identifier(self) -> sql.Identifier:
        return sql.Identifier(self.schema, self.table)

    @property
    def node_id(self) -> str:
        return f"{self.schema}.{self.table}"


@asynccontextmanager
async def disposable_hypertable(
    source: TimescaleSource, prefix: str, *, compressed: bool = False,
) -> AsyncIterator[PolicyTable]:
    target = PolicyTable(f"{prefix}_{uuid.uuid4().hex[:12]}")
    session = source.session()
    await session.schema_change(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(target.schema)).as_string())
    try:
        await create_hypertable(source, target, compressed=compressed)
        await session.schema_change(sql.SQL(
            "INSERT INTO {} VALUES ('2026-01-01 00:00:00+00', 1), ('2026-01-20 00:00:00+00', 2)"
        ).format(target.identifier).as_string())
        yield target
    finally:
        # Dropping the hypertable removes its policy jobs with it.
        await session.schema_change(sql.SQL("DROP SCHEMA {} CASCADE").format(
            sql.Identifier(target.schema),
        ).as_string())


async def create_hypertable(source: TimescaleSource, target: PolicyTable, *, compressed: bool) -> None:
    session = source.session()
    await session.schema_change(sql.SQL(
        "CREATE TABLE {} (observed_at timestamptz NOT NULL, value integer NOT NULL)"
    ).format(target.identifier).as_string())
    await session.query(
        "SELECT public.create_hypertable(%s::regclass, 'observed_at', "
        "chunk_time_interval => INTERVAL '7 days')", (target.identifier.as_string(),),
    )
    if compressed:
        await session.schema_change(sql.SQL(
            "ALTER TABLE {} SET (timescaledb.compress, timescaledb.compress_orderby = 'observed_at')"
        ).format(target.identifier).as_string())


def registry(source: TimescaleSource) -> PostgresActions:
    session = source.session()
    return PostgresActions(session, PostgresCatalog(session))


async def reviewed(action: Previews, node_id: str, params: dict[str, object]) -> str:
    preview = await action.preview(node_id, params)
    assert not preview.blocked, preview.summary
    assert preview.fingerprint is not None
    return preview.fingerprint


async def jobs(source: TimescaleSource, target: PolicyTable, routine: str) -> list[dict[str, Any]]:
    return await source.session().query(_JOBS, (target.schema, target.table, routine))


async def rows(source: TimescaleSource, target: PolicyTable) -> list[dict[str, Any]]:
    return await source.session().query(sql.SQL(
        "SELECT observed_at, value FROM {} ORDER BY observed_at"
    ).format(target.identifier).as_string())
