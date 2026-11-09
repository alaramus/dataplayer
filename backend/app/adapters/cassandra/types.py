"""CQL types as the neutral column type, and CQL values as the text of a cell (D342).

A type is read from the text `system_schema.columns` keeps (`map<text, int>`,
`frozen<list<int>>`, a user-defined type by its name); a value is what the
driver decoded, written back as text the grid shows and a later slice parses.
"""

import json
import math
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any
from uuid import UUID

from cassandra.util import Date, Duration, OrderedMap, SortedSet, Time

from app.adapters.cells import encode_cell
from app.adapters.relation import ColumnType, TypeCategory

_SCALARS: dict[str, TypeCategory] = {
    "ascii": "string",
    "text": "string",
    "varchar": "string",
    "tinyint": "number",
    "smallint": "number",
    "int": "number",
    "bigint": "number",
    "varint": "number",
    "counter": "number",
    "float": "number",
    "double": "number",
    "decimal": "number",
    "boolean": "boolean",
    "timestamp": "datetime",
    "date": "datetime",
    "time": "datetime",
    "duration": "other",
    "uuid": "uuid",
    "timeuuid": "uuid",
    "inet": "network",
    "blob": "binary",
}

INTEGERS = frozenset({"tinyint", "smallint", "int", "bigint", "varint", "counter"})
FLOATS = frozenset({"float", "double"})
TEXTS = frozenset({"ascii", "text", "varchar"})


def split_arguments(text: str) -> list[str]:
    """`text, frozen<map<int, text>>` split at its own commas only."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current or parts:
        parts.append("".join(current).strip())
    return parts


_GENERIC = re.compile(r"^([A-Za-z_][A-Za-z0-9_.']*)\s*<(.*)>$", re.DOTALL)


def unfrozen(text: str) -> str:
    """The type without `frozen<…>`, which says how it is stored and not what it holds."""
    text = text.strip()
    found = _GENERIC.match(text)
    while found and found.group(1).lower() == "frozen":
        text = found.group(2).strip()
        found = _GENERIC.match(text)
    return text


def type_name(text: str) -> str:
    """`map` of `map<text, int>`, `int` of `int`, a UDT's own name."""
    inner = unfrozen(text)
    found = _GENERIC.match(inner)
    return (found.group(1) if found else inner).lower()


def type_arguments(text: str) -> list[str]:
    inner = unfrozen(text)
    found = _GENERIC.match(inner)
    return split_arguments(found.group(2)) if found else []


def build_column_type(text: str) -> ColumnType:
    name = type_name(text)
    category = _SCALARS.get(name)
    if category is not None:
        return ColumnType(sql=text, category=category)
    arguments = type_arguments(text)
    if name in ("list", "set") and arguments:
        return ColumnType(
            sql=text,
            category="array",
            element=build_column_type(arguments[0]),
            dimensions=1,
        )
    if name == "vector" and arguments:
        return ColumnType(
            sql=text,
            category="array",
            element=build_column_type(arguments[0]),
            dimensions=1,
        )
    if name == "map":
        return ColumnType(sql=text, category="json")
    # A tuple and a user-defined type: named or positional fields.
    return ColumnType(sql=text, category="composite")


def _plain(value: Any) -> Any:
    """A decoded value as JSON's own shapes, every number kept exact."""
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return _Number(str(value))
    if isinstance(value, float):
        return (
            _Number(_float_text(value)) if math.isfinite(value) else _float_text(value)
        )
    if isinstance(value, Decimal):
        return _Number(str(value)) if value.is_finite() else str(value)
    if isinstance(value, OrderedMap | dict):
        items = list(value.items())
        if all(isinstance(key, str) for key, _ in items):
            return {key: _plain(item) for key, item in items}
        # Keys that are not text cannot be JSON's: a list of pairs keeps them.
        return [[_plain(key), _plain(item)] for key, item in items]
    if isinstance(value, list | SortedSet | set | frozenset):
        return [_plain(item) for item in value]
    fields = getattr(value, "_fields", None)
    if isinstance(fields, tuple) and type(value) is not tuple:
        # A user-defined type, decoded as a named tuple.
        return {str(name): _plain(getattr(value, name)) for name in fields}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return scalar_text(value)


