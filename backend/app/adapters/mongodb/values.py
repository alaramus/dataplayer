"""A document's values as text, and the columns a sample of documents has (D284).

A scalar crosses as its text (D23): a number as Python writes it, an ObjectId
as its hex, a moment in UTC with `Z` and its milliseconds, a UUID in its
canonical form, bytes as `0x…`. An object, an array and every BSON type with no
plain spelling cross as relaxed Extended JSON, the form `mongosh` and
`mongoexport` write, so `{"$oid": …}` and `{"$date": …}` say what they are.
"""

import math
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from bson import Decimal128, Int64, ObjectId, json_util
from bson.binary import Binary, UuidRepresentation
from bson.json_util import JSONMode, JSONOptions

from app.adapters.fetch import FilterOp
from app.adapters.relation import ColumnType, TypeCategory

_RELAXED = JSONOptions(json_mode=JSONMode.RELAXED, tz_aware=True, uuid_representation=UuidRepresentation.STANDARD)

# The BSON types a field is told apart by, as `$type` names them; `mixed` is a
# field whose documents disagree, `number` one whose numbers do.
Tag = Literal[
    "objectId",
    "string",
    "int",
    "long",
    "double",
    "decimal",
    "number",
    "bool",
    "date",
    "uuid",
    "binData",
    "object",
    "array",
    "mixed",
]

_CATEGORIES: dict[Tag, TypeCategory] = {
    "objectId": "other",
    "string": "string",
    "int": "number",
    "long": "number",
    "double": "number",
    "decimal": "number",
    "number": "number",
    "bool": "boolean",
    "date": "datetime",
    "uuid": "uuid",
    "binData": "binary",
    "object": "json",
    "array": "json",
    "mixed": "other",
}

_NUMBERS = frozenset({"int", "long", "double", "decimal", "number"})

# $jsonSchema's bsonType words that name one of the tags above.
_SCHEMA_TYPES: dict[str, Tag] = {
    "objectId": "objectId",
    "string": "string",
    "int": "int",
    "long": "long",
    "double": "double",
    "decimal": "decimal",
    "number": "number",
    "bool": "bool",
    "date": "date",
    "binData": "binData",
    "object": "object",
    "array": "array",
}


