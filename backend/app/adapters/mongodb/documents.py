"""A collection's documents whole, and a document changed field by field (D295).

A page is the grid's own query (D285) read as documents: each one's text in
relaxed Extended JSON, the form `mongosh` writes, and the same as a tree. A
document past a ceiling is shown as the beginning of its text and is not
edited here.

A change is always field by field. Edited text is compared with the document
as it is stored, value by value, and only what differs is written, with
`$set` and `$unset` under the filter that holds the document read (D287). A
value nobody touched is therefore never written back, so an `Int64` stays one
though its text is a bare number; and an object is descended into, so a
change deep inside it leaves its other fields as they were.
"""

from collections.abc import Mapping
from typing import Any

from bson import json_util
from bson.binary import UuidRepresentation
from bson.json_util import JSONMode, JSONOptions

from app.adapters import jsontext
from app.adapters.content import json_tree
from app.adapters.documents import (
    DocumentChanged,
    DocumentChangeRequest,
    DocumentItem,
    DocumentsPage,
    DocumentsRequest,
    DocumentText,
)
from app.adapters.mongodb.fetch import PAGE_MILLISECONDS, MongodbFetch
from app.adapters.mongodb.relation import MongodbRelation
from app.adapters.mongodb.rows import (
    digest,
    editing_reason,
    handle_of,
    read_handle,
    unchanged,
)
from app.adapters.mongodb.session import (
    DOCUMENT_VALIDATION_FAILURE,
    DUPLICATE_KEY,
    MongodbSession,
)
from app.adapters.mongodb.values import addressable, relaxed_json
from app.adapters.update import RowConflict
from app.core.translation import N_, say

# The most of one document drawn and edited; past it, the beginning is shown.
MAX_DOCUMENT_BYTES = 256 * 1024

_RELAXED = JSONOptions(
    json_mode=JSONMode.RELAXED, tz_aware=True, uuid_representation=UuidRepresentation.STANDARD
)

UPDATE_CONFLICT = 40

_REFUSALS = {
    DUPLICATE_KEY: N_("Another document already has that value in a unique index"),
    DOCUMENT_VALIDATION_FAILURE: N_("The collection's validator refused the document"),
    UPDATE_CONFLICT: N_("Two changes touch the same field"),
}

type Path = tuple[str, ...]


def document_text(document: Mapping[str, Any]) -> str:
    return json_util.dumps(document, json_options=_RELAXED, ensure_ascii=False, indent=2)


def document_item(document: Mapping[str, Any]) -> DocumentItem:
    text = document_text(document)
    encoded = text.encode()
    if len(encoded) > MAX_DOCUMENT_BYTES:
        return DocumentItem(
            row_handle=handle_of(document),
            text=encoded[:MAX_DOCUMENT_BYTES].decode(errors="ignore"),
            truncated=True,
        )
    return DocumentItem(
        row_handle=handle_of(document),
        text=text,
        value=json_tree(jsontext.load(relaxed_json(document))),
    )


def parsed(text: str) -> Any:
    """A value in relaxed Extended JSON, or a refusal saying it is not one."""
    try:
        return json_util.loads(text, json_options=_RELAXED)
    except (ValueError, TypeError):
        raise ValueError(say("That is not valid JSON")) from None


def _same(before: Any, after: Any) -> bool:
    return relaxed_json(before) == relaxed_json(after)


def _descends(before: Any, after: Any) -> bool:
    """Whether a change inside an object can be written field by field."""
    return (
        isinstance(before, Mapping)
        and isinstance(after, Mapping)
        and all(addressable(key) for key in [*before, *after])
    )


def differences(
    before: Mapping[str, Any], after: Mapping[str, Any], prefix: Path = ()
) -> tuple[dict[Path, Any], list[Path]]:
    """What to set and what to remove so that `before` reads as `after`."""
    sets: dict[Path, Any] = {}
    unsets: list[Path] = []
    for key, value in after.items():
        if key not in before:
            sets[(*prefix, key)] = value
        elif _same(before[key], value):
            continue
        elif _descends(before[key], value):
            inner_sets, inner_unsets = differences(before[key], value, (*prefix, key))
            sets.update(inner_sets)
            unsets.extend(inner_unsets)
        else:
            sets[(*prefix, key)] = value
    unsets.extend((*prefix, key) for key in before if key not in after)
    return sets, unsets


def _dotted(path: Path) -> str:
    if path[0] == "_id":
        raise ValueError(say("_id is every document's own and cannot be changed"))
    for name in path:
        if not addressable(name):
            raise ValueError(
                say('A field named "{name}" cannot be changed by a query', name=name)
            )
    return ".".join(path)


class MongodbDocuments:
    def __init__(
        self, session: MongodbSession, relation: MongodbRelation, fetch: MongodbFetch
    ) -> None:
        self._session = session
        self._relation = relation
        self._fetch = fetch

    async def read_documents(self, request: DocumentsRequest) -> DocumentsPage:
        prepared = await self._fetch.prepare(request)
        facts = prepared.facts
        async with self._session.client() as client:
            with self._session.failures():
                cursor = client[facts.database][facts.name].find(prepared.query)
                if prepared.sort:
                    cursor = cursor.sort(prepared.sort)
                documents = await (
                    cursor.skip(request.offset)
                    .limit(request.limit + 1)
                    .max_time_ms(PAGE_MILLISECONDS)
                    .to_list()
                )
        refused = editing_reason(facts)
        return DocumentsPage(
            items=[document_item(document) for document in documents[: request.limit]],
            has_more=len(documents) > request.limit,
            offset=request.offset,
            change_supported=refused is None,
            change_reason=refused,
        )

    async def change_document(self, request: DocumentChangeRequest) -> DocumentChanged:
        facts = await self._relation.facts(request.node_id, structure=False)
        refused = editing_reason(facts)
        if refused is not None:
            raise ValueError(refused)
        key, version = read_handle(request.row_handle)
        async with self._session.client() as client:
            collection = client[facts.database][facts.name]
            with self._session.failures(_REFUSALS):
                document = await collection.find_one({"_id": key})
                if document is None or digest(document) != version:
                    raise RowConflict()
                sets, unsets = self._changes(document, request)
                if sets or unsets:
                    change: dict[str, Any] = {}
                    if sets:
                        change["$set"] = {_dotted(path): value for path, value in sets.items()}
                    if unsets:
                        change["$unset"] = {_dotted(path): "" for path in unsets}
                    answer = await collection.update_one(unchanged(document), change)
                    if answer.matched_count == 0:
                        raise RowConflict()
                    document = await collection.find_one({"_id": key})
                    if document is None:
                        raise RowConflict()
        return DocumentChanged(changed=len(sets) + len(unsets), item=document_item(document))

    @staticmethod
    def _changes(
        document: Mapping[str, Any], request: DocumentChangeRequest
    ) -> tuple[dict[Path, Any], list[Path]]:
        change = request.change
        if isinstance(change, DocumentText):
            edited = parsed(change.text)
            if not isinstance(edited, Mapping):
                raise ValueError(say("A document is a JSON object"))
            if "_id" in edited and not _same(document["_id"], edited["_id"]):
                raise ValueError(say("_id is every document's own and cannot be changed"))
            # An `_id` left out of the text is the document's still.
            return differences(document, {"_id": document["_id"], **edited})
        sets: dict[Path, Any] = {}
        unsets: list[Path] = []
        for field in change.changes:
            path = tuple(field.path)
            if field.op == "unset":
                unsets.append(path)
            elif field.value is None:
                raise ValueError(say("A field set needs a value"))
            else:
                sets[path] = parsed(field.value)
        return sets, unsets
