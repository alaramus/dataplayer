"""Which rows of a MySQL relation can be named, changed, and how (D234).

A row is named by the key its pages are ordered by (D231): the primary key, or
a unique key over columns that cannot be null. A table with neither has no row
to name, and so takes new rows and no edits.

MySQL keeps no version of a row that a client can read, as PostgreSQL's `xmin`
is. The version in a handle is a digest of the row's values as they were shown,
and a change is made only after the same row, read again under `FOR UPDATE`,
digests the same: somebody else's change in between, to any column, refuses
this one rather than being written over.
"""

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.adapters.fetch import FetchColumn
from app.adapters.mysql.sql import SQL, Composable, Identifier
from app.adapters.relation import ColumnType
from app.core.translation import say


@dataclass(frozen=True)
class RowShape:
    """What a page of one relation is, and what may be done to its rows."""

    columns: list[FetchColumn]
    key: list[str]
    update_reason: str | None
    insert_reason: str | None

    @property
    def update_supported(self) -> bool:
        return self.update_reason is None

    @property
    def insert_supported(self) -> bool:
        return self.insert_reason is None


def version_of(cells: list[str | None]) -> str:
    """A digest of a row's values as they are shown."""
    encoded = json.dumps(cells, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:32]


@dataclass(frozen=True)
class RowHandle:
    keys: list[str]
    version: str


def encode_handle(keys: list[str], version: str) -> str:
    raw = json.dumps({"keys": keys, "version": version}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_handle(value: str, key: list[str]) -> RowHandle:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded: Any = json.loads(base64.urlsafe_b64decode(padded).decode())
        keys = decoded["keys"]
        version = decoded["version"]
        if (
            not isinstance(keys, list)
            or not all(isinstance(item, str) for item in keys)
            or not isinstance(version, str)
        ):
            raise ValueError
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError(say("The row handle is not valid")) from None
    if len(keys) != len(key):
        raise ValueError(say("The row handle is not valid for this relation"))
    return RowHandle(keys=keys, version=version)


def handle_of(shape: RowShape, cells: list[str | None]) -> str | None:
    """The handle of a row read with every column of the shape, in order."""
    if shape.update_reason is not None:
        return None
    positions = {column.name: index for index, column in enumerate(shape.columns)}
    keys = [cells[positions[name]] for name in shape.key]
    if any(value is None for value in keys):
        return None
    return encode_handle([value for value in keys if value is not None], version_of(cells))


def written(value: str | None, type_: ColumnType) -> tuple[Composable, object]:
    """A value as it is shown, turned into what is sent for this column.

    Each is the inverse of how `read_cell` showed it: hexadecimal back to
    bytes, WKT through ST_GeomFromText, a TIMESTAMP's offset to UTC. Anything
    else is sent as the text it is, and the server, in strict mode, says
    whether its column can hold it.
    """
    # The placeholder depends on the column alone, so every row of a block
    # is the same statement; ST_GeomFromText(NULL) is NULL.
    if type_.category == "geometric":
        return SQL("ST_GeomFromText(%s)"), value
    if type_.category == "binary" and value is None:
        return SQL("UNHEX(%s)"), None
    if value is None:
        return SQL("%s"), None
    base = type_.sql.split("(", 1)[0].split(" ", 1)[0].lower()
    if type_.category == "binary":
        # As hexadecimal through UNHEX, never as bytes: aiomysql escapes bytes
        # with a PyMySQL function that PyMySQL 1.2 replaced by a string, so a
        # bytes parameter fails with "'str' object is not callable".
        if value.startswith("0x"):
            try:
                return SQL("UNHEX(%s)"), bytes.fromhex(value[2:]).hex()
            except ValueError:
                pass
        return SQL("UNHEX(%s)"), value.encode().hex()
    if base == "bit" and value.isdigit():
        return SQL("%s"), int(value)
    if base == "timestamp":
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return SQL("%s"), value
        if moment.tzinfo is not None:
            moment = moment.astimezone(UTC).replace(tzinfo=None)
        return SQL("%s"), moment
    return SQL("%s"), value


def key_match(shape: RowShape, keys: list[str], params: list[object]) -> Composable:
    """`a = %s AND b = %s` for one row's key, its values appended to params."""
    types = {column.name: column.type for column in shape.columns}
    parts: list[Composable] = []
    for name, value in zip(shape.key, keys, strict=True):
        placeholder, param = written(value, types[name])
        parts.append(SQL("{} = {}").format(Identifier(name), placeholder))
        params.append(param)
    return SQL(" AND ").join(parts)