class _Number:
    def __init__(self, text: str) -> None:
        self.text = text


def _encode(value: Any) -> str:
    if isinstance(value, _Number):
        return value.text
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(
                f"{json.dumps(key, ensure_ascii=False)}:{_encode(item)}"
                for key, item in value.items()
            )
            + "}"
        )
    raise TypeError("Not a JSON value")


def _float_text(value: float) -> str:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    return repr(value)


def duration_text(value: Duration) -> str:
    """A duration in CQL's own unit form: `1mo2d3h4m5s6ms7us8ns`."""
    months, days, nanoseconds = (
        int(value.months),
        int(value.days),
        int(value.nanoseconds),
    )
    if months == 0 and days == 0 and nanoseconds == 0:
        return "0s"
    negative = months < 0 or days < 0 or nanoseconds < 0
    months, days, nanoseconds = abs(months), abs(days), abs(nanoseconds)
    parts: list[str] = []
    years, months = divmod(months, 12)
    for amount, unit in ((years, "y"), (months, "mo"), (days, "d")):
        if amount:
            parts.append(f"{amount}{unit}")
    for size, unit in (
        (3_600_000_000_000, "h"),
        (60_000_000_000, "m"),
        (1_000_000_000, "s"),
        (1_000_000, "ms"),
        (1_000, "us"),
        (1, "ns"),
    ):
        amount, nanoseconds = divmod(nanoseconds, size)
        if amount:
            parts.append(f"{amount}{unit}")
    return ("-" if negative else "") + "".join(parts)


def time_text(value: Time) -> str:
    nanoseconds = int(value.nanosecond_time)
    seconds, fraction = divmod(nanoseconds, 1_000_000_000)
    hours, rest = divmod(seconds, 3600)
    minutes, second = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{second:02d}.{fraction:09d}"


