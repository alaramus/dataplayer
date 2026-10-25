"""ClickHouse types in the adapter-neutral vocabulary, and their values as text.

A type is read from the text the server writes for it — `Nullable(String)`,
`DateTime64(3, 'UTC')`, `Array(Tuple(a Int8, b String))` — and a value from
the JSON the server writes for it (D268).
"""

import json
import re
from typing import Any

from app.adapters.relation import ColumnType, TypeCategory


class Number(str):
    """A number exactly as the server wrote it, never through a float."""


def decode_line(line: str | bytes) -> Any:
    """One line of a JSON answer, every number kept as the server's text."""
    return json.loads(line, parse_int=Number, parse_float=Number, parse_constant=Number)


def _compact(value: Any) -> str:
    if isinstance(value, Number):
        return str(value)
    if value is None or isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_compact(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(f"{_compact(key)}:{_compact(item)}" for key, item in value.items()) + "}"
    raise TypeError(f"Not a JSON value: {type(value).__name__}")


def read_cell(value: Any) -> str | None:
    """One value as it crosses to the grid (D268).

    A scalar is the server's own text — a number to its last digit, a moment in
    UTC with its `Z` — and an array, a map or a tuple is compact JSON with its
    numbers as they were written.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return str(value)
    return _compact(value)


def split_arguments(text: str) -> list[str]:
    """The top-level arguments of `Name(a, b(c, d), 'e,f')`, as written."""
    start = text.find("(")
    if start < 0 or not text.endswith(")"):
        return []
    inner = text[start + 1 : -1]
    parts: list[str] = []
    depth = 0
    quoted: str | None = None
    current: list[str] = []
    index = 0
    while index < len(inner):
        character = inner[index]
        if quoted is not None:
            current.append(character)
            if character == "\\" and index + 1 < len(inner):
                current.append(inner[index + 1])
                index += 2
                continue
            if character == quoted:
                quoted = None
        elif character in "'`\"":
            quoted = character
            current.append(character)
        elif character == "(":
            depth += 1
            current.append(character)
        elif character == ")":
            depth -= 1
            current.append(character)
        elif character == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(character)
        index += 1
    if current or parts:
        parts.append("".join(current).strip())
    return parts


def type_name(text: str) -> str:
    """`Decimal` of `Decimal(38, 10)`, `String` of `String`."""
    return text.split("(", 1)[0].strip()


def unwrapped(text: str) -> str:
    """The type a value has, without `Nullable` and `LowCardinality` around it."""
    while type_name(text) in ("Nullable", "LowCardinality"):
        arguments = split_arguments(text)
        if len(arguments) != 1:
            break
        text = arguments[0]
    return text


def is_nullable(text: str) -> bool:
    current = text
    while True:
        name = type_name(current)
        if name == "Nullable":
            return True
        if name != "LowCardinality":
            return False
        arguments = split_arguments(current)
        if len(arguments) != 1:
            return False
        current = arguments[0]


_NUMBERS = re.compile(r"(U?Int(8|16|32|64|128|256)|Float(32|64)|BFloat16|Decimal(32|64|128|256)?)")
_DATETIMES = frozenset({"Date", "Date32", "DateTime", "DateTime64", "Time", "Time64"})
_GEOMETRY = frozenset(
    {"Point", "Ring", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "Geometry"}
)
_CATEGORIES: dict[str, TypeCategory] = {
    "String": "string",
    "FixedString": "string",
    "Bool": "boolean",
    "UUID": "uuid",
    "IPv4": "network",
    "IPv6": "network",
    "Enum8": "enum",
    "Enum16": "enum",
    "Enum": "enum",
    "Array": "array",
    "Tuple": "composite",
    "Map": "composite",
    "Nested": "composite",
    "JSON": "json",
    "Object": "json",
}


def category_of(text: str) -> TypeCategory:
    name = type_name(unwrapped(text))
    if _NUMBERS.fullmatch(name):
        return "number"
    if name in _DATETIMES:
        return "datetime"
    if name in _GEOMETRY:
        return "geometric"
    return _CATEGORIES.get(name, "other")


def _unquote(literal: str) -> str:
    """A string literal of a type's text, `'it\\'s'`, as the label it names."""
    body = literal.strip()
    if len(body) < 2 or body[0] != "'" or body[-1] != "'":
        return body
    text = body[1:-1]
    out: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == "\\" and index + 1 < len(text):
            out.append(text[index + 1])
            index += 2
            continue
        if character == "'" and index + 1 < len(text) and text[index + 1] == "'":
            out.append("'")
            index += 2
            continue
        out.append(character)
        index += 1
    return "".join(out)


def enum_labels(text: str) -> list[str]:
    """The labels of `Enum8('a' = 1, 'it\\'s' = 2)`, in the server's order."""
    labels: list[str] = []
    for argument in split_arguments(unwrapped(text)):
        # The value after the last `=` outside the quotes is its number.
        literal = argument.rsplit("=", 1)[0] if argument.rstrip()[-1:].isdigit() else argument
        labels.append(_unquote(literal))
    return labels


def build_column_type(text: str) -> ColumnType:
    """A type from the text the server writes for it."""
    inner = unwrapped(text)
    category = category_of(inner)
    name = type_name(inner)
    arguments = split_arguments(inner)
    element: ColumnType | None = None
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    if category == "array" and len(arguments) == 1:
        element = build_column_type(arguments[0])
    elif name == "FixedString" and len(arguments) == 1 and arguments[0].isdigit():
        length = int(arguments[0])
    elif name == "Decimal" and len(arguments) == 2:
        precision, scale = int(arguments[0]), int(arguments[1])
    elif name.startswith("Decimal") and len(arguments) == 1:
        precision = {"Decimal32": 9, "Decimal64": 18, "Decimal128": 38, "Decimal256": 76}[name]
        scale = int(arguments[0])
    return ColumnType(
        sql=text,
        category=category,
        element=element,
        dimensions=1 if element is not None else 0,
        enum_values=enum_labels(inner) if category == "enum" else None,
        length=length,
        precision=precision,
        scale=scale,
    )
