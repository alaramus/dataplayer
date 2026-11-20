"""DuckDB column types in the adapter-neutral vocabulary, and how a value crosses (D390).

A type is read from the text `duckdb_columns()` writes for it: `INTEGER[]`,
`DECIMAL(18,3)`, `STRUCT(a INTEGER, "b c" VARCHAR)`, `ENUM('sad', 'ok')`.
"""

import re

from app.adapters.duckdb.sql import SQL, Composable, Composed
from app.adapters.relation import ColumnType, TypeCategory

_NUMBERS = frozenset(
    {
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "HUGEINT",
        "UTINYINT",
        "USMALLINT",
        "UINTEGER",
        "UBIGINT",
        "UHUGEINT",
        "BIGNUM",
        "FLOAT",
        "DOUBLE",
        "DECIMAL",
    }
)
_NAMED: dict[str, TypeCategory] = {
    "VARCHAR": "string",
    "BOOLEAN": "boolean",
    "BLOB": "binary",
    "UUID": "uuid",
    "JSON": "json",
    "VARIANT": "json",
    "GEOMETRY": "geometric",
    "ENUM": "enum",
    "STRUCT": "composite",
    "MAP": "composite",
    "UNION": "composite",
}
_DECIMAL = re.compile(r"DECIMAL\((\d+),\s*(\d+)\)")
# Written by DuckDB as JSON (`to_json`) rather than in its own text, which
# quotes neither a struct's text nor a map's keys.
_NESTED = frozenset({"array", "composite"})


def base_name(text: str) -> str:
    """The type's name without its arguments: `DECIMAL` of `DECIMAL(10,2)`."""
    return text.split("(", 1)[0].strip().upper()


def category_of(text: str) -> TypeCategory:
    if text.endswith("]"):
        return "array"
    name = base_name(text)
    if name in _NUMBERS:
        return "number"
    if name.startswith(("DATE", "TIME")):
        return "datetime"
    if name == "VARIANT":
        # Any value at all, nested ones included, and written as JSON.
        return "json"
    return _NAMED.get(name, "other")


def enum_labels(text: str) -> list[str]:
    """The labels of `ENUM('a', 'it''s')`, in DuckDB's order."""
    inside = text[text.index("(") + 1 : text.rindex(")")]
    labels: list[str] = []
    index = 0
    while index < len(inside):
        if inside[index] != "'":
            index += 1
            continue
        label: list[str] = []
        index += 1
        while index < len(inside):
            if inside[index] == "'":
                if inside[index + 1 : index + 2] == "'":
                    label.append("'")
                    index += 2
                    continue
                break
            label.append(inside[index])
            index += 1
        labels.append("".join(label))
        index += 1
    return labels


def build_column_type(text: str) -> ColumnType:
    category = category_of(text)
    element: ColumnType | None = None
    precision: int | None = None
    scale: int | None = None
    if category == "array":
        element = build_column_type(text[: text.rindex("[")])
    elif (decimal := _DECIMAL.fullmatch(text.strip())) is not None:
        precision, scale = int(decimal.group(1)), int(decimal.group(2))
    return ColumnType(
        sql=text,
        category=category,
        element=element,
        dimensions=element.dimensions + 1 if element is not None else 0,
        enum_values=enum_labels(text) if category == "enum" else None,
        precision=precision,
        scale=scale,
    )


def is_nested(type_: ColumnType) -> bool:
    return type_.category in _NESTED or base_name(type_.sql) == "VARIANT"


def shown(name: Composable, type_: ColumnType) -> Composed:
    """The text a value crosses as, made by DuckDB itself (D390).

    Every value is text before it leaves the engine: a 128-bit integer and a
    decimal to their last digit, a moment with a time zone in UTC, which the
    driver could not even hand over without a library this server lacks.
    """
    if is_nested(type_):
        return SQL("CAST(to_json({}) AS VARCHAR)").format(name)
    if type_.category == "binary":
        return SQL("'0x' || hex({})").format(name)
    return SQL("CAST({} AS VARCHAR)").format(name)
