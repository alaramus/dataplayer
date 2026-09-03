"""Writing a Redis key space: the six ways in, and the three ways after.

Against a real server, for the reason the rest of these tests are: what they
are about is what the driver does to a Redis, and a fake would be this
repository's own idea of one checked against itself.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import redis.asyncio as redis
from pydantic import ValidationError

from app.adapters.actions import ActionRefused
from app.adapters.redis.actions import lines, pairs, scored
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.keyspace import database_id, folder_id, key_id
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options

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


async def _perform(
    adapter: RedisAdapter, action_name: str, node_id: str | None, **params: Any
) -> str:
    result = await adapter.action(action_name).perform(node_id, params)
    return result.message


# --- what a form is read as -------------------------------------------------


def test_a_typed_value_is_read_a_line_at_a_time() -> None:
    """Blank lines out, and nothing else touched: a value may legitimately
    start with a space."""
    assert lines("one\n\n two \n") == ["one", " two "]
    assert lines("") == []


def test_a_pair_splits_at_the_first_sign_only() -> None:
    """A value may hold `=` — a URL, a base64 blob — so only the first one
    separates."""
    assert pairs("url=https://x/?a=b") == [("url", "https://x/?a=b")]

    with pytest.raises(ValueError, match="name=value"):
        pairs("no sign at all")


def test_a_score_has_to_be_a_number() -> None:
    assert scored("ada=3\nalan=1.5") == {"ada": 3.0, "alan": 1.5}

    with pytest.raises(ValueError, match="not a score"):
        scored("ada=soon")


# --- the six ----------------------------------------------------------------


async def test_a_string_is_written_with_an_expiry_if_one_is_asked_for(
    adapter: RedisAdapter,
) -> None:
    await _perform(
        adapter, "new_string", HERE, name="cache:one", value="hello", ttl_seconds=120
    )

    client = await _client()
    try:
        assert await client.get("cache:one") == b"hello"
        assert 0 < int(await client.ttl("cache:one")) <= 120
    finally:
        await client.aclose()


async def test_every_type_redis_has_can_be_written_from_a_form(
    adapter: RedisAdapter,
) -> None:
    """The point of six actions: what this source can read, it can also write.

    Read back through the catalog rather than through the driver, because what
    is being checked is that the two agree about what was made.
    """
    await _perform(adapter, "new_string", HERE, name="a", value="hello")
    await _perform(adapter, "new_hash", HERE, name="b", value="name=Ada\nborn=1815")
    await _perform(adapter, "new_list", HERE, name="c", value="one\ntwo\nthree")
    await _perform(adapter, "new_set", HERE, name="d", value="ada\nalan\nada")
    await _perform(adapter, "new_zset", HERE, name="e", value="ada=3\nalan=1")
    await _perform(adapter, "new_stream", HERE, name="f", value="who=ada\nwhat=in")

    made = {
        node.name: node
        for node in await adapter.list_children(HERE)
        if node.kind == "key"
    }

    assert {name: node.data_type for name, node in made.items()} == {
        "a": "string",
        "b": "hash",
        "c": "list",
        "d": "set",
        "e": "zset",
        "f": "stream",
    }
    assert made["b"].length == 2
    assert made["c"].length == 3
    # A repeated member counts once, which is what a set is.
    assert made["d"].length == 2


async def test_a_sorted_set_keeps_the_scores_it_was_given(
    adapter: RedisAdapter,
) -> None:
    await _perform(adapter, "new_zset", HERE, name="board", value="ada=3\nalan=1")

    client = await _client()
    try:
        assert await client.zrange("board", 0, -1, withscores=True) == [
            (b"alan", 1.0),
            (b"ada", 3.0),
        ]
    finally:
        await client.aclose()


async def test_a_key_is_made_where_the_catalog_is_standing(
    adapter: RedisAdapter,
) -> None:
    """A folder is a place, so a name typed in one goes under it. Worked out
    on the server, which is the only party that may take an id apart (D21)."""
    result = await adapter.action("new_string").perform(
        folder_id(DB, "cache:"), {"name": "one", "value": "hello"}
    )

    assert result.message == "cache:one written"
    # And the branch that changed is named, so the tree re-reads the right one.
    assert result.reload_node_ids == [folder_id(DB, "cache:")]
    client = await _client()
    try:
        assert await client.get("cache:one") == b"hello"
    finally:
        await client.aclose()


async def test_a_key_written_in_the_database_itself_names_the_database(
    adapter: RedisAdapter,
) -> None:
    result = await adapter.action("new_string").perform(
        HERE, {"name": "plain", "value": "x"}
    )

    assert result.reload_node_ids == [HERE]


async def test_a_name_already_in_use_is_a_conflict_unless_replacing_is_asked_for(
    adapter: RedisAdapter,
) -> None:
    await _perform(adapter, "new_list", HERE, name="taken", value="one")

    with pytest.raises(ActionRefused) as refusal:
        await _perform(adapter, "new_string", HERE, name="taken", value="second")

    assert refusal.value.reason == "conflict"

    # Replacing removes what is there first, so a list may become a string.
    await _perform(
        adapter, "new_string", HERE, name="taken", value="second", overwrite=True
    )
    client = await _client()
    try:
        assert await client.get("taken") == b"second"
    finally:
        await client.aclose()


async def test_a_collection_written_with_nothing_in_it_is_refused(
    adapter: RedisAdapter,
) -> None:
    """Redis has no empty hash: a key with no fields is a key that is not
    there, so the form says so rather than reporting a write that made
    nothing."""
    for action_name in ("new_hash", "new_list", "new_set", "new_zset", "new_stream"):
        with pytest.raises(ValidationError):
            await _perform(adapter, action_name, HERE, name="empty", value="")

    # A string is the exception, because an empty string is a value.
    await _perform(adapter, "new_string", HERE, name="empty", value="")


async def test_a_line_that_is_not_a_pair_is_refused_before_anything_is_written(
    adapter: RedisAdapter,
) -> None:
    with pytest.raises(ValidationError):
        await _perform(adapter, "new_hash", HERE, name="person", value="Ada")

    assert await adapter.list_children(HERE) == []


async def test_a_name_that_could_not_be_typed_back_is_refused(
    adapter: RedisAdapter,
) -> None:
    """Redis accepts almost any bytes as a key; a form should not."""
    for written in ["with space", "new\nline", "quote'd", "*", ""]:
        with pytest.raises(ValidationError):
            await _perform(adapter, "new_string", HERE, name=written, value="x")


async def test_a_key_cannot_be_written_on_the_server_itself(
    adapter: RedisAdapter,
) -> None:
    """There is no key space outside a database to put one in."""
    with pytest.raises(ActionRefused) as refusal:
        await _perform(adapter, "new_string", None, name="stray", value="x")

    assert refusal.value.reason == "not_applicable"


# --- and what can be done to one afterwards ---------------------------------


async def test_deleting_a_key_takes_it_away_and_saying_so_twice_is_not_an_error(
    adapter: RedisAdapter,
) -> None:
    """Something with an expiry may go between the listing and the click."""
    await _perform(adapter, "new_string", HERE, name="doomed", value="x")

    first = await _perform(adapter, "delete_key", key_id(DB, "doomed"))
    second = await _perform(adapter, "delete_key", key_id(DB, "doomed"))

    assert "deleted" in first
    assert "already gone" in second


async def test_an_expiry_is_set_and_taken_off_again(adapter: RedisAdapter) -> None:
    await _perform(adapter, "new_string", HERE, name="kept", value="x")
    client = await _client()

    try:
        await _perform(adapter, "set_expiry", key_id(DB, "kept"), seconds=300)
        assert 0 < int(await client.ttl("kept")) <= 300

        await _perform(adapter, "remove_expiry", key_id(DB, "kept"))
        # -1 is what the server answers for a key that will not expire.
        assert int(await client.ttl("kept")) == -1
    finally:
        await client.aclose()


async def test_an_expiry_on_a_key_that_is_gone_is_refused(
    adapter: RedisAdapter,
) -> None:
    with pytest.raises(ActionRefused) as refusal:
        await _perform(adapter, "set_expiry", key_id(DB, "never"), seconds=60)

    assert refusal.value.reason == "conflict"


async def test_an_action_meant_for_a_key_refuses_a_folder(
    adapter: RedisAdapter,
) -> None:
    with pytest.raises(ActionRefused) as refusal:
        await _perform(adapter, "delete_key", folder_id(DB, "cache:"))

    assert refusal.value.reason == "not_applicable"


async def test_what_a_node_admits_depends_on_what_it_is(
    adapter: RedisAdapter,
) -> None:
    """A key is written into a database, and neither a key nor a server is
    one."""
    writing = {
        "new_string",
        "new_hash",
        "new_list",
        "new_set",
        "new_zset",
        "new_stream",
    }

    on_server = {action.name for action in await adapter.available(None)}
    on_database = {action.name for action in await adapter.available(HERE)}
    on_folder = {
        action.name for action in await adapter.available(folder_id(DB, "cache:"))
    }
    on_key = {action.name for action in await adapter.available(key_id(DB, "any"))}

    assert on_server == set()
    assert on_database == writing
    assert on_folder == writing
    assert on_key == {"delete_key", "set_expiry", "remove_expiry"}


async def test_a_key_written_here_appears_in_the_catalog(
    adapter: RedisAdapter,
) -> None:
    """The end of it: what an action wrote is what the next listing shows."""
    await _perform(adapter, "new_string", HERE, name="fresh:one", value="hello")

    inside_database = await adapter.list_children(HERE)
    inside_folder = await adapter.list_children(folder_id(DB, "fresh:"))

    assert [node.name for node in inside_database] == ["fresh:"]
    assert [node.name for node in inside_folder] == ["one"]
