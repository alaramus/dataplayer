"""Which rows of a ClickHouse table can be named and changed, and how (D272).

No key of ClickHouse is unique (D269), so a row is named by its whole row: the
handle carries every value its page showed and a digest of them. It is found
again by the columns that compare exactly — everything but a float, which may
be NaN, and the types a value cannot be written back into — and the digest
says whether the rows found are still the one shown. Rows the same in every
value are the same row to anybody reading them, and are changed together.

A value goes back as it was shown, through the server's own parsing:
`accurateCast` of the text to the column's type, refusing what the type
cannot hold rather than wrapping it, and a moment through the best-effort
parser in UTC, as every moment is shown (D268). An array, a tuple and a shape
are shown as JSON and written back as the server's text of them.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from app.adapters.clickhouse.sql import (
    SQL,
    Composable,
    Identifier,
    Params,
    text_literal,
)
from app.adapters.clickhouse.types import (
    Number,
    category_of,
    decode_line,
    split_arguments,
    type_name,
    unwrapped,
)
from app.adapters.fetch import FetchColumn
from app.adapters.relation import ColumnType
from app.adapters.row_handles import encode_handle, version_of
from app.core.translation import say

# Engines whose rows a lightweight DELETE or an UPDATE reaches.


def editable_engine(engine: str) -> bool:
    return engine.endswith("MergeTree")


# Engines that keep the rows inserted into them. `Null` takes rows and keeps
# none, and an engine reading from outside has nowhere to put them.
_INSERTABLE_ENGINES = frozenset({"Log", "TinyLog", "StripeLog", "Memory", "Buffer", "Distributed"})


def insertable_engine(engine: str) -> bool:
    return editable_engine(engine) or engine in _INSERTABLE_ENGINES


# Types a value shown as text cannot be written back into: a map has no cast
# from text, and the rest are no single value at all.
_UNWRITABLE = frozenset(
    {
        "Map",
        "JSON",
        "Object",
        "Dynamic",
        "Variant",
        "AggregateFunction",
        "SimpleAggregateFunction",
        "Nothing",
        "Geometry",
    }
)
_FLOATS = frozenset({"Float32", "Float64", "BFloat16"})
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# What a shape is made of, so its JSON can be written back as the server's text.
_SHAPES = {
    "Point": "Tuple(Float64, Float64)",
    "Ring": "Array(Point)",
    "LineString": "Array(Point)",
    "MultiLineString": "Array(LineString)",
    "Polygon": "Array(Ring)",
    "MultiPolygon": "Array(Polygon)",
}


def _words(type_sql: str) -> set[str]:
    # A quoted part — an enum's label, a time zone — names no type.
    return set(_WORD.findall(re.sub(r"'(?:[^'\\]|\\.)*'", "", type_sql)))


def writable_type(type_: ColumnType) -> bool:
    return not (_words(type_.sql) & _UNWRITABLE)


def comparable_type(type_: ColumnType) -> bool:
    words = _words(type_.sql)
    shapes = words & set(_SHAPES)
    return writable_type(type_) and not (words & _FLOATS) and not shapes


# A row named by its values carries them all in its handle, to every page and
# back; past this many bytes of them it is not named, and cannot be edited.
WHOLE_ROW_BYTES = 64 * 1024


@dataclass(frozen=True)
class RowShape:
    """What a page of one table is, and what may be done to its rows."""

    columns: list[FetchColumn]
    # The columns a row is found again by (D272).
    matched: list[str]
    update_reason: str | None
    insert_reason: str | None

    @property
    def update_supported(self) -> bool:
        return self.update_reason is None

    @property
    def insert_supported(self) -> bool:
        return self.insert_reason is None


def handle_of(shape: RowShape, cells: list[str | None], occurrence: int = 0) -> str | None:
    if shape.update_reason is not None:
        return None
    if len(json.dumps(cells, ensure_ascii=False).encode()) > WHOLE_ROW_BYTES:
        return None
    return encode_handle(list(cells), version_of(cells), occurrence)


def handles_of(shape: RowShape, rows: list[list[str | None]]) -> list[str | None]:
    """The handles of a page's rows, rows the same in every value told apart."""
    seen: dict[str, int] = {}
    handles: list[str | None] = []
    for cells in rows:
        version = version_of(cells)
        occurrence = seen.get(version, 0)
        seen[version] = occurrence + 1
        handles.append(handle_of(shape, cells, occurrence))
    return handles


def _element(argument: str) -> str:
    """A tuple's element type, without the name a named tuple gives it."""
    head, _, rest = argument.partition(" ")
    if rest and "(" not in head and "'" not in head:
        return rest.strip()
    return argument


def clickhouse_text(value: Any, type_sql: str) -> str:
    """A value decoded from the JSON it was shown as, in the server's text format."""
    inner = unwrapped(type_sql)
    name = type_name(inner)
    if name in _SHAPES:
        inner = _SHAPES[name]
        name = type_name(inner)
    if value is None:
        return "NULL"
    arguments = split_arguments(inner)
    if name == "Array":
        if not isinstance(value, list) or len(arguments) != 1:
            raise ValueError
        return "[" + ",".join(clickhouse_text(item, arguments[0]) for item in value) + "]"
    if name == "Tuple":
        elements = [_element(argument) for argument in arguments]
        items = list(value.values()) if isinstance(value, dict) else value
        if not isinstance(items, list) or len(items) != len(elements):
            raise ValueError
        return "(" + ",".join(
            clickhouse_text(item, element) for item, element in zip(items, elements, strict=True)
        ) + ")"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Number):
        return str(value)
    if isinstance(value, str):
        return value if category_of(inner) == "number" else text_literal(value)
    raise ValueError


def value_expression(value: str | None, type_: ColumnType, params: Params) -> Composable:
    """A value as it was shown, as the expression that writes it into its column.

    The column's type travels as a parameter of its own, so nothing the
    catalog says is composed into the statement either.
    """
    if value is None:
        return SQL("NULL")
    inner = unwrapped(type_.sql)
    target = params.add(inner, "String")
    if type_.category == "datetime" and type_name(inner) in ("DateTime", "DateTime64"):
        return SQL("CAST(parseDateTime64BestEffort({}, 9, 'UTC'), {})").format(
            params.add(value, "String"), target
        )
    if type_.category in ("array", "composite", "geometric"):
        try:
            text = clickhouse_text(decode_line(value), inner)
        except ValueError:
            raise ValueError(say("That value cannot be read as {sql}", sql=type_.sql)) from None
        return SQL("accurateCast({}, {})").format(params.add(text, "String"), target)
    return SQL("accurateCast({}, {})").format(params.add(value, "String"), target)


def row_match(shape: RowShape, cells: list[str | None], params: Params) -> Composable:
    """The condition that finds the rows alike to these values (D272)."""
    types = {column.name: column.type for column in shape.columns}
    positions = {column.name: index for index, column in enumerate(shape.columns)}
    parts: list[Composable] = []
    for name in shape.matched:
        value = cells[positions[name]]
        if value is None:
            parts.append(SQL("{} IS NULL").format(Identifier(name)))
        else:
            parts.append(
                SQL("{} = {}").format(Identifier(name), value_expression(value, types[name], params))
            )
    return SQL(" AND ").join(parts) if parts else SQL("1")
