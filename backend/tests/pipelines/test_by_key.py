"""A link keeping the latest per key in Redis, run by its pipeline (D314)."""

import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import pytest
import redis.asyncio as redis
from confluent_kafka import KafkaError, KafkaException, Producer
from httpx import AsyncClient

from app.adapters.redis.keyspace import database_id, folder_id
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.main import app
from tests.adapters.kafka_fixture import (
    ORDERS,
    PARTITIONS,
    admin,
    bootstrap,
    make,
    names,
    on_server,
    remove,
)
from tests.pipelines.canvas import Canvas, card, connector, end, link
from tests.utils.database import working_postgres_options
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options

pytestmark = pytest.mark.usefixtures("clean")

DB = chosen_database()
# The fixture's orders are keyed k0 to k6, round the partitions in turn; its
# last message has a key that is not text.
KEYS = 7


@pytest.fixture
async def keyspace() -> AsyncGenerator[None]:
    async for _ in empty_keyspace():
        yield


@pytest.fixture
async def topic() -> AsyncIterator[str]:
    name, group = names()
    await on_server(lambda: make(name, group))
    yield name
    await on_server(lambda: remove(name, group))


def _client() -> redis.Redis:
    options = redis_options()
    return redis.Redis(
        host=options.host, port=options.port, db=options.database, decode_responses=True
    )


async def _redis(client: AsyncClient, headers: dict[str, str]) -> str:
    return await connector(
        client, headers, "redis", redis_options().model_dump(mode="json")
    )


async def _ran(canvas: Canvas, link_id: str) -> str | None:
    started = await canvas.run()
    assert started.status_code == 200, started.text
    job_id = uuid.UUID(started.json()["job_id"])
    await app.state.job_runner.wait_for(job_id)
    async with async_session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.state == "succeeded", job.message
    return (await canvas.outcomes())[link_id][1]


def _send(topic: str, prices: dict[str, float]) -> None:
    producer = Producer({"bootstrap.servers": bootstrap()})
    for key, price in prices.items():
        # Keyed by hand to the partition the fixture gave the key.
        partition = int(key[1:]) % PARTITIONS
        producer.produce(
            topic, key=key, value=json.dumps({"price": price}), partition=partition
        )
    producer.flush(10)


async def _forget(group: str) -> None:
    def drop() -> None:
        client = admin()
        for future in client.delete_consumer_groups([group]).values():
            try:
                future.result()
            except KafkaException as failure:
                if failure.args[0].code() != KafkaError.GROUP_ID_NOT_FOUND:
                    raise

    await on_server(drop)


def _keyed(
    source: dict[str, Any],
    node: str,
    target: dict[str, Any],
    place: str,
    **choices: Any,
) -> dict[str, Any]:
    return link(source, node, target, place, "rows_by_key", **choices)


@pytest.mark.usefixtures("keyspace")
async def test_a_topic_keeps_the_latest_value_of_each_key_and_reads_only_what_is_new(
    client: AsyncClient, normal_user_token_headers: dict[str, str], topic: str
) -> None:
    headers = normal_user_token_headers
    kafka = await connector(
        client,
        headers,
        "kafka",
        {"bootstrap_servers": bootstrap(), "auth_method": "none"},
    )
    cache = await _redis(client, headers)
    source = card(kafka, [(f"topic:{topic}", topic, "topic")], name="Kafka")
    target = card(cache, [(database_id(DB), "db", "database")], x=400, name="Cache")
    canvas = await Canvas(client, headers).make()
    drawn = _keyed(
        source,
        f"topic:{topic}",
        target,
        database_id(DB),
        by_key={"key_column": "key", "prefix": "order:", "ttl_seconds": 600},
        columns=[
            {"source": "value.id", "target": "id"},
            {"source": "value.price", "target": "price"},
        ],
    )
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text
    group = saved.json()["readers"][0]["name"]
    offered = await canvas.offers(
        end(source, f"topic:{topic}"), end(target, database_id(DB))
    )
    assert offered["rows_by_key"]["available"] is True
    assert offered["rows_by_key"]["reads_on"] is True
    try:
        first = await _ran(canvas, str(drawn["id"]))
        # Seven keys of orders; the last message is not JSON, so it has no
        # fields to hold and is skipped, counted.
        assert first == (
            f"{ORDERS + 1} rows: {KEYS} keys written under order:; "
            "1 rows without a key or a value skipped; "
            "no position was kept, so reading started from the beginning"
        )
        cache_client = _client()
        # The fixture puts one key in every partition, which a producer
        # keying by partitioner never does; which of them wins is then the
        # partition order (D314's deviation), so only the key is checked.
        held = await cache_client.hgetall("order:k6")
        assert int(held["id"]) % KEYS == 6
        assert held["price"] == str(int(held["id"]) * 1.5)
        assert 0 < await cache_client.ttl("order:k6") <= 600

        await on_server(lambda: _send(topic, {"k6": 99.5}))
        assert (
            await _ran(canvas, str(drawn["id"]))
            == "1 rows: 1 keys written under order:"
        )
        assert await cache_client.hgetall("order:k6") == {"price": "99.5"}
    finally:
        await _forget(group)


@pytest.mark.usefixtures("keyspace")
async def test_a_table_is_read_whole_into_keys_at_every_run(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    headers = normal_user_token_headers
    database = await connector(client, headers, "postgres", working_postgres_options())
    cache = await _redis(client, headers)
    source = card(database, [(f"{schema}.regions", "regions", "table")], name="Sales")
    target = card(
        cache, [(folder_id(DB, "region:"), "region:", "directory")], x=400, name="Cache"
    )
    canvas = await Canvas(client, headers).make()
    drawn = _keyed(
        source,
        f"{schema}.regions",
        target,
        folder_id(DB, "region:"),
        by_key={"key_column": "id", "prefix": "region:"},
        columns=[{"source": "code", "target": "code"}],
    )
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text
    offered = await canvas.offers(
        end(source, f"{schema}.regions"), end(target, folder_id(DB, "region:"))
    )
    assert offered["rows_by_key"]["suggested_name"] == "region:"
    assert offered["rows_by_key"]["reads_on"] is False

    assert (
        await _ran(canvas, str(drawn["id"])) == "2 rows: 2 keys written under region:"
    )
    assert await _client().get("region:1") == "EU"
    # Read whole again: the same keys, written again, nothing more.
    assert (
        await _ran(canvas, str(drawn["id"])) == "2 rows: 2 keys written under region:"
    )
    assert sorted(await _client().keys("region:*")) == ["region:1", "region:2"]


async def test_a_link_to_a_key_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    headers = normal_user_token_headers
    database = await connector(client, headers, "postgres", working_postgres_options())
    cache = await _redis(client, headers)
    source = card(database, [(f"{schema}.regions", "regions", "table")], name="Sales")
    key = f"k{DB}:region:1"
    target = card(cache, [(key, "region:1", "key")], x=400, name="Cache")
    canvas = await Canvas(client, headers).make()
    saved = await canvas.save([source, target], [])
    assert saved.status_code == 200, saved.text

    offered = await canvas.offers(end(source, f"{schema}.regions"), end(target, key))
    assert offered["rows_by_key"]["available"] is False
    assert offered["rows_by_key"]["reason"] == "Draw it to a database or a folder"
