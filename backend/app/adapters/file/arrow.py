"""Arrow types and Arrow values, as this source renders them.

Two readers arrive here. A Parquet file states its schema in Arrow already
(D51), and the query engine hands its results over the same way (D78), so what
a column is called, what category it belongs to and how one of its values is
spelled is decided once rather than once per reader — the same value seen
through a grid and through a query would otherwise differ in nothing but which
code path read it.

Rendering is D23's: a cell crosses as canonical text.
"""

import json
from collections.abc import Callable
from typing import Any

import pyarrow.types as types

from app.adapters.cells import encode_cell
from app.adapters.relation import ColumnType, TypeCategory


def column_type(arrow_type: Any, sql: str | None = None) -> ColumnType:
    """What a column is, in the reader's own spelling and in categories.

    `sql` is there for the engine: Arrow flattens `JSON`, `UUID` and an
    enumeration into a string, and the engine knows the name it gave the
    column. A reader with nothing more to say passes nothing and gets Arrow's
    own spelling.
    """
    return ColumnType(
        sql=sql or str(arrow_type), category=category(arrow_type, sql)
    )


def category(arrow_type: Any, sql: str | None = None) -> TypeCategory:
    """What the values of this type mean.

    The two named spellings come first because Arrow cannot tell them from a
    string: both travel as text and both have a canonical form of their own.
    """
    if sql == "JSON":
        return "json"
    if sql == "UUID":
        return "uuid"
    if types.is_boolean(arrow_type):
        return "boolean"
    if (
        types.is_integer(arrow_type)
        or types.is_floating(arrow_type)
        or types.is_decimal(arrow_type)
    ):
        return "number"
    if types.is_temporal(arrow_type) and not types.is_interval(arrow_type):
        return "datetime"
    if types.is_string(arrow_type) or types.is_large_string(arrow_type):
        return "string"
    if (
        types.is_binary(arrow_type)
        or types.is_large_binary(arrow_type)
        or types.is_fixed_size_binary(arrow_type)
    ):
        return "binary"
    if is_nested(arrow_type):
        return "json"
    if types.is_dictionary(arrow_type):
        # A dictionary encodes how the column is stored, not what it holds.
        return category(arrow_type.value_type, sql)
    return "other"


def is_nested(arrow_type: Any) -> bool:
    return bool(
        types.is_list(arrow_type)
        or types.is_large_list(arrow_type)
        or types.is_fixed_size_list(arrow_type)
        or types.is_struct(arrow_type)
        or types.is_map(arrow_type)
    )


def encoder(arrow_type: Any, sql: str | None = None) -> Callable[[Any], str | None]:
    """How one column's values become text, decided once for the column."""
    type_ = column_type(arrow_type, sql)
    if type_.category == "json" and is_nested(arrow_type):
        # A nested value arrives as Python containers. It is serialised here
        # and compacted by the shared renderer, so JSON has one spelling
        # wherever it crosses the boundary (D23).
        def encode_nested(value: Any) -> str | None:
            if value is None:
                return None
            return encode_cell(
                json.dumps(value, separators=(",", ":"), default=plain), type_
            )

        return encode_nested

    if types.is_interval(arrow_type):
        # Arrow hands an interval over as a named tuple, whose repr is the
        # name of a Python class. ISO 8601 is the one spelling of a duration
        # that says what it is without a reader knowing the library.
        def encode_interval(value: Any) -> str | None:
            return None if value is None else _iso_duration(value)

        return encode_interval

    def encode(value: Any) -> str | None:
        return encode_cell(value, type_)

    return encode


def plain(value: Any) -> str:
    """A value inside a nested one that JSON has no spelling for."""
    if isinstance(value, bytes | bytearray):
        return f"0x{bytes(value).hex().upper()}"
    return str(value)


def _iso_duration(value: Any) -> str:
    """`MonthDayNano` as ISO 8601, with the parts that are nought left out."""
    months = int(getattr(value, "months", 0))
    days = int(getattr(value, "days", 0))
    nanoseconds = int(getattr(value, "nanoseconds", 0))
    date_part = f"{months}M" if months else ""
    date_part += f"{days}D" if days else ""
    seconds = nanoseconds / 1_000_000_000
    time_part = f"T{seconds:g}S" if nanoseconds else ""
    return f"P{date_part}{time_part}" if date_part or time_part else "P0D"
