"""Which rows of a DuckDB table can be named, changed, and how (D395).

A row is named by its primary key and nothing else: DuckDB moves a row when it
is updated (D391), and a table may hold two identical rows. The key's values
travel in the handle as the page showed them, and DuckDB casts that text back
to the key's type when it is bound against the key column.

The version is a digest of the row as it was shown, checked in the
transaction that makes the change.
"""

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.adapters.duckdb.sql import SQL, Composable, Identifier
from app.adapters.duckdb.types import is_nested, shown
from app.adapters.fetch import FetchColumn
from app.adapters.relation import ColumnType
from app.core.translation import say


@dataclass(frozen=True)
class RowShape:
    """What a page of one relation is, and what may be done to its rows."""

    columns: list[FetchColumn]
    # The primary key's columns; a table without one names no row.
    key: list[str]
    update_reason: str | None
    insert_reason: str | None

    @property
    def update_supported(self) -> bool:
        return self.update_reason is None

    @property
    def insert_supported(self) -> bool:
        return self.insert_reason is None

    def column(self, name: str) -> FetchColumn:
        return next(column for column in self.columns if column.name == name)

    def handle_of(self, cells: list[str | None]) -> str | None:
        """A row's handle from its cells as shown, or nothing when it names no row."""
        if not self.update_supported:
            return None
        names = [column.name for column in self.columns]
        keys = [cells[names.index(name)] for name in self.key]
        if any(value is None for value in keys):
            return None
        return encode_handle(keys, cells)


def writable(type_: ColumnType) -> bool:
    """Whether a value shown as text goes back as text into this column (D395)."""
    return not is_nested(type_) and type_.category != "geometric"


def selected(shape: RowShape) -> Composable:
    """Every column of the page, as the text DuckDB writes for it (D390)."""
    return SQL(", ").join(shown(Identifier(column.name), column.type) for column in shape.columns)


def version_of(cells: list[str | None]) -> str:
    """A digest of a row's values as they are shown."""
    encoded = json.dumps(cells, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:32]


@dataclass(frozen=True)
class RowHandle:
    keys: list[str]
    version: str


def encode_handle(keys: list[str | None], cells: list[str | None]) -> str:
    named = {"keys": keys, "version": version_of(cells)}
    raw = json.dumps(named, separators=(",", ":"), ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_handle(value: str, shape: RowShape) -> RowHandle:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded: Any = json.loads(base64.urlsafe_b64decode(padded).decode())
        keys = decoded["keys"]
        version = decoded["version"]
        if not isinstance(version, str) or not isinstance(keys, list):
            raise ValueError
        if not all(isinstance(key, str) for key in keys):
            raise ValueError
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError(say("The row handle is not valid")) from None
    if not shape.key or len(keys) != len(shape.key):
        raise ValueError(say("The row handle is not valid for this relation"))
    return RowHandle(keys=keys, version=version)


def key_match(shape: RowShape, keys: list[str], params: list[object]) -> Composable:
    """The condition that finds one row by its handle's values.

    The text is bound against the column itself, which DuckDB casts to the
    key's type; a binary key is compared as the text it is shown as.
    """
    params.extend(keys)
    conditions: list[Composable] = []
    for name in shape.key:
        column = shape.column(name)
        compared: Composable = (
            shown(Identifier(name), column.type)
            if column.type.category == "binary"
            else Identifier(name)
        )
        conditions.append(SQL("{} = ?").format(compared))
    return SQL(" AND ").join(conditions)


def written(value: str | None, type_: ColumnType) -> object:
    """A value as it is shown, as it is bound for its column (D395).

    Hexadecimal goes back as bytes into a binary column; anything else as the
    text it is, which DuckDB converts by its own rules.
    """
    if value is None:
        return None
    if type_.category == "binary":
        if value.startswith("0x"):
            try:
                return bytes.fromhex(value[2:])
            except ValueError:
                pass
        return value.encode()
    return value
