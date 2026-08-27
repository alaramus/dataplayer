"""The closed PostgreSQL type vocabulary offered for new columns."""

from psycopg import sql

from app.adapters.relation import ColumnTypeOption

POSTGRES_COLUMN_TYPE_OPTIONS = [
    ColumnTypeOption(code="text", title="Text", sql="text"),
    ColumnTypeOption(code="integer", title="Integer", sql="integer"),
    ColumnTypeOption(code="bigint", title="Big integer", sql="bigint"),
    ColumnTypeOption(code="numeric", title="Numeric", sql="numeric"),
    ColumnTypeOption(code="boolean", title="Boolean", sql="boolean"),
    ColumnTypeOption(code="date", title="Date", sql="date"),
    ColumnTypeOption(
        code="timestamp_tz", title="Timestamp with time zone", sql="timestamp with time zone"
    ),
    ColumnTypeOption(code="jsonb", title="JSON", sql="jsonb"),
    ColumnTypeOption(code="uuid", title="UUID", sql="uuid"),
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
