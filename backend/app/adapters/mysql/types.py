"""MySQL column types in the adapter-neutral vocabulary, and their values as text.

Read from `information_schema.COLUMNS`: `DATA_TYPE` decides the category and
`COLUMN_TYPE`, which keeps `unsigned`, lengths and an enum's labels, is the DDL
spelling shown.
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from app.adapters.cells import encode_cell
from app.adapters.relation import ColumnType, TypeCategory

_BY_DATA_TYPE: dict[str, TypeCategory] = {
    **dict.fromkeys(
        (
            "tinyint",
            "smallint",
            "mediumint",
            "int",
            "integer",
            "bigint",
            "decimal",
            "numeric",
            "float",
            "double",
            "real",
            "bit",
            "year",
        ),
        "number",
    ),
    **dict.fromkeys(
        ("char", "varchar", "tinytext", "text", "mediumtext", "longtext", "set"),
        "string",
    ),
    **dict.fromkeys(
        ("binary", "varbinary", "tinyblob", "blob", "mediumblob", "longblob"),
        "binary",
    ),
    **dict.fromkeys(("date", "datetime", "timestamp", "time"), "datetime"),
    **dict.fromkeys(
        (
            "geometry",
            "point",
            "linestring",
            "polygon",
            "multipoint",
            "multilinestring",
            "multipolygon",
            "geometrycollection",
            "geomcollection",
        ),
        "geometric",
    ),
    "json": "json",
    "enum": "enum",
    # MariaDB's own types.
    "uuid": "uuid",
    "inet4": "network",
    "inet6": "network",
}

_LENGTHED = frozenset({"char", "varchar", "binary", "varbinary"})


def enum_labels(column_type: str) -> list[str]:
    """The labels of `enum('a','b''c')`, as the server quotes them."""
    start = column_type.find("(")
    labels: list[str] = []
    if start < 0:
        return labels
    text = column_type[start + 1 : column_type.rfind(")")]
    index = 0
    while index < len(text):
        if text[index] != "'":
            index += 1
            continue
        index += 1
        label: list[str] = []
        while index < len(text):
            if text[index] == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    label.append("'")
                    index += 2
                    continue
                break
            label.append(text[index])
            index += 1
        labels.append("".join(label))
        index += 1
    return labels


def build_column_type(row: Mapping[str, Any], *, is_json: bool = False) -> ColumnType:
    """A type from one row of COLUMNS.

    `is_json` is MariaDB's: its JSON is LONGTEXT with a `json_valid` check on
    the column, so the catalog says it rather than the type.
    """
    data_type = str(row["data_type"]).lower()
    sql = str(row["column_type"])
    category: TypeCategory = "json" if is_json else _BY_DATA_TYPE.get(data_type, "other")
    length = row.get("character_length") if data_type in _LENGTHED else None
    precision = row.get("numeric_precision") if data_type in ("decimal", "numeric") else None
    scale = row.get("numeric_scale") if data_type in ("decimal", "numeric") else None
    return ColumnType(
        sql="json" if is_json else sql,
        category=category,
        enum_values=enum_labels(sql) if category == "enum" else None,
        length=None if length is None else int(length),
        precision=None if precision is None else int(precision),
        scale=None if scale is None else int(scale),
    )


def _time_text(value: timedelta) -> str:
    """A TIME as MySQL writes it: it may be negative and past 24 hours."""
    total = abs(value)
    microseconds = total.microseconds
    seconds = int(total.total_seconds())
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    sign = "-" if value < timedelta(0) else ""
    text = f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{text}.{microseconds:06d}" if microseconds else text


def read_cell(value: Any, type_: ColumnType) -> str | None:
    """One value the driver handed over, in the canonical text of its type (D230).

    What the driver could not parse it hands over as the server wrote it — a
    zero date is `0000-00-00` — and that text is kept rather than refused.
    """
    if value is None:
        return None
    data_type = type_.sql.split("(", 1)[0].split(" ", 1)[0].lower()
    if data_type == "bit" and isinstance(value, bytes | bytearray):
        return str(int.from_bytes(value, "big"))
    if data_type == "timestamp" and isinstance(value, datetime):
        # The session reads TIMESTAMP in UTC, so the offset is known.
        return value.replace(tzinfo=UTC).isoformat()
    if isinstance(value, timedelta):
        return _time_text(value)
    if isinstance(value, bytes | bytearray):
        # Bytes the server did not call binary are still not text: decoding
        # them with replacements would show a value that is not there.
        return f"0x{bytes(value).hex().upper()}"
    return encode_cell(value, type_)


# What a result column of each wire type is, as far as a result says.
_WIRE_TYPES: dict[int, tuple[str, TypeCategory]] = {
    0: ("decimal", "number"),
    1: ("tinyint", "number"),
    2: ("smallint", "number"),
    3: ("int", "number"),
    4: ("float", "number"),
    5: ("double", "number"),
    6: ("null", "other"),
    7: ("timestamp", "datetime"),
    8: ("bigint", "number"),
    9: ("mediumint", "number"),
    10: ("date", "datetime"),
    11: ("time", "datetime"),
    12: ("datetime", "datetime"),
    13: ("year", "number"),
    14: ("date", "datetime"),
    15: ("varchar", "string"),
    16: ("bit", "number"),
    245: ("json", "json"),
    246: ("decimal", "number"),
    247: ("enum", "enum"),
    248: ("set", "string"),
    249: ("text", "string"),
    250: ("text", "string"),
    251: ("text", "string"),
    252: ("text", "string"),
    253: ("varchar", "string"),
    254: ("char", "string"),
    255: ("geometry", "binary"),
}


def wire_type(code: int) -> tuple[str, TypeCategory]:
    """What a result column of this wire type is, where nothing else says."""
    return _WIRE_TYPES.get(code, ("unknown", "other"))
