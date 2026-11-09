"""What a Cassandra table's structure may be changed to: types and secondary indexes (D346)."""

from app.adapters.relation import ColumnTypeOption, IndexMethodOption
from app.core.translation import N_

# The closed vocabulary of types a column is given (D27), spelt as CQL writes
# them. A code is never CQL.
CASSANDRA_COLUMN_TYPE_OPTIONS = [
    ColumnTypeOption(code="text", title=N_("Text"), sql="text"),
    ColumnTypeOption(code="int", title=N_("Integer"), sql="int"),
    ColumnTypeOption(code="bigint", title=N_("Big integer"), sql="bigint"),
    ColumnTypeOption(code="varint", title=N_("Integer of any size"), sql="varint"),
    ColumnTypeOption(code="decimal", title=N_("Decimal"), sql="decimal"),
    ColumnTypeOption(code="double", title=N_("Floating point"), sql="double"),
    ColumnTypeOption(code="boolean", title=N_("Boolean"), sql="boolean"),
    ColumnTypeOption(code="date", title=N_("Date"), sql="date"),
    ColumnTypeOption(
        code="timestamp", title=N_("Date and time (UTC)"), sql="timestamp"
    ),
    ColumnTypeOption(code="time", title=N_("Time of day"), sql="time"),
    ColumnTypeOption(code="uuid", title=N_("UUID"), sql="uuid"),
    ColumnTypeOption(code="timeuuid", title=N_("Time-based UUID"), sql="timeuuid"),
    ColumnTypeOption(code="inet", title=N_("IP address"), sql="inet"),
    ColumnTypeOption(code="blob", title=N_("Bytes"), sql="blob"),
    ColumnTypeOption(code="text_list", title=N_("List of text"), sql="list<text>"),
    ColumnTypeOption(code="text_set", title=N_("Set of text"), sql="set<text>"),
    ColumnTypeOption(
        code="text_map", title=N_("Map of text to text"), sql="map<text, text>"
    ),
]
COLUMN_TYPES = {option.code: option for option in CASSANDRA_COLUMN_TYPE_OPTIONS}

# Secondary indexes, one column each and none unique. Cassandra 5 has the
# storage-attached index and the legacy one; ScyllaDB has its global index.
CASSANDRA_INDEX_METHODS = [
    IndexMethodOption(
        code="sai",
        title=N_("Storage-attached index"),
        sql="sai",
        unique_supported=False,
        multi_column_supported=False,
    ),
    IndexMethodOption(
        code="legacy",
        title=N_("Legacy secondary index"),
        sql="",
        unique_supported=False,
        multi_column_supported=False,
    ),
]
SCYLLA_INDEX_METHODS = [
    IndexMethodOption(
        code="global",
        title=N_("Global secondary index"),
        sql="",
        unique_supported=False,
        multi_column_supported=False,
    ),
]


def index_methods(scylla: bool, version: tuple[int, ...]) -> list[IndexMethodOption]:
    """The methods this server offers: the storage-attached index came with Cassandra 5."""
    if scylla:
        return SCYLLA_INDEX_METHODS
    if version[:1] >= (5,):
        return CASSANDRA_INDEX_METHODS
    return CASSANDRA_INDEX_METHODS[1:]
