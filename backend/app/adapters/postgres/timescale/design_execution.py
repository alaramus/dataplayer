"""Apply a reviewed hypertable design in one transaction (D207).

Locks are taken in one order — job metadata, dimension metadata, then the
table — which is the order every single-purpose strategy here already uses for
the subset it needs, so no two of them can wait on each other in a circle.
"""

from typing import Any

import psycopg
from psycopg import sql

from app.adapters.hypertable_design import (
    HypertableDesign,
    NoColumns,
    OrderBy,
    OrderColumns,
    SegmentBy,
    SegmentColumns,
)
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.age_policy_execution import JOBS_LOCK
from app.adapters.postgres.timescale.compression_settings_plan import (
    order_option,
    segment_option,
)
from app.adapters.postgres.timescale.design_plan import (
    AddAgePolicy,
    AddHashDimension,
    AddReorderPolicy,
    AttachTablespace,
    ConfigureColumnstore,
    ConvertTable,
    DesignStep,
    DetachTablespace,
    DisableColumnstore,
    HypertableDesignPlan,
    RemovePolicy,
    SetChunkInterval,
    SetPartitions,
    plan_design,
)
from app.adapters.postgres.timescale.execution import run_reviewed
from app.adapters.postgres.timescale.plans import OrderColumn
from app.core.config import settings

_DIMENSIONS_LOCK = sql.SQL('LOCK TABLE ONLY "timescaledb_information"."dimensions" IN SHARE ROW EXCLUSIVE MODE')
_REMOVE = {"retention": "remove_retention_policy", "compression": "remove_compression_policy",
           "reorder": "remove_reorder_policy"}
_ADD = {"retention": "add_retention_policy", "compression": "add_compression_policy"}


async def execute_design(
    session: PostgresSession, schema_name: str, table_name: str,
    requested: HypertableDesign, reviewed_fingerprint: str,
) -> HypertableDesignPlan:
    async def replan(reader: PostgresReader) -> HypertableDesignPlan:
        return await plan_design(reader, schema_name, table_name, requested)

    return await run_reviewed(session, replan, _locks, _apply, reviewed_fingerprint, "hypertable change")


async def execute_design_job(
    session: PostgresSession, schema_name: str, table_name: str,
    requested: HypertableDesign, unit_fingerprint: str,
) -> HypertableDesignPlan:
    """The one unit of a conversion that moves rows: the same transaction, given time (D207)."""
    async def replan(reader: PostgresReader) -> HypertableDesignPlan:
        return await plan_design(reader, schema_name, table_name, requested)

    return await run_reviewed(
        session, replan, _locks, _apply, unit_fingerprint, "conversion",
        seconds=settings.TIMESCALE_CONVERSION_TIMEOUT_SECONDS, lock_seconds=5,
    )


def _locks(plan: HypertableDesignPlan) -> list[sql.SQL | sql.Composed]:
    locks: list[sql.SQL | sql.Composed] = []
    if plan.strategy.jobs_view_oid is not None:
        locks.append(JOBS_LOCK)
    if plan.strategy.dimensions_view_oid is not None:
        locks.append(_DIMENSIONS_LOCK)
    target = plan.current.target
    mode = "ACCESS EXCLUSIVE" if plan.locks_table_exclusively else "SHARE UPDATE EXCLUSIVE"
    locks.append(sql.SQL("LOCK TABLE ONLY {} IN {} MODE").format(
        sql.Identifier(target.schema_name, target.table_name), sql.SQL(mode),
    ))
    return locks


def _segment_value(segment: SegmentBy) -> str:
    return segment_option(segment.columns) if isinstance(segment, SegmentColumns) else ""


def _order_value(order: OrderColumns) -> str:
    return order_option([
        OrderColumn(column=key.column, descending=key.descending, nulls_first=key.nulls_first)
        for key in order.columns
    ])


def _columnstore_statements(table: sql.Identifier, step: ConfigureColumnstore) -> list[sql.Composed]:
    options: list[sql.Composable] = []
    resets: list[sql.Composable] = []
    if step.enable:
        options.append(sql.SQL("timescaledb.compress"))
    segment: SegmentBy = step.segment_by
    order: OrderBy = step.order_by
    if isinstance(segment, SegmentColumns | NoColumns):
        options.append(sql.SQL("timescaledb.compress_segmentby = {}").format(sql.Literal(_segment_value(segment))))
    elif step.segment_changed and not step.enable:
        resets.append(sql.SQL("timescaledb.compress_segmentby"))
    if isinstance(order, OrderColumns):
        options.append(sql.SQL("timescaledb.compress_orderby = {}").format(sql.Literal(_order_value(order))))
    elif step.order_changed and not step.enable:
        resets.append(sql.SQL("timescaledb.compress_orderby"))
    if step.merge_changed:
        merge = "0" if step.merge_interval is None else step.merge_interval.interval_value()
        options.append(sql.SQL("timescaledb.compress_chunk_time_interval = {}").format(sql.Literal(merge)))
    statements: list[sql.Composed] = []
    if options:
        statements.append(sql.SQL("ALTER TABLE {} SET ({})").format(table, sql.SQL(", ").join(options)))
    if resets:
        statements.append(sql.SQL("ALTER TABLE {} RESET ({})").format(table, sql.SQL(", ").join(resets)))
    return statements


