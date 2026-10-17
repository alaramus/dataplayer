"""Apply a reviewed hypertable design in one transaction (D207).

Locks are taken in one order — DataPlayer's job guard, dimension metadata, then
the table — which is the order every single-purpose strategy here already uses
for the subset it needs, so no two of them can wait on each other in a circle.
A job's own lock comes after all three, taken by TimescaleDB's removal, which
then locks the job catalogs: TimescaleDB's order, the one its scheduler keeps
too. The scheduler takes none of the three, so nothing it holds is waited for
before that lock (D211).
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
    SparseColumns,
)
from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.compression_settings_plan import (
    order_option,
    segment_option,
)
from app.adapters.postgres.timescale.design_plan import (
    POLICY_STEPS,
    AddAgePolicy,
    AddCompactionPolicy,
    AddHashDimension,
    AddReorderPolicy,
    AttachTablespace,
    ConfigureColumnstore,
    ConvertTable,
    Count,
    CreateNowFunction,
    DesignStep,
    DetachTablespace,
    DisableColumnstore,
    HypertableDesignPlan,
    Length,
    RemovePolicy,
    SetChunkInterval,
    SetIntegerNow,
    SetPartitions,
    plan_design,
)
from app.adapters.postgres.timescale.execution import run_reviewed
from app.adapters.postgres.timescale.job_locks import JOBS_GUARD, remove_jobs
from app.adapters.postgres.timescale.plans import OrderColumn
from app.core.config import settings

_DIMENSIONS_LOCK = sql.SQL('LOCK TABLE ONLY "timescaledb_information"."dimensions" IN SHARE ROW EXCLUSIVE MODE')
_REMOVE = {"retention": "remove_retention_policy", "compression": "remove_compression_policy",
           "reorder": "remove_reorder_policy", "compaction": "remove_compaction_policy"}
_ADD = {"retention": "add_retention_policy", "compression": "add_compression_policy"}
_INTEGER_SQL = {"smallint": "pg_catalog.int2", "integer": "pg_catalog.int4", "bigint": "pg_catalog.int8"}
_SCALE = {"epoch_seconds": "", "epoch_milliseconds": " OPERATOR(pg_catalog.*) 1000",
          "epoch_microseconds": " OPERATOR(pg_catalog.*) 1000000"}


def length_type(length: Length) -> sql.SQL:
    """The cast a length takes: an interval of time, or a bigint count Timescale checks against the column."""
    return sql.SQL("pg_catalog.int8" if isinstance(length, Count) else "pg_catalog.interval")


def length_value(length: Length) -> int | str:
    return length.amount if isinstance(length, Count) else length.interval_value()


def now_function_statement(step: CreateNowFunction) -> sql.Composed:
    """The template's function: its body is the server's constant text, never the request's (D207)."""
    integer = _INTEGER_SQL[step.column_type]
    body = sql.SQL("SELECT pg_catalog.floor(EXTRACT(epoch FROM pg_catalog.now()){})::{}").format(
        sql.SQL(_SCALE[step.template]), sql.SQL(integer),
    ).as_string()
    return sql.SQL("CREATE FUNCTION {}() RETURNS {} LANGUAGE sql STABLE AS {}").format(
        sql.Identifier(step.schema_name, step.name), sql.SQL(integer), sql.Literal(body),
    )


def routine_signature(schema_name: str, name: str) -> str:
    """A zero-argument function as regprocedure reads it, identifiers quoted."""
    return sql.Identifier(schema_name, name).as_string() + "()"


async def execute_design(
    session: PostgresSession, schema_name: str, table_name: str,
    requested: HypertableDesign, reviewed_fingerprint: str,
) -> HypertableDesignPlan:
    async def replan(reader: PostgresReader) -> HypertableDesignPlan:
        return await plan_design(reader, schema_name, table_name, requested)

    return await run_reviewed(session, replan, _locks, _apply, reviewed_fingerprint)


async def execute_design_job(
    session: PostgresSession, schema_name: str, table_name: str,
    requested: HypertableDesign, unit_fingerprint: str,
) -> HypertableDesignPlan:
    """The one unit of a conversion that moves rows: the same transaction, given time (D207)."""
    async def replan(reader: PostgresReader) -> HypertableDesignPlan:
        return await plan_design(reader, schema_name, table_name, requested)

    return await run_reviewed(
        session, replan, _locks, _apply, unit_fingerprint,
        seconds=settings.TIMESCALE_CONVERSION_TIMEOUT_SECONDS, lock_seconds=5,
    )


