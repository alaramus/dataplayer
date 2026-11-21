"""What a DuckDB table's structure may be changed to: types and index methods (D396)."""

from app.adapters.relation import ColumnTypeOption, IndexMethodOption
from app.core.translation import N_

# The closed vocabulary of types a column is given (D27), spelt as DuckDB
# names them, so `duckdb_columns()` reads each back as the same text. A code
# is never SQL.
COLUMN_TYPE_OPTIONS = [
    ColumnTypeOption(code="text", title=N_("Text"), sql="VARCHAR"),
    ColumnTypeOption(code="smallint", title=N_("Small integer"), sql="SMALLINT"),
    ColumnTypeOption(code="integer", title=N_("Integer"), sql="INTEGER"),
    ColumnTypeOption(code="bigint", title=N_("Big integer"), sql="BIGINT"),
    ColumnTypeOption(code="hugeint", title=N_("128-bit integer"), sql="HUGEINT"),
    ColumnTypeOption(code="double", title=N_("Floating point"), sql="DOUBLE"),
    ColumnTypeOption(code="decimal", title=N_("Decimal"), sql="DECIMAL(18,3)"),
    ColumnTypeOption(code="boolean", title=N_("Boolean"), sql="BOOLEAN"),
    ColumnTypeOption(code="date", title=N_("Date"), sql="DATE"),
    ColumnTypeOption(code="time", title=N_("Time"), sql="TIME"),
    ColumnTypeOption(code="timestamp", title=N_("Date and time"), sql="TIMESTAMP"),
    ColumnTypeOption(
        code="timestamptz", title=N_("Date and time with time zone"), sql="TIMESTAMP WITH TIME ZONE"
    ),
    ColumnTypeOption(code="interval", title=N_("Interval"), sql="INTERVAL"),
    ColumnTypeOption(code="uuid", title=N_("UUID"), sql="UUID"),
    ColumnTypeOption(code="json", title=N_("JSON"), sql="JSON"),
    ColumnTypeOption(code="blob", title=N_("Binary"), sql="BLOB"),
]


def column_type(code: str) -> ColumnTypeOption | None:
    return next((option for option in COLUMN_TYPE_OPTIONS if option.code == code), None)


# DuckDB builds one kind of index, the adaptive radix tree.
INDEX_METHODS = [
    IndexMethodOption(
        code="art",
        title=N_("Adaptive radix tree"),
        sql="",
        unique_supported=True,
        multi_column_supported=True,
    ),
]
