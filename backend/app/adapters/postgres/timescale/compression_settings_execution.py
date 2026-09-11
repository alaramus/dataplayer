"""Compression settings strategy: the source's own lock, taken first and under a timeout (D123)."""

from typing import Any

import psycopg
from psycopg import sql

from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.compression_settings_plan import (
    order_option,
    plan_compression_settings,
    segment_option,
)
from app.adapters.postgres.timescale.execution import run_reviewed
from app.adapters.postgres.timescale.plans import CompressionSettingsPlan


async def execute_compression_settings(
    session: PostgresSession, schema_name: str, table_name: str,
    segment_text: str, order_text: str, reviewed_fingerprint: str,
) -> CompressionSettingsPlan:
    async def replan(reader: PostgresReader) -> CompressionSettingsPlan:
        return await plan_compression_settings(reader, schema_name, table_name, segment_text, order_text)

    return await run_reviewed(
        session, replan, _locks, _apply, reviewed_fingerprint, "compression settings change",
    )


def _locks(plan: CompressionSettingsPlan) -> list[sql.SQL | sql.Composed]:
    # TimescaleDB takes this lock inside ALTER TABLE; taking it first bounds the wait.
    return [sql.SQL("LOCK TABLE ONLY {} IN ACCESS EXCLUSIVE MODE").format(
        sql.Identifier(plan.target.schema_name, plan.target.table_name),
    )]


async def _apply(connection: psycopg.AsyncConnection[Any], plan: CompressionSettingsPlan) -> None:
    # Both lists are always explicit, so the source neither keeps an old one nor derives a default.
    await connection.execute(sql.SQL(
        "ALTER TABLE {} SET (timescaledb.compress, "
        "timescaledb.compress_segmentby = {}, timescaledb.compress_orderby = {})"
    ).format(
        sql.Identifier(plan.target.schema_name, plan.target.table_name),
        sql.Literal(segment_option(plan.segment_by)),
        sql.Literal(order_option(plan.order_by)),
    ))
