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
    SystemReport(
        key="timescale.v1.hypertables",
        title="Hypertables",
        description="Logical hypertables identified by schema and name",
        statement=sql.SQL("""
            SELECT hypertable_schema, hypertable_name
            FROM timescaledb_information.hypertables
            ORDER BY hypertable_schema, hypertable_name
        """),
        stable_order=("hypertable_schema", "hypertable_name"),
    ),
    SystemReport(
        key="timescale.v1.continuous_aggregates",
        title="Continuous aggregates",
        description="Continuous aggregate views and their materialization hypertables",
        statement=sql.SQL("""
            SELECT view_schema, view_name,
                   materialization_hypertable_schema,
                   materialization_hypertable_name
            FROM timescaledb_information.continuous_aggregates
            ORDER BY view_schema, view_name
        """),
        stable_order=("view_schema", "view_name"),
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
)

BY_ID = {report.node_id: report for report in REPORTS}