def _schema(plan: HypertableDesignPlan) -> str:
    # Planning discovers a routine for every step that calls one, which sets the schema.
    if plan.strategy.function_schema is None:
        raise RuntimeError("A routine step was planned without a discovered schema")
    return plan.strategy.function_schema


def _call(plan: HypertableDesignPlan, name: str, arguments: str) -> sql.Composed:
    # `arguments` is one of the placeholder lists below, never anything from a request.
    return sql.SQL("SELECT {}(" + arguments + ")").format(sql.Identifier(_schema(plan), name))


async def _step(connection: psycopg.AsyncConnection[Any], plan: HypertableDesignPlan, step: DesignStep) -> None:
    target = plan.current.target
    table = sql.Identifier(target.schema_name, target.table_name)
    relation = target.relation_oid
    match step:
        case ConvertTable(column=column, interval=interval, migrate=migrate):
            conversion = plan.strategy.conversion
            if conversion is None:
                raise RuntimeError("A conversion was planned without its strategy")
            schema = conversion.function_schema
            # Default indexes on and if_not_exists off, as the single-purpose conversion has them.
            await connection.execute(
                sql.SQL(
                    "SELECT hypertable_id FROM {}(%s::pg_catalog.regclass, "
                    "{}(%s::pg_catalog.name, %s::pg_catalog.interval), true, false, %s)"
                ).format(sql.Identifier(schema, "create_hypertable"), sql.Identifier(schema, "by_range")),
                (relation, column, interval.interval_value(), migrate),
            )
        case RemovePolicy(kind=kind):
            await connection.execute(_call(plan, _REMOVE[kind], "%s::pg_catalog.regclass, false"), (relation,))
        case AddAgePolicy(kind=kind, older_than=older_than):
            await connection.execute(
                _call(plan, _ADD[kind], "%s::pg_catalog.regclass, %s::pg_catalog.interval, false"),
                (relation, older_than.interval_value()),
            )
        case AddReorderPolicy(index=index):
            await connection.execute(
                _call(plan, "add_reorder_policy", "%s::pg_catalog.regclass, %s::pg_catalog.name, false"),
                (relation, index),
            )
        case SetChunkInterval(interval=interval):
            await connection.execute(
                _call(plan, "set_chunk_time_interval",
                      "%s::pg_catalog.regclass, %s::pg_catalog.interval, %s::pg_catalog.name"),
                (relation, interval.interval_value(), target.column_name),
            )
        case SetPartitions(column=column, partitions=partitions):
            await connection.execute(
                _call(plan, "set_number_partitions",
                      "%s::pg_catalog.regclass, %s::pg_catalog.int4, %s::pg_catalog.name"),
                (relation, partitions, column),
            )
        case AddHashDimension(column=column, partitions=partitions):
            schema = _schema(plan)
            await connection.execute(
                sql.SQL("SELECT dimension_id FROM {}(%s::pg_catalog.regclass, "
                        "{}(%s::pg_catalog.name, %s::pg_catalog.int4), false)").format(
                    sql.Identifier(schema, "add_dimension"), sql.Identifier(schema, "by_hash"),
                ),
                (relation, column, partitions),
            )
        case ConfigureColumnstore():
            for statement in _columnstore_statements(table, step):
                await connection.execute(statement)
        case DisableColumnstore():
            await connection.execute(sql.SQL("ALTER TABLE {} SET (timescaledb.compress = false)").format(table))
        case AttachTablespace(name=name):
            await connection.execute(
                _call(plan, "attach_tablespace", "%s::pg_catalog.name, %s::pg_catalog.regclass"), (name, relation),
            )
        case DetachTablespace(name=name):
            await connection.execute(
                _call(plan, "detach_tablespace", "%s::pg_catalog.name, %s::pg_catalog.regclass"), (name, relation),
            )


async def _apply(connection: psycopg.AsyncConnection[Any], plan: HypertableDesignPlan) -> None:
    for step in plan.steps:
        await _step(connection, plan, step)