def scalar_text(value: Any) -> str:
    """One scalar the driver decoded, as the text of a cell."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return _float_text(value)
    if isinstance(value, datetime):
        # The driver decodes a timestamp as a naive moment in UTC.
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return moment.isoformat()
    if isinstance(value, Date):
        # A date outside Python's years stays the day count the driver keeps.
        try:
            return str(value.date().isoformat())
        except ValueError:
            return str(value.days_from_epoch)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Time):
        return time_text(value)
    if isinstance(value, Duration):
        return duration_text(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return f"0x{bytes(value).hex().upper()}"
    if isinstance(value, UUID | IPv4Address | IPv6Address | Decimal | int | str):
        return str(value)
    return str(value)


def read_cell(value: Any, type_: ColumnType) -> str | None:
    """A decoded value as the text of its cell."""
    if value is None:
        return None
    if type_.category in ("array", "json", "composite"):
        return _encode(_plain(value))
    if type_.category == "boolean":
        return encode_cell(value, type_)
    return scalar_text(value)


def _from_json(value: Any, type_text: str) -> Any:
    """A JSON value, already parsed, as the Python value the driver binds."""
    if value is None:
        return None
    name = type_name(type_text)
    arguments = type_arguments(type_text)
    if name in ("list", "vector"):
        if not isinstance(value, list):
            raise ValueError
        return [_from_json(item, arguments[0]) for item in value]
    if name == "set":
        if not isinstance(value, list):
            raise ValueError
        return {_hashable(_from_json(item, arguments[0])) for item in value}
    if name == "map":
        if isinstance(value, dict):
            pairs = list(value.items())
        elif isinstance(value, list) and all(
            isinstance(pair, list) and len(pair) == 2 for pair in value
        ):
            pairs = [(pair[0], pair[1]) for pair in value]
        else:
            raise ValueError
        return {
            _hashable(_from_json(key, arguments[0])): _from_json(item, arguments[1])
            for key, item in pairs
        }
    if name == "tuple":
        if not isinstance(value, list) or len(value) != len(arguments):
            raise ValueError
        return tuple(
            _from_json(item, argument)
            for item, argument in zip(value, arguments, strict=True)
        )
    if name in _SCALARS:
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, str):
            text = value
        else:
            text = json.dumps(value)
        return parse_value(text, type_text)
    # A user-defined type: its fields by name, which the driver binds from a dict.
    if not isinstance(value, dict):
        raise ValueError
    return value


def _hashable(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_hashable(item) for item in value)
    if isinstance(value, set):
        return frozenset(value)
    if isinstance(value, dict):
        return tuple(sorted(value.items()))
    return value


def parse_value(text: str, type_text: str) -> Any:
    """Text a person wrote, as the Python value the driver binds to this CQL type.

    The reverse of `read_cell`: a scalar in the spelling a cell shows it in, a
    collection, a tuple or a user-defined type as JSON. Raises ValueError for
    text the type cannot hold.
    """
    name = type_name(type_text)
    if name in INTEGERS:
        return int(text.strip())
    if name in FLOATS:
        return float(text.strip())
    if name == "decimal":
        try:
            number = Decimal(text.strip())
        except ArithmeticError:
            raise ValueError from None
        if not number.is_finite():
            raise ValueError
        return number
    if name in TEXTS:
        return text
    if name == "boolean":
        lowered = text.strip().lower()
        if lowered not in ("true", "false"):
            raise ValueError
        return lowered == "true"
    if name == "timestamp":
        moment = datetime.fromisoformat(text.strip())
        # A moment with no offset is UTC, as every moment is shown.
        return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    if name == "date":
        return date.fromisoformat(text.strip())
    if name == "time":
        return Time(text.strip())
    if name in ("uuid", "timeuuid"):
        return UUID(text.strip())
    if name == "inet":
        return str(ip_address(text.strip()))
    if name == "blob":
        hexadecimal = text.strip()
        if hexadecimal[:2].lower() == "0x":
            hexadecimal = hexadecimal[2:]
        return bytes.fromhex(hexadecimal)
    if name == "duration":
        raise ValueError
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError from None
    return _from_json(parsed, type_text)


def driver_value(value: Any, cql_type: Any) -> Any:
    """A value `parse_value` made, shaped as the driver serializes `cql_type`.

    The driver writes a user-defined type from its fields in order, not from
    a dictionary, and a field's value as its own type; the server's description
    of a prepared statement names both, so the shaping happens here.
    """
    if value is None:
        return None
    subtypes = list(getattr(cql_type, "subtypes", ()) or ())
    fields = getattr(cql_type, "fieldnames", None)
    if fields is not None:
        if not isinstance(value, dict):
            raise ValueError
        unknown = set(value) - set(fields)
        if unknown:
            raise ValueError
        return tuple(
            driver_value(_field(value.get(name), subtype), subtype)
            for name, subtype in zip(fields, subtypes, strict=True)
        )
    if not subtypes:
        return value
    if isinstance(value, dict):
        key_type, item_type = subtypes[0], subtypes[-1]
        return {
            _hashable(driver_value(_field(key, key_type), key_type)): driver_value(
                _field(item, item_type), item_type
            )
            for key, item in value.items()
        }
    if getattr(cql_type, "typename", "") == "tuple":
        if not isinstance(value, tuple | list) or len(value) != len(subtypes):
            raise ValueError
        return tuple(
            driver_value(_field(item, subtype), subtype)
            for item, subtype in zip(value, subtypes, strict=True)
        )
    if isinstance(value, list | tuple):
        return [driver_value(_field(item, subtypes[0]), subtypes[0]) for item in value]
    if isinstance(value, set | frozenset):
        return {
            _hashable(driver_value(_field(item, subtypes[0]), subtypes[0]))
            for item in value
        }
    return value


def _field(value: Any, cql_type: Any) -> Any:
    """A field of a user-defined type still in JSON's shapes, read as its type."""
    if value is None or getattr(cql_type, "fieldnames", None) is not None:
        return value
    spelled = getattr(cql_type, "cql_parameterized_type", None)
    text = str(spelled()) if callable(spelled) else ""
    if type_name(text) not in _SCALARS:
        return value
    if isinstance(value, bool):
        return parse_value("true" if value else "false", text)
    if isinstance(value, str | int | float):
        return parse_value(value if isinstance(value, str) else json.dumps(value), text)
    return value
