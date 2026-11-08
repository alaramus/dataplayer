"""A link that reads a topic on from where it stopped, run by its pipeline (D312)."""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import psycopg
import pytest
from confluent_kafka import KafkaError, KafkaException, Producer
from httpx import AsyncClient

from app.core.db import async_session_maker
from app.jobs.models import Job
from app.main import app
from tests.adapters.kafka_fixture import (
    ORDERS,
    adapter,
    admin,
    bootstrap,
    make,
    names,
    on_server,
    remove,
)
from tests.pipelines.canvas import CONNECTORS, Canvas, card, connector, end, link
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import conninfo, run

pytestmark = pytest.mark.usefixtures("clean")

SENT = ORDERS + 1
COLUMNS = [
    {"source": "value.id", "target": "id"},
    {"source": "offset", "target": "position"},
]


@pytest.fixture
async def topic() -> AsyncIterator[str]:
    name, group = names()
    await on_server(lambda: make(name, group))
    yield name
    await on_server(lambda: remove(name, group))


@pytest.fixture
async def table(schema: str) -> str:
    await run(f"CREATE TABLE {schema}.arrived (id text, position text)")  # noqa: S608 -- the fixture's own schema
    return f"{schema}.arrived"


async def _count(table: str) -> int:
    async with await psycopg.AsyncConnection.connect(conninfo()) as conn:
        found = await (await conn.execute(f"SELECT count(*) FROM {table}")).fetchone()  # noqa: S608 -- a test's own table
        return int(found[0]) if found else 0


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


def _send(topic: str, count: int) -> None:
    producer = Producer({"bootstrap.servers": bootstrap()})
    for index in range(count):
        producer.produce(
            topic, value=json.dumps({"id": 5000 + index}), partition=index % 3
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


async def _drawn(
    client: AsyncClient, headers: dict[str, str], topic: str, table: str, **choices: Any
) -> tuple[Canvas, str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    kafka = await connector(
        client,
        headers,
        "kafka",
        {"bootstrap_servers": bootstrap(), "auth_method": "none"},
    )
    database = await connector(client, headers, "postgres", working_postgres_options())
    source = card(kafka, [(f"topic:{topic}", topic, "topic")], name="Kafka")
    target = card(database, [(table, "arrived", "table")], x=400, name="Warehouse")
    canvas = await Canvas(client, headers).make()
    drawn = link(
        source,
        f"topic:{topic}",
        target,
        table,
        "rows_since_last",
        columns=COLUMNS,
        **choices,
    )
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text
    return canvas, str(drawn["id"]), source, target, saved.json()


async def test_each_run_adds_only_what_arrived_since_the_last(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    topic: str,
    table: str,
) -> None:
    canvas, link_id, _, _, saved = await _drawn(
        client, normal_user_token_headers, topic, table
    )
    [reader] = saved["readers"]
    group = reader["name"]
    assert reader == {"link_id": link_id, "name": f"dataplayer-link-{link_id}"}
    try:
        first = await _ran(canvas, link_id)
        assert first == (
            f"{SENT} new messages added to arrived; "
            "no position was kept, so reading started from the beginning"
        )
        assert await _count(table) == SENT
        # It writes into the table and makes nothing (D178).
        [shown] = (await canvas.last())["links"]
        assert shown["made"] is None
        # The group keeps where the link stopped.
        kept = await adapter().unread(f"topic:{topic}", group, "earliest")
        assert (kept.fresh, kept.count) == (False, 0)

        await on_server(lambda: _send(topic, 3))
        assert await _ran(canvas, link_id) == "3 new messages added to arrived"
        assert await _count(table) == SENT + 3

        assert await _ran(canvas, link_id) == "Nothing new since the last run"
        assert await _count(table) == SENT + 3
    finally:
        await _forget(group)


async def test_only_new_reads_nothing_the_first_time(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    topic: str,
    table: str,
) -> None:
    canvas, link_id, _, _, saved = await _drawn(
        client, normal_user_token_headers, topic, table, start="latest"
    )
    group = saved["readers"][0]["name"]
    try:
        assert await _ran(canvas, link_id) == (
            "Nothing new since the last run; no position was kept, so reading started from the end"
        )
        await on_server(lambda: _send(topic, 2))
        assert await _ran(canvas, link_id) == "2 new messages added to arrived"
        assert await _count(table) == 2
    finally:
        await _forget(group)


async def test_a_topic_is_offered_only_the_reading_on_link_in_a_pipeline_and_not_by_paste(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    topic: str,
    table: str,
) -> None:
    headers = normal_user_token_headers
    canvas, _, source, target, _ = await _drawn(client, headers, topic, table)

    offered = await canvas.offers(end(source, f"topic:{topic}"), end(target, table))
    assert offered["rows_since_last"]["available"] is True
    assert {"rows_into_relation", "rows_new_relation", "relation_csv"}.isdisjoint(
        offered
    )

    pasted = await client.post(
        f"{CONNECTORS}/{target['connector_id']}/paste/offers",
        headers=headers,
        json={
            "source_connector_id": source["connector_id"],
            "source_node_ids": [f"topic:{topic}"],
            "mode": "copy",
            "destination_node_id": table,
            "target_node_id": table,
        },
    )
    assert pasted.status_code == 200, pasted.text
    kinds = {one["kind"] for one in pasted.json()["offers"]}
    assert "rows_since_last" not in kinds
    assert "rows_into_relation" in kinds


async def test_a_link_reading_on_is_refused_from_a_table(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    table: str,
) -> None:
    headers = normal_user_token_headers
    database = await connector(client, headers, "postgres", working_postgres_options())
    other = await connector(client, headers, "postgres", working_postgres_options())
    source = card(database, [(f"{schema}.regions", "regions", "table")], name="Sales")
    target = card(other, [(table, "arrived", "table")], x=400, name="Warehouse")
    canvas = await Canvas(client, headers).make()
    saved = await canvas.save([source, target], [])
    assert saved.status_code == 200, saved.text

    offered = await canvas.offers(end(source, f"{schema}.regions"), end(target, table))
    # PostgreSQL cannot read on, so the kind is not even asked.
    assert "rows_since_last" not in offered
    assert "rows_into_relation" in offered
