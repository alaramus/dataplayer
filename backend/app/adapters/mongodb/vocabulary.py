"""The types a field may be converted to and the kinds of index, MongoDB's own (D288)."""

from dataclasses import dataclass

from app.adapters.relation import ColumnTypeOption, IndexMethodOption
from app.core.translation import N_


@dataclass(frozen=True)
class Conversion:
    """A `$convert` target, by the tag a field of it is read as."""

    code: str
    title: str
    # What `$convert` calls it.
    convert_to: str
    # What a column of it says it is (D284).
    tag: str


CONVERSIONS: dict[str, Conversion] = {
    conversion.code: conversion
    for conversion in (
        Conversion("string", N_("Text"), "string", "string"),
        Conversion("int", N_("Integer (32-bit)"), "int", "int"),
        Conversion("long", N_("Integer (64-bit)"), "long", "long"),
        Conversion("double", N_("Floating point"), "double", "double"),
        Conversion("decimal", N_("Decimal"), "decimal", "decimal"),
        Conversion("bool", N_("Yes or no"), "bool", "bool"),
        Conversion("date", N_("Date and time"), "date", "date"),
        Conversion("objectId", N_("ObjectId"), "objectId", "objectId"),
    )
}

MONGODB_COLUMN_TYPE_OPTIONS = [
    ColumnTypeOption(code=conversion.code, title=conversion.title, sql=conversion.tag)
    for conversion in CONVERSIONS.values()
]


@dataclass(frozen=True)
class IndexKey:
    code: str
    title: str
    # What stands beside each field in the key document.
    key: int | str
    unique: bool
    compound: bool


INDEX_KEYS: dict[str, IndexKey] = {
    key.code: key
    for key in (
        IndexKey("ascending", N_("Ascending"), 1, unique=True, compound=True),
        IndexKey("descending", N_("Descending"), -1, unique=True, compound=True),
        IndexKey("hashed", N_("Hashed"), "hashed", unique=False, compound=False),
        IndexKey("text", N_("Text search"), "text", unique=False, compound=True),
        IndexKey("2dsphere", N_("Geospatial (sphere)"), "2dsphere", unique=False, compound=True),
    )
}

MONGODB_INDEX_METHODS = [
    IndexMethodOption(
        code=key.code,
        title=key.title,
        sql=str(key.key),
        unique_supported=key.unique,
        multi_column_supported=key.compound,
    )
    for key in INDEX_KEYS.values()
]
