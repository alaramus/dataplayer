"""The canonical text of one value, whatever source it came from.

Shared because the rendering of a boolean, a timestamp or a byte string is not
a property of a driver: PostgreSQL rows, its exported rows and the columnar
files of D51 all cross the boundary as text (D23), and two spellings of the
same value would show up as a difference between sources that does not exist.

A JSON value arrives here already as text. PostgreSQL selects `jsonb` as text
so the driver cannot round a number into a float, and a source holding a native
structure serialises it before calling: the compacting below is about one
canonical spelling, not about parsing.
"""

from datetime import date, datetime, time
from typing import Any

from app.adapters import jsontext
from app.adapters.relation import ColumnType


def encode_cell(value: Any, type_: ColumnType) -> str | None:
    """Render one value with the canonical representation for its type."""
    if value is None:
        return None
    if type_.category == "boolean":
        return "true" if value else "false"
    if type_.category == "datetime" and isinstance(value, datetime | date | time):
        return value.isoformat()
    if type_.category == "binary" and isinstance(value, bytes | bytearray | memoryview):
        return f"0x{bytes(value).hex().upper()}"
    if type_.category == "json":
        if not isinstance(value, str):
            raise TypeError("A JSON value must be serialised before it is rendered")
        return jsontext.compact(value)
    return str(value)
