"""Walking and reading a Redis key space, against a real server.

What is written into one is next door in `test_redis_actions.py`, which
mirrors the two modules the behaviour lives in.
"""

from collections.abc import AsyncGenerator

import pytest
import redis.asyncio as redis

from app.adapters.actions import SupportsActions
from app.adapters.catalog import DatabaseNode, KeyNode
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import (
    DataAdapter,
    NodeNotFound,
    SupportsCatalog,
    SupportsFetch,
)
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.keyspace import database_id, folder_id, key_id
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options

# The database these tests connect to, which every id they write has to carry.
DB = chosen_database()
HERE = database_id(DB)


@pytest.fixture(autouse=True)
async def keyspace() -> AsyncGenerator[None]:
    async for _ in empty_keyspace():
        yield


@pytest.fixture
def adapter() -> RedisAdapter:
    return RedisAdapter(redis_options())


async def _client() -> redis.Redis:
    options = redis_options()
    return redis.Redis(host=options.host, port=options.port, db=options.database)


async def _seed(**pairs: str) -> None:
    client = await _client()
    try:
        for name, value in pairs.items():
            await client.set(name.replace("__", ":"), value)
    finally:
        await client.aclose()


# --- what the type says it can do ------------------------------------------


def test_it_now_browses_reads_and_acts() -> None:
    """Read off the driver, so the catalog cannot claim what is not there."""
    adapter = RedisAdapter(redis_options())

    assert isinstance(adapter, DataAdapter)
    assert isinstance(adapter, SupportsCatalog)
    assert isinstance(adapter, SupportsFetch)
    assert isinstance(adapter, SupportsActions)


# --- the databases ----------------------------------------------------------


async def test_the_root_is_the_databases_the_server_has(
    adapter: RedisAdapter,
) -> None:
    """A grouping and not a wall: the number in the connection says where the
    catalog opens, and the rest are beside it to switch to (D91)."""
    await _seed(greeting="hello")

    root = await adapter.list_children(None)

    assert all(isinstance(node, DatabaseNode) for node in root)
    assert len(root) >= 16
    named = [node for node in root if isinstance(node, DatabaseNode) and node.preferred]
    assert [node.id for node in named] == [HERE]
    assert next(node for node in named).keys == 1


async def test_a_database_says_how_full_it_is(adapter: RedisAdapter) -> None:
    """One `INFO` for all of them: sixteen `DBSIZE` round trips to draw one
    select is sixteen too many."""
    await _seed(one="a", two="b", three="c")

    counted = {
        node.id: node.keys
        for node in await adapter.list_children(None)
        if isinstance(node, DatabaseNode)
    }

    assert counted[HERE] == 3


async def test_a_key_belongs_to_its_database_and_says_so_in_its_id(
    adapter: RedisAdapter,
) -> None:
    """Which is the whole reason the database is part of every id: without it
    the same name in two databases would be the same string."""
    await _seed(only__here="yes")

    mine = await adapter.list_children(HERE)
    elsewhere = await adapter.list_children(database_id(0 if DB != 0 else 1))

    assert [node.id for node in mine] == [folder_id(DB, "only:")]
    assert folder_id(DB, "only:") not in [node.id for node in elsewhere]


# --- walking it -------------------------------------------------------------


async def test_a_database_groups_keys_by_the_colons_in_their_names(
    adapter: RedisAdapter,
) -> None:
    """Which is how every Redis convention names things, and how every tool
    that shows a key space shows one."""
    await _seed(
        session__42__token="a",
        session__43__token="b",
        cache__user__7="c",
        plain="d",
    )

    children = await adapter.list_children(HERE)

    assert [(node.kind, node.name) for node in children] == [
        ("directory", "cache:"),
        ("directory", "session:"),
        ("key", "plain"),
    ]


async def test_walking_into_a_folder_lists_the_next_segment(
    adapter: RedisAdapter,
) -> None:
    await _seed(session__42__token="a", session__43__token="b", session__count="7")

    children = await adapter.list_children(folder_id(DB, "session:"))

    assert [(node.kind, node.name) for node in children] == [
        ("directory", "42:"),
        ("directory", "43:"),
        ("key", "count"),
    ]


async def test_a_key_says_its_type_its_size_and_its_expiry(
    adapter: RedisAdapter,
) -> None:
    client = await _client()
    try:
        await client.set("greeting", "hello")
        await client.expire("greeting", 600)
        await client.hset("person", mapping={"name": "Ada", "born": "1815"})
        await client.rpush("queue", "one", "two", "three")
    finally:
        await client.aclose()

    children = await adapter.list_children(HERE)
    by_name = {node.name: node for node in children}

    greeting = by_name["greeting"]
    assert isinstance(greeting, KeyNode)
    assert greeting.data_type == "string"
    assert greeting.length == 5
    assert greeting.ttl_seconds is not None
    assert 0 < greeting.ttl_seconds <= 600

    person = by_name["person"]
    assert isinstance(person, KeyNode)
    assert person.data_type == "hash"
    assert person.length == 2
    # No expiry is nothing, never the -1 the server answers with: a screen
    # showing "-1 seconds" is a screen repeating a protocol detail.
    assert person.ttl_seconds is None

    queue = by_name["queue"]
    assert isinstance(queue, KeyNode)
    assert queue.data_type == "list"
    assert queue.length == 3


