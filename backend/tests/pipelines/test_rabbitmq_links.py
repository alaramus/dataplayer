"""RabbitMQ in pipelines: a stream and a queue read on, a queue and an
exchange taking rows (D335, D336)."""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import aio_pika
import psycopg
import pytest
from httpx import AsyncClient

from app.adapters.fetch import FetchColumn
from app.adapters.reading_on import Bookmark
from app.adapters.relation import ColumnType
from app.adapters.update import InsertRowsRequest, RowsInserted
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.main import app
from tests.adapters.rabbitmq_fixture import (
    EXCHANGE,
    ORDERS,
    QUEUE,
    QUORUM,
    STREAM,
    WAITING,
    adapter,
    amqp_host,
    amqp_port,
    make,
    management,
    names,
    options,
    password,
    remove,
    user,
)
from tests.pipelines.canvas import Canvas, card, connector, end, joined
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import conninfo, run

pytestmark = pytest.mark.usefixtures("clean")


@pytest.fixture
async def vhost() -> AsyncIterator[str]:
    made = names()
    await make(made)
    yield made
    await remove(made)


def _v(vhost: str) -> str:
    return quote(vhost, safe="")


def _id(kind: str, vhost: str, name: str) -> str:
    return f"{kind}:{_v(vhost)}/{quote(name, safe='')}"


@pytest.fixture
async def table(schema: str) -> str:
    await run(f"CREATE TABLE {schema}.arrived (id text, position text)")  # noqa: S608 -- the fixture's own schema
    return f"{schema}.arrived"


async def _rows(table: str) -> list[tuple[Any, ...]]:
    async with await psycopg.AsyncConnection.connect(conninfo()) as conn:
        query = f"SELECT * FROM {table} ORDER BY 1, 2"  # noqa: S608 -- a test's own table
        return await (await conn.execute(query)).fetchall()


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


async def _rabbit(client: AsyncClient, headers: dict[str, str], vhost: str) -> str:
    return await connector(
        client,
        headers,
        "rabbitmq",
        {
            "host": amqp_host(),
            "port": amqp_port(),
            "management_url": management(),
            "user": user(),
            "password": password(),
            "vhost": vhost,
        },
    )


async def _publish(vhost: str, routing_key: str, bodies: list[bytes]) -> None:
    connection = await aio_pika.connect(
        host=amqp_host(),
        port=amqp_port(),
        login=user(),
        password=password(),
        virtualhost=vhost,
    )
    async with connection:
        channel = await connection.channel()
        for body in bodies:
            await channel.default_exchange.publish(
                aio_pika.Message(body), routing_key=routing_key
            )


async def _drawn(
    client: AsyncClient,
    headers: dict[str, str],
    vhost: str,
    node: str,
    table: str,
    columns: list[dict[str, str]],
) -> tuple[Canvas, str]:
    rabbit = await _rabbit(client, headers, vhost)
    database = await connector(client, headers, "postgres", working_postgres_options())
    source = card(rabbit, [(node, node, None)], name="RabbitMQ")
    target = card(database, [(table, "arrived", "table")], x=400, name="Warehouse")
    canvas = await Canvas(client, headers).make()
    drawn = joined(
        end(source, node), end(target, table), "rows_since_last", columns=columns
    )
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text
    return canvas, str(drawn["id"])


# --- a stream, read on from a bookmark ---------------------------------------------


async def test_a_stream_is_read_on_from_where_the_link_stopped(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    vhost: str,
    table: str,
) -> None:
    canvas, link_id = await _drawn(
        client,
        normal_user_token_headers,
        vhost,
        _id("stream", vhost, STREAM),
        table,
        [
            {"source": "body.id", "target": "id"},
            {"source": "offset", "target": "position"},
        ],
    )
    first = await _ran(canvas, link_id)
    assert first == (
        f"{ORDERS + 1} new messages added to arrived; "
        "no position was kept, so reading started from the beginning"
    )
    assert len(await _rows(table)) == ORDERS + 1

    await _publish(
        vhost, STREAM, [json.dumps({"id": 900 + n}).encode() for n in range(3)]
    )
    assert await _ran(canvas, link_id) == "3 new messages added to arrived"
    assert await _ran(canvas, link_id) == "Nothing new since the last run"
    assert len(await _rows(table)) == ORDERS + 4


# --- a queue, consumed and acknowledged after writing --------------------------------


async def test_a_queue_is_taken_and_acknowledged_once_written(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    vhost: str,
    table: str,
) -> None:
    queue = _id("queue", vhost, QUEUE)
    canvas, link_id = await _drawn(
        client,
        normal_user_token_headers,
        vhost,
        queue,
        table,
        [
            {"source": "body", "target": "id"},
            {"source": "routing_key", "target": "position"},
        ],
    )
    assert await _ran(canvas, link_id) == f"{WAITING} new messages added to arrived"
    assert [row[1] for row in await _rows(table)] == ["orders.new"] * WAITING
    session = adapter()._session  # noqa: SLF001 - the exact count, not the API's sample
    assert await session.waiting(vhost, QUEUE) == 0

    await _publish(vhost, QUEUE, [b"one", b"two"])
    assert await _ran(canvas, link_id) == "2 new messages added to arrived"
    assert await _ran(canvas, link_id) == "Nothing new since the last run"


