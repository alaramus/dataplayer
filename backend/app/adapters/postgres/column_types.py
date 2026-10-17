"""The closed PostgreSQL type vocabulary offered for new columns."""

from psycopg import sql

from app.adapters.relation import ColumnTypeOption
from app.core.translation import N_

POSTGRES_COLUMN_TYPE_OPTIONS = [
    ColumnTypeOption(code="text", title=N_("Text"), sql="text"),
    ColumnTypeOption(code="integer", title=N_("Integer"), sql="integer"),
    ColumnTypeOption(code="bigint", title=N_("Big integer"), sql="bigint"),
    ColumnTypeOption(code="numeric", title=N_("Numeric"), sql="numeric"),
    ColumnTypeOption(code="boolean", title=N_("Boolean"), sql="boolean"),
    ColumnTypeOption(code="date", title=N_("Date"), sql="date"),
    ColumnTypeOption(
        code="timestamp_tz", title=N_("Timestamp with time zone"), sql="timestamp with time zone"
    ),
    ColumnTypeOption(code="jsonb", title=N_("JSON"), sql="jsonb"),
    ColumnTypeOption(code="uuid", title=N_("UUID"), sql="uuid"),
]

POSTGRES_COLUMN_TYPES: dict[str, sql.SQL] = {
    "text": sql.SQL("text"),
    "integer": sql.SQL("integer"),
    "bigint": sql.SQL("bigint"),
    "numeric": sql.SQL("numeric"),
    "boolean": sql.SQL("boolean"),
    "date": sql.SQL("date"),
    "timestamp_tz": sql.SQL("timestamp with time zone"),
    "jsonb": sql.SQL("jsonb"),
    "uuid": sql.SQL("uuid"),
}
