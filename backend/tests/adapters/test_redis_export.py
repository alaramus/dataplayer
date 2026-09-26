"""Every row of a Redis node, in bounded batches (D44, D171)."""

from collections.abc import AsyncGenerator

import pytest
import redis.asyncio as redis

from app.adapters.declared_tables import DeclaredTable
from app.adapters.export import EXPORT_BATCH_SIZE, ExportRequest
from app.adapters.fetch import ScalarFilter, Sort
from app.adapters.protocol import NodeNotFound
from app.adapters.redis import export as redis_export
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.keyspace import database_id, folder_id, key_id, table_id
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options

DB = chosen_database()


@pytest.fixture(autouse=True)
async def keyspace() -> AsyncGenerator[None]:
    async for _ in empty_keyspace():
        yield


async def _client() -> redis.Redis:
    options = redis_options()
    return redis.Redis(host=options.host, port=options.port, db=options.database)


async def _batches(
    adapter: RedisAdapter, node_id: str, columns: list[str]
) -> list[list[list[str | None]]]:
    return [
        batch.rows
        async for batch in adapter.export_rows(ExportRequest(node_id=node_id, columns=columns))
    ]


def _all(batches: list[list[list[str | None]]]) -> list[list[str | None]]:
    return [row for batch in batches for row in batch]


async def test_each_type_is_written_with_the_grids_columns() -> None:
    client = await _client()
    try:
        await client.set("greeting", "x" * 70_000)
        await client.hset("profile", mapping={"name": "Ada", "age": "36"})
        await client.rpush("queue", "a", "b", "c")
        await client.sadd("tags", "red", "blue")
        await client.zadd("scores", {"ada": 3.0, "grace": 1.5})
        first = await client.xadd("events", {"kind": "login", "who": "ada"})
    finally:
        await client.aclose()
    adapter = RedisAdapter(redis_options())

    # Whole, not cut where the viewer cuts it.
    assert _all(await _batches(adapter, key_id(DB, "greeting"), ["value"])) == [["x" * 70_000]]
    assert sorted(_all(await _batches(adapter, key_id(DB, "profile"), ["field", "value"]))) == [
        ["age", "36"], ["name", "Ada"],
    ]
    assert _all(await _batches(adapter, key_id(DB, "queue"), ["index", "value"])) == [
        ["0", "a"], ["1", "b"], ["2", "c"],
    ]
    assert sorted(_all(await _batches(adapter, key_id(DB, "tags"), ["member"]))) == [
        ["blue"], ["red"],
    ]
    assert _all(await _batches(adapter, key_id(DB, "scores"), ["member", "score"])) == [
        ["grace", "1.5"], ["ada", "3.0"],
    ]
    assert _all(await _batches(adapter, key_id(DB, "events"), ["id", "fields"])) == [
        [first.decode(), "kind=login, who=ada"],
    ]


async def test_the_columns_asked_for_are_written_in_their_order() -> None:
    client = await _client()
    try:
        await client.zadd("scores", {"ada": 3.0})
    finally:
        await client.aclose()
    adapter = RedisAdapter(redis_options())

    assert _all(await _batches(adapter, key_id(DB, "scores"), ["score", "member"])) == [
        ["3.0", "ada"],
    ]
    with pytest.raises(ValueError, match="Unknown column: value"):
        await _batches(adapter, key_id(DB, "scores"), ["value"])
    with pytest.raises(ValueError, match="cannot be filtered or sorted"):
        [
            batch
            async for batch in adapter.export_rows(
                ExportRequest(
                    node_id=key_id(DB, "scores"),
                    columns=["member"],
                    sort=[Sort(column="member", direction="asc")],
                )
            )
        ]
    with pytest.raises(ValueError, match="cannot be filtered or sorted"):
        [
            batch
            async for batch in adapter.export_rows(
                ExportRequest(
                    node_id=key_id(DB, "scores"),
                    columns=["member"],
                    filters=[ScalarFilter(column="member", op="eq", value="ada")],
                )
            )
        ]


