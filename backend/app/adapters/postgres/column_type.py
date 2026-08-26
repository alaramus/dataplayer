"""Turn PostgreSQL type metadata into the adapter-neutral column type."""

from collections.abc import Mapping
from typing import Any

from app.adapters.relation import ColumnType, TypeCategory

_BY_CATEGORY: dict[str, TypeCategory] = {
    "A": "array",
    "B": "boolean",
    "C": "composite",
    "D": "datetime",
    "E": "enum",
    "G": "geometric",
    "I": "network",
    "N": "number",
    "R": "range",
    "S": "string",
    "T": "datetime",
    "V": "binary",
}

_BY_NAME: dict[str, TypeCategory] = {
    "json": "json",
    "jsonb": "json",
    "uuid": "uuid",
    "bytea": "binary",
    "xml": "string",
}


def _category(typcategory: str | None, typname: str | None) -> TypeCategory:
    named = _BY_NAME.get(typname or "")
    if named is not None:
        return named
    return _BY_CATEGORY.get(typcategory or "", "other")


def _length(typname: str | None, typmod: int | None) -> int | None:
    if typmod is None or typmod < 0:
        return None
    if typname in {"varchar", "bpchar"}:
        return typmod - 4
    return None


def _precision_and_scale(
    typname: str | None, typmod: int | None
) -> tuple[int | None, int | None]:
    if typname != "numeric" or typmod is None or typmod < 0:
        return None, None
    packed = typmod - 4
    return (packed >> 16) & 0xFFFF, packed & 0xFFFF


def _labels(value: Any) -> list[str] | None:
    if isinstance(value, list):
        return [str(item) for item in value]
    return None


def build_column_type(row: Mapping[str, Any]) -> ColumnType:
    """Build a type while preserving PostgreSQL's DDL-safe spelling."""
    sql = str(row["sql_type"])
    typname = row.get("type_name")
    typmod = row.get("type_mod")
    category = _category(row.get("type_category"), typname)

    element: ColumnType | None = None
    if category == "array" and row.get("element_sql") is not None:
        element = ColumnType(
            sql=str(row["element_sql"]),
            category=_category(row.get("element_category"), row.get("element_name")),
            enum_values=_labels(row.get("element_enum_values")),
        )

    precision, scale = _precision_and_scale(typname, typmod)
    return ColumnType(
        sql=sql,
        category=category,
        element=element,
        dimensions=sql.count("[]"),
        enum_values=_labels(row.get("enum_values")),
        length=_length(typname, typmod),
        precision=precision,
        scale=scale,
    )
