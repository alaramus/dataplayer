"""A database of known shape on the MongoDB server the suite talks to.

Built with the driver directly rather than through the adapter, which cannot
write yet, and rebuilt by every module that asks for it.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from bson import Decimal128, Int64, ObjectId
from pydantic import TypeAdapter
from pymongo import AsyncMongoClient

from app.adapters.mongodb.adapter import MongodbAdapter
from app.adapters.mongodb.options import MongodbOptions, MongodbUserPassword
from app.adapters.mongodb.session import options_from_url
from tests.utils.services import MONGODB

DATABASE = "dp_test_mongodb"
# A collection's name may hold dots, and a node id must survive them.
DOTTED = "logs.2026.web"

PEOPLE_IDS = [ObjectId("650000000000000000000001"), ObjectId("650000000000000000000002"), ObjectId("650000000000000000000003")]
UID = uuid.UUID("12345678-1234-5678-1234-567812345678")

PEOPLE: list[dict[str, Any]] = [
    {
        "_id": PEOPLE_IDS[0],
        "name": "Ann",
        "age": 31,
        "born": datetime(1994, 3, 1, 12, 30, tzinfo=UTC),
        "tags": ["a", "b"],
        "price": Decimal128("1.10"),
        "uid": UID,
        "big": Int64(9007199254740993),
        "active": True,
    },
    {"_id": PEOPLE_IDS[1], "name": "Bob", "age": 2.5, "address": {"city": "Riga"}, "active": False},
    {"_id": PEOPLE_IDS[2], "name": "Cy", "age": None, "odd.field": 1, "$weird": 2},
]

# Enough rows that a page and an order mean something.
NUMBERS = [{"_id": index, "n": index % 7, "label": f"row {index:03d}"} for index in range(250)]

VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["title"],
        "properties": {
            "title": {"bsonType": "string"},
            "pages": {"bsonType": ["int", "null"]},
        },
    }
}


def raw_client() -> AsyncMongoClient[dict[str, Any]]:
    return AsyncMongoClient(MONGODB.require(), tz_aware=True, uuidRepresentation="standard")


def options(**changes: Any) -> MongodbUserPassword:
    chosen = TypeAdapter[MongodbOptions](MongodbOptions).validate_python(
        options_from_url(MONGODB.require())
    )
    assert isinstance(chosen, MongodbUserPassword)
    return chosen.model_copy(update=changes)


def adapter(**changes: Any) -> MongodbAdapter:
    return MongodbAdapter(options(**changes))


async def build() -> None:
    client = raw_client()
    try:
        await client.drop_database(DATABASE)
        database = client[DATABASE]
        await database["people"].insert_many(PEOPLE)
        await database["people"].create_index([("name", 1)], name="people_name", unique=True)
        await database["numbers"].insert_many(NUMBERS)
        await database.create_collection("books", validator=VALIDATOR)
        await database["books"].insert_one({"title": "Dune"})
        await database[DOTTED].insert_one({"line": "GET /"})
        await database.command(
            {"create": "adults", "viewOn": "people", "pipeline": [{"$match": {"age": {"$gte": 18}}}]}
        )
        await database.create_collection("empty")
    finally:
        await client.close()


async def tear_down() -> None:
    client = raw_client()
    try:
        await client.drop_database(DATABASE)
    finally:
        await client.close()
