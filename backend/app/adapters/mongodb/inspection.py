"""What a MongoDB collection says about itself, and what its documents do (D284).

A collection has no columns. Its fields are read from two places: the
properties its `$jsonSchema` validator declares, then the documents at both
ends of the collection in natural order. Both ends rather than a `$sample`, so
two reads of an unchanged collection give the same columns and a filter that
named one is not refused the next time.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from app.adapters.mongodb.session import Client, MongodbSession
from app.adapters.mongodb.values import FieldSample, SampledField, schema_fields

# Documents read from each end of a collection to learn its fields.
SAMPLE_EACH_END = 100

CollectionType = Literal["collection", "view", "timeseries"]


@dataclass
class CollectionFacts:
    database: str
    name: str
    type: CollectionType
    # What listCollections says: the validator, a view's pipeline, capping.
    options: dict[str, Any]
    read_only: bool
    fields: list[SampledField] = field(default_factory=list)
    indexes: list[dict[str, Any]] = field(default_factory=list)
    row_estimate: int | None = None
    size_bytes: int | None = None

    @property
    def is_view(self) -> bool:
        return self.type == "view"

    @property
    def validator(self) -> Mapping[str, Any] | None:
        found = self.options.get("validator")
        return found if isinstance(found, Mapping) else None


def collection_type(info: Mapping[str, Any]) -> CollectionType:
    kind = info.get("type")
    if kind == "view":
        return "view"
    return "timeseries" if kind == "timeseries" else "collection"


async def collection_info(
    client: Client, database: str, name: str
) -> dict[str, Any] | None:
    cursor = await client[database].list_collections(filter={"name": name})
    found = await cursor.to_list()
    return dict(found[0]) if found else None


async def sample_fields(client: Client, facts: CollectionFacts) -> list[SampledField]:
    sample = FieldSample()
    for name, tag, required in schema_fields(facts.validator):
        sample.declare(name, tag, required)
    collection = client[facts.database][facts.name]
    if facts.type == "collection":
        sample.read(await collection.find().limit(SAMPLE_EACH_END).to_list())
        sample.read(
            await collection.find().sort("$natural", -1).limit(SAMPLE_EACH_END).to_list()
        )
    else:
        # A view and a time series are read through a pipeline, which has
        # no natural order to read the far end of.
        sample.read(await collection.find().limit(2 * SAMPLE_EACH_END).to_list())
    if not facts.is_view and "_id" not in sample.fields:
        # Every stored document has one, whatever the sample saw.
        sample.declare("_id", "objectId", True)
    return sample.ordered()


async def statistics(client: Client, database: str, name: str) -> tuple[int | None, int | None]:
    """The document count the server keeps and the bytes on disk, if it says."""
    try:
        stats = await (
            await client[database][name].aggregate(
                [{"$collStats": {"count": {}, "storageStats": {}}}]
            )
        ).to_list()
    except Exception:
        # Not every user may ask, and a time series answers in pieces.
        return None, None
    if len(stats) != 1:
        return None, None
    count = stats[0].get("count")
    size = stats[0].get("storageStats", {}).get("storageSize")
    return (
        count if isinstance(count, int) else None,
        size if isinstance(size, int) else None,
    )


async def read_collection(
    session: MongodbSession, database: str, name: str, *, structure: bool = True
) -> CollectionFacts | None:
    """One collection or view, or None when there is none of that name."""
    async with session.client() as client:
        with session.failures():
            info = await collection_info(client, database, name)
            if info is None:
                return None
            kind = collection_type(info)
            details = info.get("info")
            facts = CollectionFacts(
                database=database,
                name=name,
                type=kind,
                options=dict(info.get("options") or {}),
                read_only=bool(details.get("readOnly")) if isinstance(details, Mapping) else False,
            )
            facts.fields = await sample_fields(client, facts)
            if structure and not facts.is_view:
                cursor = await client[database][name].list_indexes()
                facts.indexes = [dict(index) for index in await cursor.to_list()]
            if structure and not facts.is_view:
                facts.row_estimate, facts.size_bytes = await statistics(client, database, name)
    return facts
