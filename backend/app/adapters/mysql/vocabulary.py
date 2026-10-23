"""What a MySQL table's structure may be changed to: types and index methods."""

from app.adapters.relation import ColumnTypeOption, IndexMethodOption
from app.core.translation import N_

# The closed vocabulary of types a column is given (D27), spelt as MySQL 8
# prints them. A code is never SQL.
MYSQL_COLUMN_TYPE_OPTIONS = [
    ColumnTypeOption(code="text", title=N_("Text"), sql="varchar(255)"),
    ColumnTypeOption(code="long_text", title=N_("Long text"), sql="text"),
    ColumnTypeOption(code="integer", title=N_("Integer"), sql="int"),
    ColumnTypeOption(code="bigint", title=N_("Big integer"), sql="bigint"),
    ColumnTypeOption(code="decimal", title=N_("Decimal"), sql="decimal(20,6)"),
    ColumnTypeOption(code="double", title=N_("Floating point"), sql="double"),
    ColumnTypeOption(code="boolean", title=N_("Boolean (0 or 1)"), sql="tinyint(1)"),
    ColumnTypeOption(code="date", title=N_("Date"), sql="date"),
    ColumnTypeOption(code="datetime", title=N_("Date and time"), sql="datetime"),
    ColumnTypeOption(code="timestamp", title=N_("Timestamp (UTC)"), sql="timestamp"),
    ColumnTypeOption(code="json", title=N_("JSON"), sql="json"),
    ColumnTypeOption(code="uuid", title=N_("UUID as text"), sql="char(36)"),
]
COLUMN_TYPES = {option.code: option for option in MYSQL_COLUMN_TYPE_OPTIONS}

# InnoDB's index kinds, with what each can do. Unlike PostgreSQL's access
# methods these are fixed by the engine rather than installed, so they are
# written down here. HASH is not offered: InnoDB accepts it and builds a
# B-tree, which would show the person a method they did not get.
MYSQL_INDEX_METHODS = [
    IndexMethodOption(
        code="btree", title=N_("B-tree"), sql="BTREE", unique_supported=True, multi_column_supported=True
    ),
    IndexMethodOption(
        code="fulltext",
        title=N_("Full text"),
        sql="FULLTEXT",
        unique_supported=False,
        multi_column_supported=True,
    ),
    IndexMethodOption(
        code="spatial", title=N_("Spatial"), sql="SPATIAL", unique_supported=False, multi_column_supported=False
    ),
]
INDEX_METHODS = {option.code: option for option in MYSQL_INDEX_METHODS}

_TEXT_TYPES = ("varchar", "char", "text", "tinytext", "mediumtext", "longtext")


def is_text(type_sql: str) -> bool:
    return type_sql.split("(", 1)[0].split(" ", 1)[0].lower() in _TEXT_TYPES
