"""Rows kept as keys of their own, each replacing its key (D314)."""

from collections.abc import AsyncGenerator

import pytest
import redis.asyncio as redis

from app.adapters.keyed import KeyedRow, KeyedWriteRequest
from app.adapters.protocol import SupportsKeyedWrite
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.keyspace import database_id, folder_id, key_id
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options

DB = chosen_database()


@pytest.fixture(autouse=True)
async def keyspace() -> AsyncGenerator[None]:
    async for _ in empty_keyspace():
        yield


@pytest.fixture
def adapter() -> RedisAdapter:
    return RedisAdapter(redis_options())


def _client() -> redis.Redis:
    options = redis_options()
    return redis.Redis(
        host=options.host, port=options.port, db=options.database, decode_responses=True
    )


def _request(
    fields: list[str],
    rows: list[tuple[str | None, list[str | None]]],
    **choices: object,
) -> KeyedWriteRequest:
    return KeyedWriteRequest(
        place_node_id=database_id(DB),
        prefix="price:",
        fields=fields,
        rows=[KeyedRow(key=key, values=values) for key, values in rows],
        **choices,  # type: ignore[arg-type] # the test's own choices
    )


def test_a_place_gives_its_prefix_and_a_key_is_no_place(adapter: RedisAdapter) -> None:
    assert isinstance(adapter, SupportsKeyedWrite)
    assert adapter.keyed_prefix(database_id(DB)) == ""
    assert adapter.keyed_prefix(folder_id(DB, "price:")) == "price:"
    assert adapter.keyed_prefix(key_id(DB, "price:BTC")) is None
    assert adapter.keyed_prefix(None) is None


async def test_one_value_is_a_string_and_the_last_row_per_key_wins(
    adapter: RedisAdapter,
) -> None:
    written = await adapter.write_keyed(
        _request(["value"], [("BTC", ["1"]), ("ETH", ["2"]), ("BTC", ["3"])])
    )

    assert (written.written, written.without_key, written.other_type) == (2, 0, 0)
    client = _client()
    assert await client.get("price:BTC") == "3"
    assert await client.get("price:ETH") == "2"
    assert await client.ttl("price:BTC") == -1


async def test_several_values_are_a_hash_replaced_whole_with_its_time_to_live(
    adapter: RedisAdapter,
) -> None:
    client = _client()
    await client.hset("price:BTC", mapping={"price": "1", "stale": "x"})

    written = await adapter.write_keyed(
        _request(
            ["price", "side"],
            [("BTC", ["2", "buy"]), ("ETH", ["3", None])],
            ttl_seconds=60,
        )
    )

    assert written.written == 2
    # The field the row does not have is gone; an empty value is no field.
    assert await client.hgetall("price:BTC") == {"price": "2", "side": "buy"}
    assert await client.hgetall("price:ETH") == {"price": "3"}
    assert 0 < await client.ttl("price:BTC") <= 60


async def test_rows_without_a_key_or_a_value_are_skipped_and_counted(
    adapter: RedisAdapter,
) -> None:
    written = await adapter.write_keyed(
        _request(
            ["value"], [(None, ["1"]), ("", ["2"]), ("BTC", [None]), ("ETH", ["4"])]
        )
    )

    assert (written.written, written.without_key) == (1, 3)
    assert await _client().keys("price:*") == ["price:ETH"]


async def test_a_key_of_another_type_is_left_as_it_was(adapter: RedisAdapter) -> None:
    client = _client()
    await client.rpush("price:BTC", "somebody's", "list")

    written = await adapter.write_keyed(
        _request(["value"], [("BTC", ["1"]), ("ETH", ["2"])])
    )

    assert (written.written, written.other_type) == (1, 1)
    assert await client.lrange("price:BTC", 0, -1) == ["somebody's", "list"]


async def test_a_value_too_long_is_refused_by_its_key(adapter: RedisAdapter) -> None:
    with pytest.raises(ValueError, match="price:BTC"):
        await adapter.write_keyed(
            _request(["value"], [("BTC", ["x" * (64 * 1024 + 1)])])
        )
    assert await _client().exists("price:BTC") == 0
