"""Public relation inventories using the discovery baseline (D121)."""

from psycopg import sql

from app.adapters.postgres.system_reports import SECTION_ID, SystemReport

TIMESCALE_SECTION_ID = f"{SECTION_ID}.timescale.v1"

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
)

BY_ID = {report.node_id: report for report in REPORTS}