async def test_a_key_has_no_children_even_when_a_folder_shares_its_name(
    adapter: RedisAdapter,
) -> None:
    """`user` the key and `user:` the folder are different things, which is
    the whole reason the kinds of id are marked apart."""
    await _seed(user="one", user__1="two")

    assert await adapter.list_children(key_id(DB, "user")) == []
    under = await adapter.list_children(folder_id(DB, "user:"))
    assert [node.name for node in under] == ["1"]


# --- reading it -------------------------------------------------------------


async def test_a_string_key_reads_as_one_value(adapter: RedisAdapter) -> None:
    await _seed(greeting="hello")

    page = await adapter.fetch(FetchRequest(node_id=key_id(DB, "greeting")))

    assert [column.name for column in page.columns] == ["value"]
    assert page.rows == [["hello"]]


async def test_a_hash_reads_as_fields_and_values(adapter: RedisAdapter) -> None:
    client = await _client()
    try:
        await client.hset("person", mapping={"name": "Ada", "born": "1815"})
    finally:
        await client.aclose()

    page = await adapter.fetch(FetchRequest(node_id=key_id(DB, "person")))

    assert [column.name for column in page.columns] == ["field", "value"]
    assert page.rows == [["born", "1815"], ["name", "Ada"]]


async def test_a_list_reads_in_its_own_order_and_pages(
    adapter: RedisAdapter,
) -> None:
    client = await _client()
    try:
        await client.rpush("queue", *[str(number) for number in range(10)])
    finally:
        await client.aclose()

    first = await adapter.fetch(FetchRequest(node_id=key_id(DB, "queue"), limit=4))
    second = await adapter.fetch(
        FetchRequest(node_id=key_id(DB, "queue"), limit=4, offset=4)
    )

    assert [row[1] for row in first.rows] == ["0", "1", "2", "3"]
    assert first.has_more is True
    assert [row[0] for row in second.rows] == ["4", "5", "6", "7"]


async def test_a_sorted_set_reads_with_its_scores(adapter: RedisAdapter) -> None:
    client = await _client()
    try:
        await client.zadd("board", {"ada": 3, "alan": 1})
    finally:
        await client.aclose()

    page = await adapter.fetch(FetchRequest(node_id=key_id(DB, "board")))

    assert [column.name for column in page.columns] == ["member", "score"]
    assert [row[0] for row in page.rows] == ["alan", "ada"]


async def test_a_folder_reads_as_the_keys_under_it(adapter: RedisAdapter) -> None:
    """The listing a person wants when they are looking for a key rather than
    at one."""
    await _seed(cache__a="1", cache__b="2")

    page = await adapter.fetch(FetchRequest(node_id=folder_id(DB, "cache:")))

    assert [column.name for column in page.columns] == ["key", "type", "ttl", "size"]
    assert [row[0] for row in page.rows] == ["cache:a", "cache:b"]
    assert [row[1] for row in page.rows] == ["string", "string"]


async def test_nothing_can_be_sorted_or_filtered(adapter: RedisAdapter) -> None:
    """Redis has no index over values, so offering either would be offering to
    read everything and do it here."""
    await _seed(cache__a="1")

    page = await adapter.fetch(FetchRequest(node_id=folder_id(DB, "cache:")))

    assert all(column.sortable is False for column in page.columns)
    assert all(column.filter_operators == [] for column in page.columns)


async def test_a_key_that_is_gone_is_not_found(adapter: RedisAdapter) -> None:
    with pytest.raises(NodeNotFound):
        await adapter.fetch(FetchRequest(node_id=key_id(DB, "never")))


async def test_the_server_itself_is_not_a_page_of_rows(
    adapter: RedisAdapter,
) -> None:
    """What is at the root is the list of databases, and a list of databases is
    a catalog level rather than something to read."""
    with pytest.raises(NodeNotFound):
        await adapter.fetch(FetchRequest(node_id=None))


@pytest.mark.parametrize(
    "written",
    ["k:greeting", "f:cache:", "d", "kx:one", "postgres.public", ""],
)
async def test_a_string_this_source_did_not_issue_is_not_a_node(
    adapter: RedisAdapter, written: str
) -> None:
    """Including the ids of the version before databases were in them: a string
    that is nearly one of ours is refused rather than nearly understood, and
    the refusal is the one a client can act on."""
    with pytest.raises(NodeNotFound):
        await adapter.fetch(FetchRequest(node_id=written))

    with pytest.raises(NodeNotFound):
        await adapter.list_children(written)
