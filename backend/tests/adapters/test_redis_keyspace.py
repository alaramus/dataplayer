"""Walking, reading and writing a Redis key space, against a real server."""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import redis.asyncio as redis

from app.adapters.actions import ActionRefused, SupportsActions
from app.adapters.catalog import KeyNode
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import (
    DataAdapter,
    NodeNotFound,
    SupportsCatalog,
    SupportsFetch,
)
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.keyspace import folder_id, key_id
from tests.utils.keyspace import empty_keyspace, redis_options


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


# --- walking it -------------------------------------------------------------


async def test_the_root_groups_keys_by_the_colons_in_their_names(
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

    children = await adapter.list_children(None)

    assert [(node.kind, node.name) for node in children] == [
        ("directory", "cache:"),
        ("directory", "session:"),
        ("key", "plain"),
    ]


async def test_walking_into_a_folder_lists_the_next_segment(
    adapter: RedisAdapter,
) -> None:
    await _seed(session__42__token="a", session__43__token="b", session__count="7")

    children = await adapter.list_children(folder_id("session:"))

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

    children = await adapter.list_children(None)
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
    the whole reason the two kinds of id are marked apart."""
    await _seed(user="one", user__1="two")

    assert await adapter.list_children(key_id("user")) == []
    under = await adapter.list_children(folder_id("user:"))
    assert [node.name for node in under] == ["1"]


# --- reading it -------------------------------------------------------------


async def test_a_string_key_reads_as_one_value(adapter: RedisAdapter) -> None:
    await _seed(greeting="hello")

    page = await adapter.fetch(FetchRequest(node_id=key_id("greeting")))

    assert [column.name for column in page.columns] == ["value"]
    assert page.rows == [["hello"]]


async def test_a_hash_reads_as_fields_and_values(adapter: RedisAdapter) -> None:
    client = await _client()
    try:
        await client.hset("person", mapping={"name": "Ada", "born": "1815"})
    finally:
        await client.aclose()

    page = await adapter.fetch(FetchRequest(node_id=key_id("person")))

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

    first = await adapter.fetch(FetchRequest(node_id=key_id("queue"), limit=4))
    second = await adapter.fetch(
        FetchRequest(node_id=key_id("queue"), limit=4, offset=4)
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

    page = await adapter.fetch(FetchRequest(node_id=key_id("board")))

    assert [column.name for column in page.columns] == ["member", "score"]
    assert [row[0] for row in page.rows] == ["alan", "ada"]


async def test_a_folder_reads_as_the_keys_under_it(adapter: RedisAdapter) -> None:
    """The listing a person wants when they are looking for a key rather than
    at one."""
    await _seed(cache__a="1", cache__b="2")

    page = await adapter.fetch(FetchRequest(node_id=folder_id("cache:")))

    assert [column.name for column in page.columns] == ["key", "type", "ttl", "size"]
    assert [row[0] for row in page.rows] == ["cache:a", "cache:b"]
    assert [row[1] for row in page.rows] == ["string", "string"]


async def test_nothing_can_be_sorted_or_filtered(adapter: RedisAdapter) -> None:
    """Redis has no index over values, so offering either would be offering to
    read everything and do it here."""
    await _seed(cache__a="1")

    page = await adapter.fetch(FetchRequest(node_id=folder_id("cache:")))

    assert all(column.sortable is False for column in page.columns)
    assert all(column.filter_operators == [] for column in page.columns)


async def test_a_key_that_is_gone_is_not_found(adapter: RedisAdapter) -> None:
    with pytest.raises(NodeNotFound):
        await adapter.fetch(FetchRequest(node_id=key_id("never")))


# --- writing it -------------------------------------------------------------


async def _perform(
    adapter: RedisAdapter, action_name: str, node_id: str | None, **params: Any
) -> str:
    result = await adapter.action(action_name).perform(node_id, params)
    return result.message


async def test_a_key_is_written_with_an_expiry_if_one_is_asked_for(
    adapter: RedisAdapter,
) -> None:
    await _perform(
        adapter, "new_key", None, name="cache:one", value="hello", ttl_seconds=120
    )

    client = await _client()
    try:
        assert await client.get("cache:one") == b"hello"
        assert 0 < int(await client.ttl("cache:one")) <= 120
    finally:
        await client.aclose()


async def test_a_name_already_in_use_is_a_conflict_unless_replacing_is_asked_for(
    adapter: RedisAdapter,
) -> None:
    await _seed(taken="first")

    with pytest.raises(ActionRefused) as refusal:
        await _perform(adapter, "new_key", None, name="taken", value="second")

    assert refusal.value.reason == "conflict"

    await _perform(
        adapter, "new_key", None, name="taken", value="second", overwrite=True
    )
    client = await _client()
    try:
        assert await client.get("taken") == b"second"
    finally:
        await client.aclose()


async def test_a_name_that_could_not_be_typed_back_is_refused(
    adapter: RedisAdapter,
) -> None:
    """Redis accepts almost any bytes as a key; a form should not."""
    for written in ["with space", "new\nline", "quote'd", "*", ""]:
        with pytest.raises(Exception) as failure:
            await _perform(adapter, "new_key", None, name=written, value="x")
        assert failure.type is not AssertionError, written


async def test_deleting_a_key_takes_it_away_and_saying_so_twice_is_not_an_error(
    adapter: RedisAdapter,
) -> None:
    """Something with an expiry may go between the listing and the click."""
    await _seed(doomed="x")

    first = await _perform(adapter, "delete_key", key_id("doomed"))
    second = await _perform(adapter, "delete_key", key_id("doomed"))

    assert "deleted" in first
    assert "already gone" in second


async def test_an_expiry_is_set_and_taken_off_again(adapter: RedisAdapter) -> None:
    await _seed(kept="x")
    client = await _client()

    try:
        await _perform(adapter, "set_expiry", key_id("kept"), seconds=300)
        assert 0 < int(await client.ttl("kept")) <= 300

        await _perform(adapter, "remove_expiry", key_id("kept"))
        # -1 is what the server answers for a key that will not expire.
        assert int(await client.ttl("kept")) == -1
    finally:
        await client.aclose()


async def test_an_expiry_on_a_key_that_is_gone_is_refused(
    adapter: RedisAdapter,
) -> None:
    with pytest.raises(ActionRefused) as refusal:
        await _perform(adapter, "set_expiry", key_id("never"), seconds=60)

    assert refusal.value.reason == "conflict"


async def test_an_action_meant_for_a_key_refuses_a_folder(
    adapter: RedisAdapter,
) -> None:
    with pytest.raises(ActionRefused) as refusal:
        await _perform(adapter, "delete_key", folder_id("cache:"))

    assert refusal.value.reason == "not_applicable"


async def test_what_a_node_admits_depends_on_what_it_is(
    adapter: RedisAdapter,
) -> None:
    """A key is written into a place, and a key is not a place."""
    on_root = {action.name for action in await adapter.available(None)}
    on_key = {action.name for action in await adapter.available(key_id("anything"))}

    assert on_root == {"new_key"}
    assert on_key == {"delete_key", "set_expiry", "remove_expiry"}


async def test_a_key_written_here_appears_in_the_catalog(
    adapter: RedisAdapter,
) -> None:
    """The end of it: what an action wrote is what the next listing shows."""
    await _perform(adapter, "new_key", None, name="fresh:one", value="hello")

    root = await adapter.list_children(None)
    inside = await adapter.list_children(folder_id("fresh:"))

    assert [node.name for node in root] == ["fresh:"]
    assert [node.name for node in inside] == ["one"]