def tag_of(value: Any) -> Tag | None:
    """The tag of one value; None for a null, which says nothing of the field."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, Int64):
        return "long"
    if isinstance(value, int):
        return "int" if -(2**31) <= value < 2**31 else "long"
    if isinstance(value, float):
        return "double"
    if isinstance(value, Decimal128):
        return "decimal"
    if isinstance(value, str):
        return "string"
    if isinstance(value, ObjectId):
        return "objectId"
    if isinstance(value, datetime):
        return "date"
    if isinstance(value, uuid.UUID):
        return "uuid"
    if isinstance(value, bytes):
        return "binData"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list):
        return "array"
    return "mixed"


def joined(left: Tag | None, right: Tag | None) -> Tag | None:
    if left is None or left == right:
        return right
    if right is None:
        return left
    if left in _NUMBERS and right in _NUMBERS:
        return "number"
    return "mixed"


def column_type(tag: Tag | None) -> ColumnType:
    """A field's type: its BSON name, and how the grid should treat it.

    A field only ever null in the sample is `mixed`: nothing is known of it.
    """
    known: Tag = tag or "mixed"
    return ColumnType(sql=known, category=_CATEGORIES[known])


def tag_from_type(type_: ColumnType) -> Tag:
    for tag in _CATEGORIES:
        if tag == type_.sql:
            return tag
    return "mixed"


def relaxed_json(value: Any) -> str:
    return json_util.dumps(
        value, json_options=_RELAXED, ensure_ascii=False, separators=(",", ":")
    )


def _moment(value: datetime) -> str:
    moment = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _number(value: float) -> str:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    return repr(value)


def read_cell(value: Any) -> str | None:
    """The text of one value as the grid shows it (D284)."""
    match value:
        case None:
            return None
        case bool():
            return "true" if value else "false"
        case int() | Int64():
            return str(int(value))
        case float():
            return _number(value)
        case Decimal128():
            return str(value)
        case str():
            return value
        case ObjectId():
            return str(value)
        case datetime():
            return _moment(value)
        case uuid.UUID():
            return str(value)
        case Binary() if value.subtype == 0:
            return f"0x{bytes(value).hex().upper()}"
        case bytes() if not isinstance(value, Binary):
            return f"0x{value.hex().upper()}"
        case _:
            return relaxed_json(value)


# A field name that a query cannot name as a path: a dot is a step into an
# embedded document, a leading `$` an operator, and NUL ends a C string.
_UNADDRESSABLE = re.compile(r"^\$|\.|\x00")


def addressable(name: str) -> bool:
    return name != "" and _UNADDRESSABLE.search(name) is None


@dataclass
class SampledField:
    name: str
    tag: Tag | None = None
    # Holding a value in every document read, or declared required by the
    # validator: what the grid calls not nullable.
    everywhere: bool = True
    declared: bool = False


@dataclass
class FieldSample:
    """The fields of a collection, as its validator and its documents say."""

    fields: dict[str, SampledField] = field(default_factory=dict)
    documents: int = 0

    def declare(self, name: str, tag: Tag | None, required: bool) -> None:
        self.fields[name] = SampledField(name=name, tag=tag, everywhere=required, declared=True)

    def read(self, documents: Iterable[Mapping[str, Any]]) -> None:
        for document in documents:
            self.documents += 1
            for name, value in document.items():
                found = self.fields.get(name)
                if found is None:
                    # Absent from every document before this one.
                    found = SampledField(name=name, everywhere=self.documents == 1)
                    self.fields[name] = found
                if not found.declared:
                    found.tag = joined(found.tag, tag_of(value))
                    if value is None:
                        found.everywhere = False
            for name, known in self.fields.items():
                if name not in document and not known.declared:
                    known.everywhere = False

    def ordered(self) -> list[SampledField]:
        """`_id` first, then the order fields were declared and met in."""
        fields = list(self.fields.values())
        return sorted(fields, key=lambda sampled: sampled.name != "_id")


def schema_fields(validator: Mapping[str, Any] | None) -> list[tuple[str, Tag | None, bool]]:
    """The top-level properties a `$jsonSchema` validator declares."""
    if not isinstance(validator, Mapping):
        return []
    schema = validator.get("$jsonSchema")
    if not isinstance(schema, Mapping):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return []
    required = schema.get("required")
    needed = set(required) if isinstance(required, list) else set()
    declared: list[tuple[str, Tag | None, bool]] = []
    for name, rule in properties.items():
        tag: Tag | None = None
        if isinstance(rule, Mapping):
            words = rule.get("bsonType")
            listed = [words] if isinstance(words, str) else words if isinstance(words, list) else []
            tags = [_SCHEMA_TYPES.get(word) for word in listed if word != "null"]
            for one in tags:
                tag = joined(tag, one) if one is not None else "mixed"
        declared.append((str(name), tag, name in needed))
    return declared


# What each tag may be filtered and sorted by. Comparisons are BSON's own, so
# an ObjectId orders by the moment it was made.
_ORDERED = frozenset({"objectId", "string", "int", "long", "double", "decimal", "number", "date"})


def capabilities(tag: Tag, name: str) -> tuple[bool, list[FilterOp]]:
    if not addressable(name):
        return False, []
    operators: list[FilterOp] = []
    if tag in _ORDERED or tag in ("bool", "uuid"):
        operators.extend(["eq", "ne", "in"])
    if tag in _ORDERED:
        operators.extend(["gt", "gte", "lt", "lte"])
    if tag == "string":
        operators.extend(["contains", "starts_with"])
    operators.extend(["is_null", "is_not_null"])
    return tag not in ("object", "array", "binData"), operators


_TRUTHS = {"true": True, "1": True, "false": False, "0": False}


def _parsed_number(text: str, tag: Tag) -> Any:
    try:
        number = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError from None
    if not number.is_finite():
        raise ValueError
    if tag == "decimal":
        return Decimal128(number)
    if tag != "double" and number == number.to_integral_value():
        whole = int(number)
        if -(2**63) <= whole < 2**63:
            return Int64(whole) if tag == "long" else whole
    return float(number)


def _parsed_moment(text: str) -> datetime:
    value = text.strip()
    if value.endswith(("Z", "z")):
        value = value[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        day = date.fromisoformat(value)
        moment = datetime(day.year, day.month, day.day)
    return moment.astimezone(UTC) if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def parsed_value(text: str, tag: Tag) -> Any:
    """A value typed in, as the value of a field of this tag.

    Raises `ValueError` for text the field cannot hold; a field of mixed type
    is compared as text, which is what it most often holds.
    """
    match tag:
        case "string" | "mixed":
            return text
        case "int" | "long" | "double" | "decimal" | "number":
            return _parsed_number(text, tag)
        case "bool":
            truth = _TRUTHS.get(text.strip().lower())
            if truth is None:
                raise ValueError
            return truth
        case "date":
            return _parsed_moment(text)
        case "objectId":
            if not ObjectId.is_valid(text.strip()):
                raise ValueError
            return ObjectId(text.strip())
        case "uuid":
            return uuid.UUID(text.strip())
        case _:
            raise ValueError
