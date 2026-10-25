"""What a ClickHouse table's structure may be changed to: types and skipping indexes."""

from app.adapters.relation import ColumnTypeOption, IndexMethodOption
from app.core.translation import N_

# The closed vocabulary of types a column is given (D27), spelt as ClickHouse
# prints them. A code is never SQL. Scalars only: each is a type
# `accurateCastOrNull` can try a value as, which is how a change is checked
# before it is made (D273).
CLICKHOUSE_COLUMN_TYPE_OPTIONS = [
    ColumnTypeOption(code="text", title=N_("Text"), sql="String"),
    ColumnTypeOption(code="repeated_text", title=N_("Text with few distinct values"), sql="LowCardinality(String)"),
    ColumnTypeOption(code="int32", title=N_("Integer"), sql="Int32"),
    ColumnTypeOption(code="int64", title=N_("Big integer"), sql="Int64"),
    ColumnTypeOption(code="uint64", title=N_("Unsigned big integer"), sql="UInt64"),
    ColumnTypeOption(code="decimal", title=N_("Decimal"), sql="Decimal(38, 10)"),
    ColumnTypeOption(code="float64", title=N_("Floating point"), sql="Float64"),
    ColumnTypeOption(code="boolean", title=N_("Boolean"), sql="Bool"),
    ColumnTypeOption(code="date", title=N_("Date"), sql="Date32"),
    ColumnTypeOption(code="datetime", title=N_("Date and time (UTC)"), sql="DateTime('UTC')"),
    ColumnTypeOption(
        code="datetime64", title=N_("Date and time with milliseconds (UTC)"), sql="DateTime64(3, 'UTC')"
    ),
    ColumnTypeOption(code="uuid", title=N_("UUID"), sql="UUID"),
    ColumnTypeOption(code="ipv4", title=N_("IPv4 address"), sql="IPv4"),
    ColumnTypeOption(code="ipv6", title=N_("IPv6 address"), sql="IPv6"),
]
COLUMN_TYPES = {option.code: option for option in CLICKHOUSE_COLUMN_TYPE_OPTIONS}

# Data skipping indexes. None is unique: a ClickHouse index skips granules
# that cannot hold a value and never refuses a row (D269). Each takes a tuple
# of columns.
CLICKHOUSE_INDEX_METHODS = [
    IndexMethodOption(
        code="minmax",
        title=N_("Min and max"),
        sql="minmax",
        unique_supported=False,
        multi_column_supported=True,
    ),
    IndexMethodOption(
        code="set",
        title=N_("Set of values"),
        sql="set(100)",
        unique_supported=False,
        multi_column_supported=True,
    ),
    IndexMethodOption(
        code="bloom_filter",
        title=N_("Bloom filter"),
        sql="bloom_filter",
        unique_supported=False,
        multi_column_supported=True,
    ),
]
INDEX_METHODS = {option.code: option for option in CLICKHOUSE_INDEX_METHODS}
