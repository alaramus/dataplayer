"""Public Timescale inventories and their required view columns (D121)."""

from dataclasses import dataclass

from psycopg import sql

from app.adapters.postgres.system_reports import SECTION_ID, SystemReport
from app.adapters.postgres.timescale.policy_projection import policy_columns

TIMESCALE_SECTION_ID = f"{SECTION_ID}.timescale.v1"


@dataclass(frozen=True)
class TimescaleReport(SystemReport):
    public_view: str = ""
    required_columns: tuple[str, ...] = ()


def _view_report(
    key: str, title: str, description: str, view: str,
    columns: tuple[str, ...], stable_order: tuple[str, ...],
    *, text_columns: frozenset[str] = frozenset(), policies: bool = False,
) -> TimescaleReport:
    projections = sql.SQL(", ").join(
        sql.SQL("{}::text AS {}").format(sql.Identifier(name), sql.Identifier(name))
        if name in text_columns else sql.Identifier(name)
        for name in columns
    )
    statement = sql.SQL("SELECT {} FROM {} AS source ORDER BY {}").format(
        sql.SQL(", ").join((projections, *policy_columns())) if policies else projections,
        sql.Identifier("timescaledb_information", view),
        sql.SQL(", ").join(sql.Identifier(name) for name in stable_order),
    )
    return TimescaleReport(
        key=f"timescale.v1.{key}", title=title, description=description,
        statement=sql.SQL(statement.as_string()), stable_order=stable_order,
        public_view=view, required_columns=(*columns, "config") if policies else columns,
    )


_VIEW_REPORTS = (
    _view_report(
        "hypertables", "Hypertables",
        "Hypertable owners, dimension/chunk counts and compression configuration",
        "hypertables",
        (
            "hypertable_schema", "hypertable_name", "owner", "num_dimensions",
            "num_chunks", "compression_enabled", "tablespaces",
        ),
        ("hypertable_schema", "hypertable_name"),
    ),
    _view_report(
        "continuous_aggregates", "Continuous aggregates",
        "Aggregate owners, source/materialization identities and configuration",
        "continuous_aggregates",
        (
            "view_schema", "view_name", "view_owner", "hypertable_schema",
            "hypertable_name", "materialization_hypertable_schema",
            "materialization_hypertable_name", "materialized_only",
            "compression_enabled",
        ),
        ("view_schema", "view_name"),
    ),
    _view_report(
        "chunks", "Chunks",
        "Chunk identities, primary-dimension boundaries and compression status",
        "chunks",
        (
            "hypertable_schema", "hypertable_name", "chunk_schema", "chunk_name",
            "primary_dimension", "primary_dimension_type", "range_start", "range_end",
            "range_start_integer", "range_end_integer", "is_compressed",
            "chunk_tablespace",
        ),
        ("chunk_schema", "chunk_name"),
        text_columns=frozenset({"primary_dimension_type"}),
    ),
    _view_report(
        "dimensions", "Dimensions",
        "Time, integer and space dimensions of each hypertable",
        "dimensions",
        (
            "hypertable_schema", "hypertable_name", "dimension_number", "column_name",
            "column_type", "dimension_type", "time_interval", "integer_interval",
            "integer_now_func", "num_partitions",
        ),
        ("hypertable_schema", "hypertable_name", "dimension_number"),
        text_columns=frozenset({"column_type", "time_interval", "integer_now_func"}),
    ),
    _view_report(
        "jobs", "Policies and jobs",
        "Native TimescaleDB jobs, including policies and their schedules",
        "jobs",
        (
            "job_id", "application_name", "hypertable_schema", "hypertable_name",
            "proc_schema", "proc_name", "owner", "scheduled", "schedule_interval",
            "max_runtime", "max_retries", "retry_period",
        ),
        ("job_id",),
        text_columns=frozenset({"schedule_interval", "max_runtime", "retry_period"}),
        policies=True,
    ),
    _view_report(
        "job_stats", "Job statistics",
        "Recorded native job runs, outcomes and counters; unrun jobs may be absent",
        "job_stats",
        (
            "hypertable_schema", "hypertable_name", "job_id",
            "last_run_started_at", "last_successful_finish", "last_run_status",
            "job_status", "last_run_duration", "next_start",
            "total_runs", "total_successes", "total_failures",
        ),
        ("job_id",),
        text_columns=frozenset({
            "last_run_started_at", "last_successful_finish", "last_run_duration",
            "next_start",
        }),
    ),
)

# Tables that carry a chunk's name and belong to no hypertable: detached, or
# left behind. A guess, read from pg_class and the public chunks view only,
# since the private catalogs that would know are not read (D121, D208): it
# offers a table to attach and asserts nothing about where it came from.
DETACHED_CHUNKS = TimescaleReport(
    key="timescale.v1.detached_chunks", title="Detached chunks",
    description="Tables named like a chunk that no hypertable holds; Attach chunk takes one back",
    statement=sql.SQL("""
        SELECT namespace.nspname AS table_schema, relation.relname AS table_name,
               pg_catalog.pg_get_userbyid(relation.relowner) AS owner,
               CASE WHEN relation.reltuples < 0 THEN NULL ELSE relation.reltuples::pg_catalog.int8 END
                   AS row_estimate,
               pg_catalog.pg_size_pretty(pg_catalog.pg_total_relation_size(relation.oid)) AS size
        FROM pg_catalog.pg_class AS relation
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE relation.relkind = 'r'
          AND relation.relname OPERATOR(pg_catalog.~) '^_hyper_[0-9]+_[0-9]+_chunk$'
          AND NOT EXISTS (
              SELECT 1 FROM pg_catalog.pg_inherits AS inheritance WHERE inheritance.inhrelid = relation.oid
          )
          AND NOT EXISTS (
              SELECT 1 FROM timescaledb_information.chunks AS chunk
              WHERE chunk.chunk_schema = namespace.nspname AND chunk.chunk_name = relation.relname
          )
          AND pg_catalog.has_schema_privilege(namespace.oid, 'USAGE')
        ORDER BY table_schema, table_name
    """),
    stable_order=("table_schema", "table_name"),
    public_view="chunks", required_columns=("chunk_schema", "chunk_name"),
)
REPORTS: tuple[TimescaleReport, ...] = (*_VIEW_REPORTS, DETACHED_CHUNKS)

BY_ID = {report.node_id: report for report in REPORTS}