async def test_a_large_key_is_read_in_several_batches_never_whole() -> None:
    """Every type that can grow is read a batch at a time."""
    count = EXPORT_BATCH_SIZE * 2 + 7
    client = await _client()
    try:
        await client.hset("big:hash", mapping={f"f{n}": str(n) for n in range(count)})
        await client.rpush("big:list", *[str(n) for n in range(count)])
        await client.sadd("big:set", *[str(n) for n in range(count)])
        await client.zadd("big:zset", {str(n): n for n in range(count)})
        for n in range(count):
            await client.xadd("big:stream", {"n": str(n)})
    finally:
        await client.aclose()
    adapter = RedisAdapter(redis_options())

    for name, columns in (
        ("big:hash", ["field", "value"]),
        ("big:list", ["index", "value"]),
        ("big:set", ["member"]),
        ("big:zset", ["member", "score"]),
        ("big:stream", ["id", "fields"]),
    ):
        batches = await _batches(adapter, key_id(DB, name), columns)
        rows = _all(batches)
        assert len(batches) >= 3, name
        assert all(len(batch) <= EXPORT_BATCH_SIZE for batch in batches), name
        # A scan may repeat an element while a key changes; this one does not.
        assert len({tuple(row) for row in rows}) == count, name

    stream = _all(await _batches(adapter, key_id(DB, "big:stream"), ["fields"]))
    assert stream[0] == ["n=0"] and stream[-1] == [f"n={count - 1}"]


async def test_a_folder_is_its_list_of_keys_up_to_the_catalogs_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = await _client()
    try:
        await client.set("user:1", "a")
        await client.hset("user:2", mapping={"f": "v"})
        await client.set("user:1:below", "b")
    finally:
        await client.aclose()
    adapter = RedisAdapter(redis_options())

    rows = _all(await _batches(adapter, folder_id(DB, "user:"), ["key", "type", "ttl", "size"]))
    whole = _all(await _batches(adapter, database_id(DB), ["key"]))

    assert rows == [["user:1", "string", None, "1"], ["user:2", "hash", None, "1"]]
    assert whole == []

    monkeypatch.setattr(redis_export, "SCAN_CEILING", 2)
    with pytest.raises(ValueError, match="more keys than can be listed"):
        await _batches(adapter, folder_id(DB, "user:"), ["key"])


async def test_a_table_is_scanned_without_a_ceiling() -> None:
    count = EXPORT_BATCH_SIZE + 20
    client = await _client()
    try:
        for n in range(count):
            await client.hset(f"user:{n}", mapping={"name": f"n{n}"})
        await client.set("user:count", str(count))
    finally:
        await client.aclose()
    table = DeclaredTable.model_validate(
        {"place_id": folder_id(DB, "user:"), "name": "users", "columns": [{"name": "name"}]}
    )
    adapter = RedisAdapter(redis_options(), [table])

    rows = _all(await _batches(adapter, table_id(DB, "user:"), ["key", "name"]))

    assert len(rows) == count
    assert sorted(rows)[0] == ["0", "n0"]
    assert ["count", None] not in rows


async def test_a_table_filtered_to_one_key_exports_that_row() -> None:
    client = await _client()
    try:
        await client.hset("user:1", mapping={"name": "Ada"})
        await client.hset("user:2", mapping={"name": "Grace"})
    finally:
        await client.aclose()
    table = DeclaredTable.model_validate(
        {"place_id": folder_id(DB, "user:"), "name": "users", "columns": [{"name": "name"}]}
    )
    adapter = RedisAdapter(redis_options(), [table])

    def by_key(value: str, column: str = "key") -> ExportRequest:
        return ExportRequest(
            node_id=table_id(DB, "user:"),
            columns=["key", "name"],
            filters=[ScalarFilter(column=column, op="eq", value=value)],
        )

    one = [batch.rows async for batch in adapter.export_rows(by_key("2"))]
    none = [batch.rows async for batch in adapter.export_rows(by_key("9"))]

    assert one == [[["2", "Grace"]]]
    assert none == []
    with pytest.raises(ValueError, match="filtered only by key"):
        [batch async for batch in adapter.export_rows(by_key("Ada", "name"))]


async def test_what_is_not_there_is_not_exported() -> None:
    adapter = RedisAdapter(redis_options())

    for missing in (key_id(DB, "gone"), table_id(DB, "user:"), folder_id(DB, "user")):
        with pytest.raises(NodeNotFound):
            await _batches(adapter, missing, ["key"])
