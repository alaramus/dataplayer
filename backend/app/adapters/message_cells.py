"""A message's bytes as cells, for a source whose rows are messages.

Kafka's topics (D306) and RabbitMQ's streams (D327) both show a body as text
or hex, lay the top-level fields of JSON bodies out as columns, and filter
what was read rather than asking the server, which keeps no index on bodies.
"""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.adapters import jsontext
from app.adapters.fetch import Filter, FilterOp, InFilter, NullFilter
from app.adapters.relation import TypeCategory
from app.core.translation import say

# Characters of a key or a body shown in a cell.
CELL_CHARACTERS = 65_536

TEXT_OPS: list[FilterOp] = [
    "eq",
    "ne",
    "contains",
    "starts_with",
    "is_null",
    "is_not_null",
]
RANGE_OPS: list[FilterOp] = ["gte", "gt", "lte", "lt"]


def text_of(raw: bytes | None) -> str | None:
    """UTF-8 as text, anything else as hex, as MongoDB's bytes are (D284)."""
    if raw is None:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = "0x" + raw.hex()
    if len(text) > CELL_CHARACTERS:
        return text[:CELL_CHARACTERS] + "…"
    return text


def json_of(raw: bytes | None) -> Any:
    """A body that is a JSON object, or nothing."""
    if raw is None or not raw.lstrip().startswith(b"{"):
        return None
    try:
        parsed = jsontext.load(raw.decode("utf-8"))
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def is_json(raw: bytes | None) -> bool:
    if raw is None:
        return True
    try:
        jsontext.load(raw.decode("utf-8"))
    except ValueError:
        return False
    return True


def moment(milliseconds: int | None) -> str | None:
    if milliseconds is None:
        return None
    at = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def milliseconds_of(text: str) -> int:
    try:
        at = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(say("timestamp takes a date and time")) from None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return int(at.timestamp() * 1000)


def json_text(mapping: dict[str, Any]) -> str | None:
    """Headers or properties as one cell, nothing when there are none."""
    if not mapping:
        return None
    return json.dumps(mapping, ensure_ascii=False, default=str)


def field_text(value: Any) -> str | None:
    """A field of a JSON body as a cell: a string as itself, the rest as JSON."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return jsontext.encode(value)


def _category(value: Any) -> TypeCategory:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, jsontext.JsonNumber):
        return "number"
    if isinstance(value, str):
        return "string"
    return "json"


def body_shape(
    bodies: list[bytes | None],
) -> tuple[TypeCategory, tuple[tuple[str, TypeCategory], ...]]:
    """What the newest bodies say: the body's category, and each field of the
    JSON objects among them in the order met, with its category."""
    all_json = all(is_json(body) for body in bodies)
    found: dict[str, TypeCategory] = {}
    for body in bodies:
        value = json_of(body)
        if value is None:
            continue
        for name, item in value.items():
            if item is None:
                found.setdefault(name, "string")
                continue
            category = _category(item)
            known = found.get(name)
            if known is None:
                found[name] = category
            elif known != category:
                found[name] = "string"
    return ("json" if all_json and bodies else "string"), tuple(found.items())


def _as_number(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def predicate[M](
    one: Filter, cell: Callable[[M, str], str | None]
) -> Callable[[M], bool]:
    """A filter applied to a message already read, through its cell."""
    column = one.column
    if isinstance(one, NullFilter):
        wanted_null = one.op == "is_null"
        return lambda message: (cell(message, column) is None) == wanted_null
    if isinstance(one, InFilter):
        values = set(one.values)
        return lambda message: cell(message, column) in values
    needle = one.value
    folded = needle.casefold()
    if one.op in {"gt", "gte", "lt", "lte"}:
        limit = _as_number(needle)
        if limit is None:
            raise ValueError(say("{column} takes a number", column=column))
        op = one.op

        def compares(message: M) -> bool:
            text = cell(message, column)
            number = None if text is None else _as_number(text)
            if number is None:
                return False
            return {
                "gt": number > limit,
                "gte": number >= limit,
                "lt": number < limit,
                "lte": number <= limit,
            }[op]

        return compares
    if one.op == "contains":
        return lambda message: folded in (cell(message, column) or "").casefold()
    if one.op == "starts_with":
        return lambda message: (
            (cell(message, column) or "").casefold().startswith(folded)
        )
    if one.op == "ne":
        return lambda message: cell(message, column) != needle
    return lambda message: cell(message, column) == needle


def bytes_of(text: str) -> bytes:
    """`0x` and hex digits is those bytes, as they are shown; anything else UTF-8."""
    if text.startswith("0x") and len(text) % 2 == 0 and len(text) > 2:
        try:
            return bytes.fromhex(text[2:])
        except ValueError:
            pass
    return text.encode("utf-8")


def field_value(text: str, category: TypeCategory) -> Any:
    """A field of a JSON body, read as its column's JSON type."""
    if category in {"number", "boolean", "json"}:
        parsed = jsontext.load(text)
        if category == "number" and not isinstance(parsed, jsontext.JsonNumber):
            raise ValueError(text)
        if category == "boolean" and not isinstance(parsed, bool):
            raise ValueError(text)
        return parsed
    return text
