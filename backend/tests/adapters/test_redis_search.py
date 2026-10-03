"""Keys found by name from the search field, against a real server (D202, S4).

The tree offers no search of its own (D91): what is tested here is the
capability the search asks, and that a key it finds can still be shown where
its tree puts it.
"""

import time
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import redis.asyncio as redis

from app.adapters.catalog import KeyNode
from app.adapters.redis import search as search_module
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.keyspace import RedisKeyspace, database_id, folder_id, key_id
from app.adapters.redis.search import RedisSearch
from app.adapters.redis.session import RedisSession
from app.adapters.search import (
    MatchClass,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
)
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options
from tests.utils.word_cases import CASES

DB = chosen_database()
HERE = database_id(DB)
# A database the tests never write to.
ELSEWHERE = (DB + 1) % 16


@pytest.fixture(autouse=True)
async def keyspace() -> AsyncGenerator[None]:
    async for _ in empty_keyspace():
        yield


async def _seed(*names: str) -> None:
    options = redis_options()
    client = redis.Redis(host=options.host, port=options.port, db=options.database)
    try:
        async with client.pipeline(transaction=False) as pipe:
            for name in names:
                pipe.set(name, "1")
            await pipe.execute()
    finally:
        await client.aclose()


async def _find(
    query: str, *, node_id: str | None = HERE, limit: int = 100, seconds: float = 10
) -> NodeSearchResult:
    return await RedisAdapter(redis_options()).search_nodes(
        NodeSearchRequest(query=query, node_id=node_id, limit=limit),
        SearchBounds.within(seconds),
    )


def _names(found: NodeSearchResult) -> list[str | None]:
    return [match.full_name for match in found.matches]


async def test_a_key_is_found_by_a_word_of_its_whole_name() -> None:
    await _seed("session:42:token", "user:42:profile", "cache:tokens")

    found = await _find("token")

    assert _names(found) == ["cache:tokens", "session:42:token"]
    [token] = [match for match in found.matches if match.full_name == "session:42:token"]
    # The node is the listing's, named by its last part as the tree names it.
    assert isinstance(token.node, KeyNode)
    assert token.node.id == key_id(DB, "session:42:token")
    assert token.node.name == "token"
    assert token.parent_id == folder_id(DB, "session:42:")
    assert found.complete is True


async def test_case_is_folded_here_and_never_compiled_into_a_pattern() -> None:
    """`MATCH` is case-sensitive; `[tT]` built from what was typed would be
    compiling it (D2c)."""
    await _seed("Session:42:TOKEN", "glob[x]*?")

    assert _names(await _find("token")) == ["Session:42:TOKEN"]
    assert _names(await _find("[x]*")) == ["glob[x]*?"]
    assert _names(await _find("*")) == ["glob[x]*?"]


async def test_a_key_found_among_a_thousand_is_shown_in_its_tree() -> None:
    """No node path (D195): the hit carries the levels above it, and each is a
    level the tree really lists."""
    await _seed(*(f"user:{index}:profile" for index in range(1000)), "orders:2024:eu:total")
    adapter = RedisAdapter(redis_options())

    found = await _find("total")

    [match] = found.matches
    assert match.ancestors is not None
    assert [one.name for one in match.ancestors] == [f"db{DB}", "orders:", "2024:", "eu:"]
    below = None
    for ancestor in match.ancestors:
        listed = await adapter.list_children(below)
        assert (ancestor.node_id, ancestor.name) in [(node.id, node.name) for node in listed]
        below = ancestor.node_id
    assert match.node.id in [node.id for node in await adapter.list_children(below)]


async def test_a_search_in_a_folder_stays_in_it() -> None:
    await _seed("user:1:token", "session:1:token")

    found = await _find("token", node_id=folder_id(DB, "user:"))

    assert _names(found) == ["user:1:token"]


async def test_a_key_is_not_a_level_to_search_from() -> None:
    await _seed("user:1:token")

    with pytest.raises(ValueError):
        await _find("token", node_id=key_id(DB, "user:1:token"))


async def test_the_scan_is_bounded_by_keys_looked_at_not_by_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A word nothing holds would otherwise walk the whole key space."""
    await _seed(*(f"user:{index}" for index in range(1000)))
    monkeypatch.setattr(search_module, "MAX_LOOKED_AT", 10)

    found = await _find("nothing-holds-this")

    assert found.matches == []
    assert found.complete is False
    assert found.notice is not None and "10 keys" in found.notice


async def test_a_scan_out_of_time_says_so() -> None:
    await _seed("user:1:token")

    found = await RedisAdapter(redis_options()).search_nodes(
        NodeSearchRequest(query="token", node_id=HERE),
        SearchBounds(deadline=time.monotonic() - 1),
    )

    assert found.complete is False
    assert found.notice is not None and found.notice.startswith("Time ran out")


async def test_the_best_classes_are_kept_when_more_match_than_are_wanted() -> None:
    await _seed(*(f"reorders:{index}" for index in range(30)), "orders")

    found = await _find("orders", limit=10)

    assert _names(found)[0] == "orders"
    assert len(found.matches) == 10
    assert found.complete is False


class _Watched(RedisSession):
    """Says which databases were opened."""

    def __init__(self) -> None:
        super().__init__(redis_options())
        self.opened: list[int | None] = []

    @asynccontextmanager
    async def connection(self, database: int | None = None) -> AsyncIterator[redis.Redis]:
        self.opened.append(database)
        async with super().connection(database) as client:
            yield client


async def test_an_empty_database_is_not_scanned() -> None:
    """`INFO` says which hold anything, so an empty one costs nothing."""
    await _seed("user:1:token")
    session = _Watched()
    async with session.connection() as client:
        counts = await RedisKeyspace(session).key_counts(client)

    found = await RedisSearch(session, RedisKeyspace(session)).search_nodes(
        NodeSearchRequest(query="token"), SearchBounds.within(10)
    )

    assert "user:1:token" in _names(found)
    scanned = {database for database in session.opened if database is not None}
    assert DB in scanned
    assert scanned <= set(counts)
    assert found.extent == sum(counts.values())


class _Crowded(RedisKeyspace):
    """Says another database holds millions of keys, which nobody scans here."""

    async def key_counts(self, client: Any) -> dict[int, int]:
        return {**await super().key_counts(client), ELSEWHERE: 5_000_000}


async def test_a_search_in_one_database_says_how_many_keys_the_server_holds() -> None:
    """The next search's cost is stated from it, and that one may scan them all (D200)."""
    await _seed("user:1:token")
    session = RedisSession(redis_options())

    found = await RedisSearch(session, _Crowded(session)).search_nodes(
        NodeSearchRequest(query="token", node_id=HERE), SearchBounds.within(10)
    )

    assert _names(found) == ["user:1:token"]
    assert found.extent is not None
    assert found.extent > 5_000_000


@pytest.mark.parametrize(("typed", "name", "expected"), CASES)
async def test_the_scan_agrees_with_the_word_table(
    typed: str, name: str, expected: MatchClass | None
) -> None:
    await _seed(*{name for _, name, _ in CASES})

    found = await _find(typed)

    assert (name in _names(found)) is (expected is not None)