def _locks(plan: HypertableDesignPlan) -> list[sql.SQL | sql.Composed]:
    locks: list[sql.SQL | sql.Composed] = []
    if any(isinstance(step, POLICY_STEPS) for step in plan.steps):
        locks.append(JOBS_GUARD)
    if plan.strategy.dimensions_view_oid is not None:
        locks.append(_DIMENSIONS_LOCK)
    target = plan.current.target
    mode = "ACCESS EXCLUSIVE" if plan.locks_table_exclusively else "SHARE UPDATE EXCLUSIVE"
    locks.append(sql.SQL("LOCK TABLE ONLY {} IN {} MODE").format(
        sql.Identifier(target.schema_name, target.table_name), sql.SQL(mode),
    ))
    return locks


def sparse_option(sparse: SparseColumns) -> str:
    """The option's own syntax, `bloom("s"), minmax("v")`, from validated column names."""
    return ", ".join(f"{index.kind}({sql.Identifier(index.column).as_string()})" for index in sparse.indexes)


def _segment_value(segment: SegmentBy) -> str:
    return segment_option(segment.columns) if isinstance(segment, SegmentColumns) else ""


def _order_value(order: OrderColumns) -> str:
    return order_option([
        OrderColumn(column=key.column, descending=key.descending, nulls_first=key.nulls_first)
        for key in order.columns
    ])


def columnstore_statements(table: sql.Identifier, step: ConfigureColumnstore) -> list[sql.Composed]:
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
    if step.sparse_changed:
        sparse = step.sparse_indexes
        if isinstance(sparse, SparseColumns):
            options.append(sql.SQL("timescaledb.sparse_index = {}").format(sql.Literal(sparse_option(sparse))))
        elif isinstance(sparse, NoColumns):
            options.append(sql.SQL("timescaledb.sparse_index = ''"))
        elif not step.enable:
            resets.append(sql.SQL("timescaledb.sparse_index"))
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


def _routine(plan: HypertableDesignPlan, name: str, arguments: str) -> sql.Composed:
    # `arguments` is one of the placeholder lists below, never anything from a request.
    return sql.SQL("{}(" + arguments + ")").format(sql.Identifier(_schema(plan), name))


def _call(plan: HypertableDesignPlan, name: str, arguments: str) -> sql.Composed:
    return sql.SQL("SELECT {}").format(_routine(plan, name, arguments))


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
                    "{}(%s::pg_catalog.name, %s::{}), true, false, %s)"
                ).format(
                    sql.Identifier(schema, "create_hypertable"), sql.Identifier(schema, "by_range"),
                    length_type(interval),
                ),
                (relation, column, length_value(interval), migrate),
            )
        case RemovePolicy(kind=kind):
            await connection.execute(_call(plan, _REMOVE[kind], "%s::pg_catalog.regclass, false"), (relation,))
        case AddAgePolicy(kind=kind, older_than=older_than):
            await connection.execute(
                sql.SQL("SELECT {}(%s::pg_catalog.regclass, %s::{}, false)").format(
                    sql.Identifier(_schema(plan), _ADD[kind]), length_type(older_than),
                ),
                (relation, length_value(older_than)),
            )
        case AddCompactionPolicy():
            await connection.execute(_call(plan, "add_compaction_policy", "%s::pg_catalog.regclass, false"), (relation,))
        case AddReorderPolicy(index=index):
            await connection.execute(
                _call(plan, "add_reorder_policy", "%s::pg_catalog.regclass, %s::pg_catalog.name, false"),
                (relation, index),
            )
        case SetChunkInterval(interval=interval):
            await connection.execute(
                sql.SQL("SELECT {}(%s::pg_catalog.regclass, %s::{}, %s::pg_catalog.name)").format(
                    sql.Identifier(_schema(plan), "set_chunk_time_interval"), length_type(interval),
                ),
                (relation, length_value(interval), target.column_name),
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
            for statement in columnstore_statements(table, step):
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
        case CreateNowFunction():
            await connection.execute(now_function_statement(step))
        case SetIntegerNow(schema_name=schema_name, name=name, replace=replace):
            await connection.execute(
                _call(plan, "set_integer_now_func",
                      "%s::pg_catalog.regclass, "
                      "%s::pg_catalog.regprocedure::pg_catalog.oid::pg_catalog.regproc, %s"),
                (relation, routine_signature(schema_name, name), replace),
            )


async def _apply(connection: psycopg.AsyncConnection[Any], plan: HypertableDesignPlan) -> None:
    # Removals lead the steps, so running them first keeps the planned order.
    removals = [step for step in plan.steps if isinstance(step, RemovePolicy)]
    if len(removals) > 1:
        await remove_jobs(
            connection, [_routine(plan, _REMOVE[step.kind], "%s::pg_catalog.regclass, false") for step in removals],
            [plan.current.target.relation_oid] * len(removals),
        )
    for step in plan.steps:
        if len(removals) <= 1 or not isinstance(step, RemovePolicy):
            await _step(connection, plan, step)
