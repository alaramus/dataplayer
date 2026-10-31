"""Something worth looking at, put into an empty MongoDB server (D294).

A server this application started for somebody is empty, and an empty server
demonstrates nothing. The lab the other servers' samples describe is told in
what MongoDB has: customers with embedded addresses and a `$jsonSchema`
validator, products with tags, orders holding their lines as an array and a
customer's id, page views as a time series, a view adding orders up, unique,
compound, text and hashed indexes, and fields that some documents lack. It
lives in a database of its own, `demo_lab`, which is dropped first.

Made here rather than read from a script: documents are values, and a script
of them would be JSON this file writes anyway. The numbers are drawn from a
seeded generator, so every lab is the same lab.
"""

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from bson import Decimal128, ObjectId

from app.adapters.mongodb.session import MongodbSession
from app.core.translation import say

SAMPLE_DATABASE = "demo_lab"

CUSTOMERS = 200
PRODUCTS = 60
ORDERS = 2_000
PAGE_VIEWS = 20_000

_CITIES = ("Riga", "Oslo", "Lisbon", "Kraków", "Tallinn", "Valencia", "Ghent", "Turku")
_WORDS = ("lamp", "desk", "chair", "shelf", "rug", "mirror", "clock", "vase", "stool", "bench")
_ADJECTIVES = ("oak", "steel", "linen", "glass", "walnut", "brass", "wool", "stone")
_PATHS = ("/", "/catalog", "/cart", "/checkout", "/account", "/search", "/help")
_START = datetime(2026, 1, 1, tzinfo=UTC)

_CUSTOMER_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["name", "email", "joined"],
        "properties": {
            "name": {"bsonType": "string"},
            "email": {"bsonType": "string"},
            "joined": {"bsonType": "date"},
            "address": {"bsonType": "object"},
            "vip": {"bsonType": "bool"},
        },
    }
}


def _customers(chance: random.Random) -> list[dict[str, Any]]:
    customers = []
    for number in range(1, CUSTOMERS + 1):
        customer: dict[str, Any] = {
            "_id": ObjectId.from_datetime(_START + timedelta(hours=number)),
            "name": f"Customer {number:03d}",
            "email": f"customer{number:03d}@example.com",
            "joined": _START + timedelta(days=chance.randrange(300)),
            "address": {"city": chance.choice(_CITIES), "street": f"{chance.randrange(1, 120)} Main St"},
        }
        # Not every document has every field: the grid shows them empty.
        if number % 7 == 0:
            customer["vip"] = True
        if number % 11 == 0:
            customer["phone"] = f"+371 2{number:07d}"
        customers.append(customer)
    return customers


def _products(chance: random.Random) -> list[dict[str, Any]]:
    return [
        {
            "_id": f"P{number:04d}",
            "title": f"{chance.choice(_ADJECTIVES)} {chance.choice(_WORDS)}",
            "price": Decimal128(Decimal(chance.randrange(500, 50_000)) / 100),
            "tags": chance.sample(_ADJECTIVES, k=2),
            "stock": chance.randrange(0, 80),
        }
        for number in range(1, PRODUCTS + 1)
    ]


def _orders(
    chance: random.Random, customers: list[dict[str, Any]], products: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    orders = []
    for number in range(1, ORDERS + 1):
        lines = [
            {
                "product": product["_id"],
                "quantity": chance.randrange(1, 5),
                "price": product["price"],
            }
            for product in chance.sample(products, k=chance.randrange(1, 5))
        ]
        orders.append(
            {
                "number": number,
                "customer": chance.choice(customers)["_id"],
                "placed": _START + timedelta(minutes=chance.randrange(0, 400_000)),
                "status": chance.choice(("new", "paid", "paid", "shipped", "shipped", "returned")),
                "lines": lines,
            }
        )
    return orders


def _page_views(chance: random.Random) -> list[dict[str, Any]]:
    return [
        {
            "at": _START + timedelta(seconds=chance.randrange(0, 90 * 86_400)),
            "page": {"path": chance.choice(_PATHS), "city": chance.choice(_CITIES)},
            "milliseconds": chance.randrange(20, 2_000),
        }
        for _ in range(PAGE_VIEWS)
    ]


class MongodbSamples:
    def __init__(self, session: MongodbSession) -> None:
        self._session = session

    async def install_sample_data(self) -> str:
        """Make the lab, and say what is now there."""
        chance = random.Random(2026)
        customers = _customers(chance)
        products = _products(chance)
        orders = _orders(chance, customers, products)
        views = _page_views(chance)
        async with self._session.client() as client:
            with self._session.failures():
                await client.drop_database(SAMPLE_DATABASE)
                lab = client[SAMPLE_DATABASE]
                await lab.create_collection("customers", validator=_CUSTOMER_SCHEMA)
                await lab["customers"].insert_many(customers)
                await lab["customers"].create_index("email", unique=True)
                await lab["products"].insert_many(products)
                await lab["products"].create_index([("title", "text")])
                await lab["orders"].insert_many(orders)
                await lab["orders"].create_index([("customer", 1), ("placed", -1)])
                await lab["orders"].create_index([("number", 1)], unique=True)
                await lab["orders"].create_index([("status", "hashed")])
                await lab.create_collection(
                    "page_views", timeseries={"timeField": "at", "metaField": "page", "granularity": "minutes"}
                )
                await lab["page_views"].insert_many(views)
                await lab.command(
                    {
                        "create": "order_totals",
                        "viewOn": "orders",
                        "pipeline": [
                            {"$unwind": "$lines"},
                            {
                                "$group": {
                                    "_id": "$customer",
                                    "orders": {"$addToSet": "$number"},
                                    "spent": {
                                        "$sum": {"$multiply": ["$lines.quantity", "$lines.price"]}
                                    },
                                }
                            },
                            {"$project": {"orders": {"$size": "$orders"}, "spent": 1}},
                        ],
                    }
                )
                cursor = await lab.list_collections()
                collections = sum(
                    1 for info in await cursor.to_list() if not str(info["name"]).startswith("system.")
                )
        return say("{schema}: {tables} collections", schema=SAMPLE_DATABASE, tables=collections)
