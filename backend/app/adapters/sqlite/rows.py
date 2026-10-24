"""Which rows of a SQLite table can be named, changed, and how (D254).

A row is named by its primary key, or else by its rowid: every table but a
`WITHOUT ROWID` one has it, and that kind always has a primary key. The key's
values travel in the handle as they are stored — an integer, a real, text or a
blob, each tagged — rather than as the text a page shows, so a row is found
again whatever its column's affinity would make of the text.

SQLite keeps no version of a row a client can read. The version in a handle is
a digest of the row's values as they were shown, checked inside a write
transaction before anything is changed: nobody else can write between the
check and the change.
"""

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from app.adapters.fetch import FetchColumn
from app.adapters.relation import ColumnType
from app.adapters.sqlite.sql import SQL, Composable, Identifier
from app.core.translation import say

# What a key value is called in a handle: its storage class, then the value.
Stored = int | float | str | bytes | None


@dataclass(frozen=True)
class RowShape:
    """What a page of one relation is, and what may be done to its rows."""

    columns: list[FetchColumn]
    # The primary key's columns, or nothing when the rowid names a row.
    key: list[str]
    # The name the rowid answers to here when it names rows (D251).
    rowid: str | None
    update_reason: str | None
    insert_reason: str | None

    @property
    def update_supported(self) -> bool:
        return self.update_reason is None

    @property
    def insert_supported(self) -> bool:
        return self.insert_reason is None

    def naming(self) -> list[Composable]:
        """What a row is found by, as it is selected and matched."""
        if self.key:
            return [Identifier(name) for name in self.key]
        # A fixed word of this package: quoted, it would be a column of that
        # name if the table had one. A view has no rowid, and names no row.
        return [] if self.rowid is None else [SQL(self.rowid)]


def version_of(cells: list[str | None]) -> str:
    """A digest of a row's values as they are shown."""
    encoded = json.dumps(cells, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:32]


def _tagged(value: Stored) -> list[Any]:
    if value is None:
        return ["n"]
    if isinstance(value, bool):
        return ["i", int(value)]
    if isinstance(value, int):
        # As text: a JSON number past 2^53 is not read back exactly by everyone.
        return ["i", str(value)]
    if isinstance(value, float):
        return ["r", repr(value)]
    if isinstance(value, bytes):
        return ["b", bytes(value).hex()]
    return ["t", value]


def _untagged(item: Any) -> Stored:
    if not isinstance(item, list) or not item or not isinstance(item[0], str):
        raise ValueError
    kind = item[0]
    if kind == "n" and len(item) == 1:
        return None
    if len(item) != 2 or not isinstance(item[1], str):
        raise ValueError
    if kind == "i":
        return int(item[1])
    if kind == "r":
        return float(item[1])
    if kind == "b":
        return bytes.fromhex(item[1])
    if kind == "t":
        return item[1]
    raise ValueError


@dataclass(frozen=True)
class RowHandle:
    keys: list[Stored]
    version: str


def encode_handle(keys: list[Stored], cells: list[str | None]) -> str:
    named = {"keys": [_tagged(value) for value in keys], "version": version_of(cells)}
    raw = json.dumps(named, separators=(",", ":"), ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_handle(value: str, shape: RowShape) -> RowHandle:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded: Any = json.loads(base64.urlsafe_b64decode(padded).decode())
        keys = [_untagged(item) for item in decoded["keys"]]
        version = decoded["version"]
        if not isinstance(version, str):
            raise ValueError
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError(say("The row handle is not valid")) from None
    if len(keys) != len(shape.naming()):
        raise ValueError(say("The row handle is not valid for this relation"))
    return RowHandle(keys=keys, version=version)


def key_match(shape: RowShape, keys: list[Stored], params: list[object]) -> Composable:
    """The condition that finds one row by its handle's values.

    `IS` rather than `=`: a primary key of a rowid table may hold NULL.
    """
    params.extend(keys)
    return SQL(" AND ").join(SQL("{} IS ?").format(name) for name in shape.naming())


_INTEGER = re.compile(r"[+-]?\d+")


def written(value: str | None, type_: ColumnType) -> object:
    """A value as it is shown, turned into what is bound for its column (D254).

    The inverse of how a page shows it where the column says which: binary as
    hexadecimal, a boolean as `true` or `false`. A column with no type keeps a
    number a number when the text is how that number is shown. Anything else
    is bound as text, which a column's affinity converts as SQLite always does.
    """
    if value is None:
        return None
    category = type_.category
    if category == "binary":
        if value.startswith("0x"):
            try:
                return bytes.fromhex(value[2:])
            except ValueError:
                pass
        return value.encode()
    if category == "boolean":
        spelt = value.strip().lower()
        if spelt == "true":
            return 1
        if spelt == "false":
            return 0
        return value
    if category == "other":
        if _INTEGER.fullmatch(value) and str(int(value)) == value and -(2**63) <= int(value) < 2**63:
            return int(value)
        try:
            number = float(value)
        except ValueError:
            return value
        return number if repr(number) == value else value
    return value
