"""A MongoDB collection described in the adapter-neutral model (D284)."""

from collections.abc import Mapping
from typing import Any

from app.adapters.database_ids import parse
from app.adapters.mongodb.catalog import is_system_collection
from app.adapters.mongodb.inspection import CollectionFacts, read_collection
from app.adapters.mongodb.session import MongodbSession
from app.adapters.mongodb.values import column_type, relaxed_json
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import (
    Column,
    Constraint,
    Index,
    PrimaryKey,
    RelationModel,
)
from app.core.translation import say


def relation_parts(node_id: str) -> tuple[str, str]:
    database, collection = parse(node_id)
    if collection is None:
        raise ValueError(
            say('"{node_id}" is not a collection: expected database.collection', node_id=node_id)
        )
    return database, collection


def _method(key: Mapping[str, Any]) -> str:
    """What kind of index a key makes: `text`, `2dsphere`, `hashed`, or ordered."""
    kinds = {value for value in key.values() if isinstance(value, str)}
    return kinds.pop() if len(kinds) == 1 else "ordered"


def index_of(index: Mapping[str, Any]) -> Index:
    key = index.get("key") or {}
    name = str(index.get("name", ""))
    partial = index.get("partialFilterExpression")
    options = {
        name_: value
        for name_, value in index.items()
        if name_ not in ("v", "key", "name", "ns")
    }
    definition = relaxed_json(key) + (f" {relaxed_json(options)}" if options else "")
    return Index(
        name=name,
        method=_method(key),
        unique=bool(index.get("unique")) or name == "_id_",
        primary=name == "_id_",
        columns=[str(field) for field in key],
        predicate=None if partial is None else relaxed_json(partial),
        definition=definition,
    )


def model_of(node_id: str, facts: CollectionFacts) -> RelationModel:
    constraints: list[Constraint] = []
    if facts.type == "collection":
        # The one key every collection has and that nothing can take away.
        constraints.append(PrimaryKey(name="_id_", columns=["_id"]))
    refused = say("A collection has no columns of its own; every document has its own fields")
    return RelationModel(
        node_id=node_id,
        schema_name=facts.database,
        name=facts.name,
        kind="view" if facts.is_view else "table",
        persistence="permanent",
        row_estimate=facts.row_estimate,
        size_bytes=facts.size_bytes,
        columns=[
            Column(
                position=position,
                name=sampled.name,
                type=column_type(sampled.tag),
                nullable=not sampled.everywhere or sampled.tag is None,
            )
            for position, sampled in enumerate(facts.fields, start=1)
        ],
        constraints=constraints,
        indexes=[index_of(index) for index in facts.indexes],
        column_changes_reason=refused,
        index_changes_reason=say("Indexes are not changed here yet"),
        constraint_changes_reason=say("MongoDB has no constraints but unique indexes"),
    )


def system_reason(facts: CollectionFacts) -> str | None:
    if is_system_collection(facts.database, facts.name):
        return say('"{name}" belongs to the server', name=facts.name)
    return None


class MongodbRelation:
    def __init__(self, session: MongodbSession) -> None:
        self._session = session

    async def facts(self, node_id: str, *, structure: bool = True) -> CollectionFacts:
        database, collection = relation_parts(node_id)
        facts = await read_collection(self._session, database, collection, structure=structure)
        if facts is None:
            raise NodeNotFound(node_id)
        return facts

    async def relation_model(self, node_id: str) -> RelationModel:
        return model_of(node_id, await self.facts(node_id))

    async def relation_models_for_nodes(self, node_ids: list[str]) -> list[RelationModel]:
        """The collections among these ids; an id that names none is left out."""
        models: list[RelationModel] = []
        for node_id in node_ids:
            database, collection = parse(node_id)
            if collection is None:
                continue
            facts = await read_collection(self._session, database, collection)
            if facts is not None:
                models.append(model_of(node_id, facts))
        return models
