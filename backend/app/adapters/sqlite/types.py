"""SQLite column types in the adapter-neutral vocabulary, and values as text (D250).

A declared type is only an affinity: the column takes whatever is written to
it, so a category says what the column is meant to hold and a value is shown
by what it is.
"""

import re
from typing import Any

from app.adapters.relation import ColumnType, TypeCategory
from app.adapters.sqlite.session import Undecodable

# Names people write for what SQLite has no class of. Read before the
# affinity rules, which would call each of them NUMERIC or TEXT.
_NAMED: dict[str, TypeCategory] = {
    **dict.fromkeys(("BOOLEAN", "BOOL"), "boolean"),
    **dict.fromkeys(("DATE", "DATETIME", "TIMESTAMP", "TIME"), "datetime"),
    "JSON": "json",
    **dict.fromkeys(("UUID", "GUID"), "uuid"),
}

_SIZE = re.compile(r"\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)")
_LENGTHED = ("CHAR", "CLOB", "TEXT")
_EXACT = ("DECIMAL", "NUMERIC")


def base_name(declared: str) -> str:
    """The first word of a declared type, in capitals: `VARCHAR` of `varchar(20)`."""
    return declared.split("(", 1)[0].strip().split(" ", 1)[0].upper()


def affinity(declared: str) -> TypeCategory:
    """SQLite's own rules, in its order (datatype3.html, 3.1)."""
    upper = declared.upper()
    if "INT" in upper:
        return "number"
    if any(word in upper for word in ("CHAR", "CLOB", "TEXT")):
        return "string"
    if "BLOB" in upper:
        return "binary"
    if upper.strip() == "" or upper.strip() == "ANY":
        return "other"
    return "number"


def build_column_type(declared: str) -> ColumnType:
    category = _NAMED.get(base_name(declared)) or affinity(declared)
    upper = declared.upper()
    size = _SIZE.search(declared)
    length = precision = scale = None
    if size is not None:
        if category == "string" and any(word in upper for word in _LENGTHED):
            length = int(size.group(1))
        elif base_name(declared) in _EXACT:
            precision = int(size.group(1))
            scale = int(size.group(2) or 0)
    return ColumnType(
        sql=declared, category=category, length=length, precision=precision, scale=scale
    )


def read_cell(value: Any, type_: ColumnType) -> str | None:
    """One stored value, in the text of what it is rather than of its column."""
    if value is None:
        return None
    if isinstance(value, Undecodable | bytes):
        return f"0x{bytes(value).hex().upper()}"
    if type_.category == "boolean" and isinstance(value, int) and value in (0, 1):
        return "true" if value else "false"
    if isinstance(value, float):
        # The shortest text that reads back as the same number.
        return repr(value)
    return str(value)


def result_type(declared: str | None) -> ColumnType:
    """What a result column is, where only its declared type is known."""
    return build_column_type(declared or "")
