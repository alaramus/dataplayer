"""Which rows of a MySQL relation can be named, changed, and how (D234).

A row is named by the key its pages are ordered by (D231): the primary key, or
a unique key over columns that cannot be null. A table with neither is named
by the whole row (D242): every value as its page showed it, found again by the
columns that compare exactly, and changed one row at a time — rows that are
the same in every value are the same row to anybody looking at them.

MySQL keeps no version of a row that a client can read, as PostgreSQL's `xmin`
is. The version in a handle is a digest of the row's values as they were shown,
and a change is made only after the same row, read again under `FOR UPDATE`,
digests the same: somebody else's change in between, to any column, refuses
this one rather than being written over.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from app.adapters.fetch import FetchColumn
from app.adapters.mysql.sql import SQL, Composable, Identifier
from app.adapters.relation import ColumnType
from app.adapters.row_handles import RowHandle as RowHandle
from app.adapters.row_handles import decode_handle as decode_shared
from app.adapters.row_handles import encode_handle as encode_handle
from app.adapters.row_handles import version_of as version_of


@dataclass(frozen=True)
class RowShape:
    """What a page of one relation is, and what may be done to its rows."""

    columns: list[FetchColumn]
    key: list[str]
    update_reason: str | None
    insert_reason: str | None
    # Named by every value rather than by a key (D242).
    whole_row: bool = False

    @property
    def naming(self) -> list[str]:
        """The columns a handle carries the values of, in order."""
        return [column.name for column in self.columns] if self.whole_row else self.key

    @property
    def update_supported(self) -> bool:
        return self.update_reason is None

    @property
    def insert_supported(self) -> bool:
        return self.insert_reason is None


# A row named by its values carries them all in its handle, to every page and
# back; past this many bytes of them it is not named, and cannot be edited.
WHOLE_ROW_BYTES = 64 * 1024


def decode_handle(value: str, shape: RowShape) -> RowHandle:
    return decode_shared(value, len(shape.naming), nulls=shape.whole_row)


def handle_of(shape: RowShape, cells: list[str | None], occurrence: int = 0) -> str | None:
    """The handle of a row read with every column of the shape, in order."""
    if shape.update_reason is not None:
        return None
    if shape.whole_row:
        if len(json.dumps(cells, ensure_ascii=False).encode()) > WHOLE_ROW_BYTES:
            return None
        return encode_handle(list(cells), version_of(cells), occurrence)
    positions = {column.name: index for index, column in enumerate(shape.columns)}
    keys = [cells[positions[name]] for name in shape.key]
    if any(value is None for value in keys):
        return None
    return encode_handle(list(keys), version_of(cells))


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


def key_match(shape: RowShape, keys: list[str | None], params: list[object]) -> Composable:
    """The condition that finds one row by its handle's values, appended to params.

    `a = %s AND b = %s` for a key. For a row named whole, every column that
    compares exactly: text as its bytes, since a collation that ignores case
    would find `A` for `a`; a floating-point number, JSON and a shape are left
    out, since none of them is equal to the text it was shown as, and the
    digest of the row tells the rows they leave alike apart (D242).
    """
    types = {column.name: column.type for column in shape.columns}
    parts: list[Composable] = []
    for name, value in zip(shape.naming, keys, strict=True):
        type_ = types[name]
        if shape.whole_row and not _comparable(type_):
            continue
        placeholder, param = written(value, type_)
        if shape.whole_row and type_.category in ("string", "enum"):
            parts.append(
                SQL("CAST(CONVERT({} USING utf8mb4) AS BINARY) <=> CAST(CONVERT({} USING utf8mb4) AS BINARY)").format(
                    Identifier(name), placeholder
                )
            )
        else:
            parts.append(SQL("{} <=> {}" if shape.whole_row else "{} = {}").format(Identifier(name), placeholder))
        params.append(param)
    return SQL(" AND ").join(parts) if parts else SQL("TRUE")


def _comparable(type_: ColumnType) -> bool:
    if type_.category in ("json", "geometric", "other"):
        return False
    base = type_.sql.split("(", 1)[0].split(" ", 1)[0].lower()
    return base not in ("float", "double", "real")