async def test_a_block_never_kept_goes_back_to_the_queue(vhost: str) -> None:
    """At least once: what was taken and not acknowledged is handed out again."""
    reading = adapter(options(vhost))
    queue = _id("queue", vhost, QUEUE)
    span = await reading.unread(queue, "link", "earliest")
    assert span.count == WAITING
    first = await reading.read_on(
        queue, ["body", "redelivered"], span.start, span.line, 100
    )
    assert [row[1] for row in first.rows] == ["false"] * WAITING
    # The write failed: no mark_read. The next reading lets the block go first.
    again = await reading.read_on(
        queue, ["body", "redelivered"], span.start, span.line, 100
    )
    assert [row[1] for row in again.rows] == ["true"] * WAITING
    await reading.mark_read(queue, "link", again.after)
    assert await reading._session.waiting(vhost, QUEUE) == 0  # noqa: SLF001


async def test_a_queue_gives_message_columns_not_its_bindings(vhost: str) -> None:
    given = await adapter(options(vhost)).moving_columns(
        _id("queue", vhost, QUEUE), None
    )
    assert given is not None
    assert [column.name for column in given] == [
        "redelivered",
        "exchange",
        "routing_key",
        "timestamp",
        "content_type",
        "headers",
        "properties",
        "body",
    ]
    assert (
        await adapter(options(vhost)).moving_columns(_id("stream", vhost, STREAM), None)
        is None
    )


# --- taking rows -------------------------------------------------------------------------


def _given(*names: str) -> list[FetchColumn]:
    return [
        FetchColumn(name=name, type=ColumnType(sql="text", category="string"))
        for name in names
    ]


async def test_an_exchange_takes_rows_with_their_columns_as_body_fields(
    vhost: str,
) -> None:
    taken = await adapter(options(vhost)).moving_columns(
        _id("exchange", vhost, EXCHANGE), _given("price", "qty", "body")
    )
    assert taken is not None
    names_taken = [column.name for column in taken]
    assert names_taken[0] == "routing_key"
    assert names_taken[-2:] == ["price", "qty"]
    assert all(column.insertable for column in taken)

    sent = await adapter(options(vhost)).insert_rows(
        InsertRowsRequest(
            node_id=_id("exchange", vhost, EXCHANGE),
            columns=["routing_key", "price", "qty", "side"],
            rows=[
                ["orders.paid", "65000.5", "2", "buy"],
                ["nowhere", "1", "1", "sell"],
            ],
        )
    )
    assert isinstance(sent, RowsInserted) and sent.inserted == 2
    # `billing` is bound to orders.#: the routed row arrives after what waited,
    # and the one routed nowhere does not.
    reading = adapter(options(vhost))
    billing = _id("queue", vhost, QUEUE)
    span = await reading.unread(billing, "test", "earliest")
    block = await reading.read_on(
        billing, ["body", "content_type"], span.start, span.line, 10
    )
    await reading.mark_read(billing, "test", block.after)
    assert len(block.rows) == WAITING + 1
    # Its fields are JSON, numbers as numbers.
    assert json.loads(block.rows[-1][0] or "") == {
        "price": 65000.5,
        "qty": 2,
        "side": "buy",
    }
    assert block.rows[-1][1] == "application/json"


async def test_a_table_is_added_to_a_queue_by_a_link(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    vhost: str,
    schema: str,
) -> None:
    headers = normal_user_token_headers
    rabbit = await _rabbit(client, headers, vhost)
    database = await connector(client, headers, "postgres", working_postgres_options())
    queue = _id("queue", vhost, QUORUM)
    source = card(
        database, [(f"{schema}.regions", "regions", "table")], name="Warehouse"
    )
    target = card(rabbit, [(queue, QUORUM, "amqp_queue")], x=400, name="RabbitMQ")
    canvas = await Canvas(client, headers).make()
    drawn = joined(
        end(source, f"{schema}.regions"),
        end(target, queue),
        "rows_into_relation",
        columns=[
            {"source": "id", "target": "id"},
            {"source": "code", "target": "code"},
        ],
    )
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text
    offers = await canvas.offers(end(source, f"{schema}.regions"), end(target, queue))
    offered = [
        column["name"] for column in offers["rows_into_relation"]["target_columns"]
    ]
    assert offered[-2:] == ["id", "code"]
    await _ran(canvas, str(drawn["id"]))

    reading = adapter(options(vhost))
    span = await reading.unread(queue, "test", "earliest")
    block = await reading.read_on(queue, ["body"], span.start, span.line, 10)
    await reading.mark_read(queue, "test", block.after)
    assert sorted(json.loads(row[0] or "")["code"] for row in block.rows) == [
        "EU",
        "US",
    ]
    assert Bookmark(positions={"taken": 2}) == block.after
