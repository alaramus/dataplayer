"""What a SQLite table's structure may be changed to: types and index methods (D255)."""

from app.adapters.relation import ColumnTypeOption, IndexMethodOption
from app.core.translation import N_

# The closed vocabulary of types a column is given (D27), spelt as SQLite reads
# them: each is a declared type whose affinity, and whose name, the catalog
# reads back as the category it is offered as (D250). A code is never SQL.
SQLITE_COLUMN_TYPE_OPTIONS = [
    ColumnTypeOption(code="text", title=N_("Text"), sql="TEXT"),
    ColumnTypeOption(code="integer", title=N_("Integer"), sql="INTEGER"),
    ColumnTypeOption(code="real", title=N_("Floating point"), sql="REAL"),
    ColumnTypeOption(code="numeric", title=N_("Number"), sql="NUMERIC"),
    ColumnTypeOption(code="boolean", title=N_("Boolean (0 or 1)"), sql="BOOLEAN"),
    ColumnTypeOption(code="date", title=N_("Date"), sql="DATE"),
    ColumnTypeOption(code="datetime", title=N_("Date and time"), sql="DATETIME"),
    ColumnTypeOption(code="json", title=N_("JSON"), sql="JSON"),
    ColumnTypeOption(code="uuid", title=N_("UUID as text"), sql="UUID"),
    ColumnTypeOption(code="blob", title=N_("Binary"), sql="BLOB"),
]
# A STRICT table takes these and no others.
STRICT_COLUMN_TYPE_OPTIONS = [
    ColumnTypeOption(code="text", title=N_("Text"), sql="TEXT"),
    ColumnTypeOption(code="integer", title=N_("Integer"), sql="INTEGER"),
    ColumnTypeOption(code="real", title=N_("Floating point"), sql="REAL"),
    ColumnTypeOption(code="blob", title=N_("Binary"), sql="BLOB"),
    ColumnTypeOption(code="any", title=N_("Any value"), sql="ANY"),
]


def column_types(strict: bool) -> list[ColumnTypeOption]:
    return STRICT_COLUMN_TYPE_OPTIONS if strict else SQLITE_COLUMN_TYPE_OPTIONS


def column_type(code: str, strict: bool) -> ColumnTypeOption | None:
    return next((option for option in column_types(strict) if option.code == code), None)


# SQLite builds one kind of index.
SQLITE_INDEX_METHODS = [
    IndexMethodOption(
        code="btree",
        title=N_("B-tree"),
        sql="",
        unique_supported=True,
        multi_column_supported=True,
    ),
]
