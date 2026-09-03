"""The key space an automatic start puts into an empty Redis (D90)."""

from collections.abc import AsyncGenerator

import pytest

from app.adapters.protocol import SupportsSampleData
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.keyspace import database_id, folder_id
from app.adapters.redis.samples import key_names
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options

# Everything a sample writes lands in the database the connection names, and
# every id naming one carries that number (D91).
DB = chosen_database()
HERE = database_id(DB)


@pytest.fixture(autouse=True)
async def keyspace() -> AsyncGenerator[None]:
    async for _ in empty_keyspace():
        yield


@pytest.fixture
def adapter() -> RedisAdapter:
    return RedisAdapter(redis_options())


def test_the_type_says_it_can_be_filled() -> None:
    """Which is what puts the offer on the template (D90)."""
    assert isinstance(RedisAdapter(redis_options()), SupportsSampleData)


def test_there_is_enough_of_it_to_be_a_demonstration() -> None:
    """A dozen keys is a screenshot; a hundred is a key space to walk."""
    names = key_names()

    assert len(names) > 100
    assert len({name.split(":")[0] for name in names}) >= 8


async def test_it_writes_every_type_redis_has(adapter: RedisAdapter) -> None:
    """The point of the sample data: every branch of the reader has something
    to read, and the type column has more than one value in it."""
    said = await adapter.install_sample_data()

    assert "keys" in said
    types: set[str] = set()
    for folder in ("session:", "cache:", "queue:", "metrics:", "events:"):
        for node in await adapter.list_children(folder_id(DB, folder)):
            if node.kind == "key":
                types.add(node.data_type)
            elif node.kind == "directory":
                for inner in await adapter.list_children(node.id):
                    if inner.kind == "key":
                        types.add(inner.data_type)

    assert {"string", "hash", "list", "set", "zset", "stream"} <= types


async def test_it_leaves_some_keys_with_an_expiry_and_some_without(
    adapter: RedisAdapter,
) -> None:
    """A column where every row says the same thing says nothing."""
    await adapter.install_sample_data()

    keys = [
        node
        for node in await adapter.list_children(folder_id(DB, "rate:north:"))
        if node.kind == "key"
    ]
    forever = [
        node
        for node in await adapter.list_children(folder_id(DB, "feature:"))
        if node.kind == "key"
    ]

    assert keys and all(node.ttl_seconds is not None for node in keys)
    assert forever and all(node.ttl_seconds is None for node in forever)


async def test_running_it_twice_leaves_the_same_key_space(
    adapter: RedisAdapter,
) -> None:
    """Written out rather than generated, so a demonstration made twice is the
    same demonstration."""
    await adapter.install_sample_data()
    first = {node.id for node in await adapter.list_children(HERE)}
    await adapter.install_sample_data()
    second = {node.id for node in await adapter.list_children(HERE)}

    assert first == second
