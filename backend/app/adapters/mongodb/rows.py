"""A document named by its `_id` and a digest of the whole of it (D287).

The handle carries the `_id` as canonical Extended JSON, so an id of any BSON
type comes back as exactly itself, and a digest of the document as it was
read. A change is made with a filter that holds the document read, compared
as a whole by the server, so a document changed in between is not matched and
nothing is written to it.
"""

import hashlib
from collections.abc import Mapping
from typing import Any

from bson import json_util
from bson.binary import UuidRepresentation
from bson.json_util import JSONMode, JSONOptions

from app.adapters.fetch import FetchColumn
from app.adapters.mongodb.inspection import CollectionFacts
from app.adapters.mongodb.relation import system_reason
from app.adapters.mongodb.values import Tag, addressable, parsed_value
from app.adapters.row_handles import decode_handle, encode_handle
from app.core.translation import say

_CANONICAL = JSONOptions(
    json_mode=JSONMode.CANONICAL, tz_aware=True, uuid_representation=UuidRepresentation.STANDARD
)


def canonical(value: Any) -> str:
    return json_util.dumps(value, json_options=_CANONICAL, separators=(",", ":"), sort_keys=False)


def from_canonical(text: str) -> Any:
    return json_util.loads(text, json_options=_CANONICAL)


def digest(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(document).encode()).hexdigest()[:32]


def handle_of(document: Mapping[str, Any]) -> str | None:
    if "_id" not in document:
        return None
    return encode_handle([canonical(document["_id"])], digest(document))


def read_handle(value: str) -> tuple[Any, str]:
    """The `_id` a handle names and the digest it was read with."""
    handle = decode_handle(value, 1, nulls=False)
    key = handle.keys[0]
    assert key is not None
    try:
        return from_canonical(key), handle.version
    except Exception:
        raise ValueError(say("The row handle is not valid")) from None


def unchanged(document: Mapping[str, Any]) -> dict[str, Any]:
    """A filter matching this document only as it is now, compared whole."""
    return {"_id": document["_id"], "$expr": {"$eq": ["$$ROOT", {"$literal": dict(document)}]}}


def written_value(text: str | None, tag: Tag) -> Any:
    """What a cell typed in is stored as (D287).

    A field of a known scalar type takes the text as that type; an object, an
    array and a mixed field take relaxed Extended JSON, and a mixed field takes
    text that is not JSON as a string.
    """
    if text is None:
        return None
    match tag:
        case "object" | "array":
            value = json_util.loads(text)
            if tag == "object" and not isinstance(value, Mapping):
                raise ValueError
            if tag == "array" and not isinstance(value, list):
                raise ValueError
            return value
        case "mixed":
            try:
                return json_util.loads(text)
            except ValueError:
                return text
        case "binData":
            if not text.lower().startswith("0x"):
                raise ValueError
            return bytes.fromhex(text[2:])
        case _:
            return parsed_value(text, tag)


def editing_reason(facts: CollectionFacts) -> str | None:
    """Why documents of this collection cannot be changed, or nothing."""
    if facts.is_view:
        return say("A view's documents come from its pipeline and cannot be changed")
    if facts.type == "timeseries":
        return say("A time series takes new documents; the ones in it are not changed here")
    return system_reason(facts)


def inserting_reason(facts: CollectionFacts) -> str | None:
    if facts.is_view:
        return say("A view's documents come from its pipeline and cannot be changed")
    return system_reason(facts)


def editable(column: FetchColumn) -> bool:
    """A field a cell may change: anything but `_id`, which is for ever."""
    return column.name != "_id" and addressable(column.name)


def insertable(column: FetchColumn) -> bool:
    return addressable(column.name)
