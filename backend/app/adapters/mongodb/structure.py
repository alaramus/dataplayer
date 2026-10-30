"""A collection's fields changed in every document, and its indexes (D288).

A collection has no columns, so a change to one is a change to every
document: a field added as null where it is missing, removed with `$unset`,
renamed with `$rename`, converted with `$convert` — each one `updateMany`,
which the server applies document by document. A conversion counts the
documents it could not convert first, and changes nothing if there are any.
"""

from typing import Any

from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    ColumnTypeBlocked,
    ColumnTypeChanged,
    ColumnTypeChangeResult,
    ColumnTypeRequest,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexBlocked,
    IndexCreated,
    IndexDropped,
)
from app.adapters.mongodb.inspection import CollectionFacts
from app.adapters.mongodb.relation import MongodbRelation, structure_reason
from app.adapters.mongodb.session import MongodbSession
from app.adapters.mongodb.values import addressable
from app.adapters.mongodb.vocabulary import CONVERSIONS, INDEX_KEYS
from app.core.translation import N_, say

# Duplicates counted before a unique index is made; past this, "at least".
MAX_COUNTED = 10_000

_INDEX_REFUSALS = {
    85: N_("An index on these fields already exists under another name"),
    86: N_("An index of that name already exists with other fields"),
    67: N_("The server cannot make that index on these fields"),
}


class MongodbStructure:
    def __init__(self, session: MongodbSession, relation: MongodbRelation) -> None:
        self._session = session
        self._relation = relation

    async def _changeable(self, node_id: str) -> CollectionFacts:
        facts = await self._relation.facts(node_id)
        refused = structure_reason(facts)
        if refused is not None:
            raise ValueError(refused)
        return facts

    @staticmethod
    def _field(facts: CollectionFacts, name: str) -> str:
        if name == "_id":
            raise ValueError(say("_id is every document's own and cannot be changed"))
        if not addressable(name):
            raise ValueError(say('A field named "{name}" cannot be changed by a query', name=name))
        if name not in {field.name for field in facts.fields}:
            raise ValueError(say('Relation has no column "{column}"', column=name))
        return name

    @staticmethod
    def _new_name(facts: CollectionFacts, name: str) -> str:
        if not addressable(name) or name == "_id":
            raise ValueError(say('"{name}" cannot be the name of a field', name=name))
        if name in {field.name for field in facts.fields}:
            raise ValueError(say('A field named "{name}" is there already', name=name))
        return name

    async def _every(self, facts: CollectionFacts, query: dict[str, Any], change: Any) -> None:
        async with self._session.client() as client:
            with self._session.failures():
                await client[facts.database][facts.name].update_many(query, change)

    async def add_column(self, request: AddColumnRequest) -> ColumnChangeResult:
        """The field, null, in every document that does not have it."""
        facts = await self._changeable(request.node_id)
        name = self._new_name(facts, request.name)
        if not request.nullable:
            raise ValueError(say("A new field is empty in every document until it is filled"))
        if request.type_code not in CONVERSIONS:
            raise ValueError(say("Unknown column type"))
        await self._every(facts, {name: {"$exists": False}}, {"$set": {name: None}})
        return ColumnChangeResult(name=name)

    async def drop_column(self, request: DropColumnRequest) -> ColumnChangeResult:
        facts = await self._changeable(request.node_id)
        name = self._field(facts, request.name)
        await self._every(facts, {name: {"$exists": True}}, {"$unset": {name: ""}})
        return ColumnChangeResult(name=name)

    async def rename_column(self, request: RenameColumnRequest) -> ColumnChangeResult:
        facts = await self._changeable(request.node_id)
        name = self._field(facts, request.name)
        new_name = self._new_name(facts, request.new_name)
        await self._every(facts, {name: {"$exists": True}}, {"$rename": {name: new_name}})
        return ColumnChangeResult(name=new_name)

    async def change_column_type(self, request: ColumnTypeRequest) -> ColumnTypeChangeResult:
        """Every value converted by the server's own `$convert`, or none.

        Counted first: a document whose value would not convert keeps the
        collection as it was. A null and a missing field stay as they are.
        """
        facts = await self._changeable(request.node_id)
        name = self._field(facts, request.name)
        target = CONVERSIONS.get(request.type_code)
        if target is None:
            raise ValueError(say("Unknown column type"))
        converted = {"$convert": {"input": f"${name}", "to": target.convert_to, "onNull": None}}
        probe = {
            "$convert": {"input": f"${name}", "to": target.convert_to, "onError": _FAILED, "onNull": None}
        }
        present = {name: {"$exists": True, "$ne": None}}
        async with self._session.client() as client:
            collection = client[facts.database][facts.name]
            with self._session.failures():
                counted = await (
                    await collection.aggregate(
                        [
                            {"$match": present},
                            {"$match": {"$expr": {"$eq": [probe, _FAILED]}}},
                            {"$limit": MAX_COUNTED + 1},
                            {"$count": "failed"},
                        ]
                    )
                ).to_list()
                failures = int(counted[0]["failed"]) if counted else 0
                if failures:
                    return ColumnTypeBlocked(
                        name=name,
                        rows_not_convertible=min(failures, MAX_COUNTED),
                        exact=failures <= MAX_COUNTED,
                    )
                await collection.update_many(present, [{"$set": {name: converted}}])
        return ColumnTypeChanged(name=name, type_sql=target.tag)

    async def create_index(self, request: CreateIndexRequest) -> CreateIndexResult:
        facts = await self._changeable(request.node_id)
        method = INDEX_KEYS.get(request.method)
        if method is None:
            raise ValueError(say("Unknown index method"))
        if request.unique and not method.unique:
            raise ValueError(say("A {method} index cannot be unique", method=say(method.title)))
        if len(request.columns) > 1 and not method.compound:
            raise ValueError(say("A {method} index covers one field", method=say(method.title)))
        fields = [
            name if name == "_id" else self._field(facts, name) for name in request.columns
        ]
        async with self._session.client() as client:
            collection = client[facts.database][facts.name]
            with self._session.failures(_INDEX_REFUSALS):
                if request.unique:
                    groups = await (
                        await collection.aggregate(
                            [
                                {"$group": {"_id": {name: f"${name}" for name in fields}, "n": {"$sum": 1}}},
                                {"$match": {"n": {"$gt": 1}}},
                                {"$limit": MAX_COUNTED + 1},
                                {"$count": "groups"},
                            ],
                            allowDiskUse=True,
                        )
                    ).to_list()
                    duplicates = int(groups[0]["groups"]) if groups else 0
                    if duplicates:
                        return IndexBlocked(
                            duplicate_groups=min(duplicates, MAX_COUNTED),
                            exact=duplicates <= MAX_COUNTED,
                        )
                name = await collection.create_index(
                    [(field, method.key) for field in fields], unique=request.unique
                )
        return IndexCreated(name=name)

    async def drop_index(self, request: DropIndexRequest) -> IndexDropped:
        facts = await self._changeable(request.node_id)
        if request.name == "_id_":
            raise ValueError(say("The index on _id is every collection's own and cannot be dropped"))
        if request.name not in {str(index.get("name")) for index in facts.indexes}:
            raise ValueError(say('Relation has no index "{name}"', name=request.name))
        async with self._session.client() as client:
            with self._session.failures():
                await client[facts.database][facts.name].drop_index(request.name)
        return IndexDropped(name=request.name)


# What a value that would not convert is read as while counting. No stored
# value is this string; were one, it would be counted as not converting.
_FAILED = "dataplayer: not converted 7f3a9c"
