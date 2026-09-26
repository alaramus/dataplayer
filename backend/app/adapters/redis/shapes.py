"""What each Redis node looks like as rows, said once.

The grid's page, the relation model and the export all read these columns, so
a key of each type, a folder's listing and a declared table have one list of
them here rather than three that could drift (D170, D171).
"""

from collections.abc import Mapping
from typing import Any

from app.adapters.declared_tables import DeclaredTable, DeclaredType
from app.adapters.fetch import FetchColumn
from app.adapters.redis.session import text
from app.adapters.relation import Column, ColumnType, TypeCategory

# A column's name, how its type is spelled, and what its values are.
type Shape = tuple[tuple[str, str, TypeCategory], ...]

KEY_SHAPES: dict[str, Shape] = {
    "string": (("value", "string", "string"),),
    "hash": (("field", "field", "string"), ("value", "string", "string")),
    "list": (("index", "position", "number"), ("value", "string", "string")),
    "set": (("member", "member", "string"),),
    "zset": (("member", "member", "string"), ("score", "score", "number")),
    "stream": (("id", "id", "string"), ("fields", "text", "string")),
}

# A folder or a database, read as the keys directly in it.
LISTING: Shape = (
    ("key", "key", "string"),
    ("type", "type", "string"),
    ("ttl", "seconds", "number"),
    ("size", "count", "number"),
)

# The first column of a declared table: the key's name within its folder.
KEY_COLUMN = "key"

DECLARED_TYPES: dict[DeclaredType, tuple[str, TypeCategory]] = {
    "text": ("text", "string"),
    "number": ("number", "number"),
    "boolean": ("boolean", "boolean"),
    "datetime": ("date and time", "datetime"),
}


def table_shape(table: DeclaredTable) -> Shape:
    return (
        (KEY_COLUMN, "key", "string"),
        *(
            (column.name, *DECLARED_TYPES[column.type])
            for column in table.columns
        ),
    )


def table_columns(table: DeclaredTable) -> list[FetchColumn]:
    """A declared table's page columns: `key` alone admits equality.

    Looking a key up reads one hash; a declared field has no index, and
    finding a value in one would read every hash of the folder (D172).
    """
    columns = fetch_columns(table_shape(table))
    return [
        column.model_copy(update={"filter_operators": ["eq"]})
        if column.name == KEY_COLUMN
        else column
        for column in columns
    ]


def fetch_columns(shape: Shape) -> list[FetchColumn]:
    """The columns of a page, saying they can be neither sorted nor filtered.

    Redis has no index over values, so a source that offered either would be
    offering to read everything and do it here.
    """
    return [
        FetchColumn(
            name=name,
            type=ColumnType(sql=sql, category=category),
            sortable=False,
            filter_operators=[],
        )
        for name, sql, category in shape
    ]


def model_columns(shape: Shape) -> list[Column]:
    return [
        Column(
            position=position,
            name=name,
            type=ColumnType(sql=sql, category=category),
            nullable=True,
        )
        for position, (name, sql, category) in enumerate(shape, start=1)
    ]


def stream_fields(fields: Mapping[Any, Any]) -> str:
    """A stream entry's fields as one cell.

    One column rather than columns of their own: a stream's entries need not
    agree on what they hold, so a grid built from the first one would hide
    what is in the rest.
    """
    return ", ".join(f"{text(key)}={text(value)}" for key, value in fields.items())
