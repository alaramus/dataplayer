"""Public Timescale inventories and their required view columns (D121)."""

from dataclasses import dataclass

from psycopg import sql

from app.adapters.postgres.system_reports import SECTION_ID, SystemReport

TIMESCALE_SECTION_ID = f"{SECTION_ID}.timescale.v1"


@dataclass(frozen=True)
class TimescaleReport(SystemReport):
    public_view: str = ""
    required_columns: tuple[str, ...] = ()


def _view_report(
    key: str, title: str, description: str, view: str,
    columns: tuple[str, ...], stable_order: tuple[str, ...],
    *, text_columns: frozenset[str] = frozenset(),
) -> TimescaleReport:
    projections = sql.SQL(", ").join(
        sql.SQL("{}::text AS {}").format(sql.Identifier(name), sql.Identifier(name))
        if name in text_columns else sql.Identifier(name)
        for name in columns
    )
    statement = sql.SQL("SELECT {} FROM {} ORDER BY {}").format(
        projections,
        sql.Identifier("timescaledb_information", view),
        sql.SQL(", ").join(sql.Identifier(name) for name in stable_order),
    )
    return TimescaleReport(
        key=f"timescale.v1.{key}", title=title, description=description,
        statement=sql.SQL(statement.as_string()), stable_order=stable_order,
        public_view=view, required_columns=columns,
    )


REPORTS = (
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
            "compression_enabled", "finalized",
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

BY_ID = {report.node_id: report for report in REPORTS}
