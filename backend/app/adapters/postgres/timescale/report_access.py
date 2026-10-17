"""Validate optional report APIs without disabling baseline inspection (D120)."""

from psycopg import sql

from app.adapters.postgres.inspection import PostgresReader
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import SystemReport
from app.adapters.postgres.timescale.reports import TimescaleReport
from app.adapters.protocol import AdapterError
from app.core.translation import say

_COLUMNS = """
SELECT attribute.attname AS column_name
FROM pg_catalog.pg_attribute AS attribute
JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
JOIN pg_catalog.pg_depend AS dependency
  ON dependency.classid = 'pg_catalog.pg_class'::pg_catalog.regclass
 AND dependency.objid = relation.oid
 AND dependency.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass
 AND dependency.deptype = 'e'
JOIN pg_catalog.pg_extension AS extension ON extension.oid = dependency.refobjid
WHERE extension.extname = 'timescaledb'
  AND namespace.nspname = 'timescaledb_information'
  AND relation.relname = %s
  AND relation.relkind = 'v'
  AND attribute.attnum > 0 AND NOT attribute.attisdropped
  AND attribute.attname = ANY(%s)
LIMIT %s
"""


async def require_report(session: PostgresSession, report: SystemReport) -> None:
    if not isinstance(report, TimescaleReport):
        return
    try:
        await require_public_view(session, report.public_view, report.required_columns)
        await session.query(
            sql.SQL("SELECT * FROM ({}) AS report LIMIT 0")
            .format(report.statement).as_string(),
            inspection=True,
        )
    except AdapterError as exc:
        if exc.error_kind in {"auth", "network", "timeout"}:
            raise
        # Without the report's title, a word that would stay English inside
        # the sentence; the refusal is shown where the report is opened.
        raise ValueError(say("This report cannot be inspected by this connection")) from None


async def require_public_view(
    session: PostgresReader, view: str, required_columns: tuple[str, ...]
) -> None:
    columns = await session.query(
        _COLUMNS, (view, list(required_columns), len(required_columns) + 1),
        inspection=True,
    )
    if {row["column_name"] for row in columns} != set(required_columns):
        raise ValueError(say("The installed TimescaleDB lacks the public API for this view"))
