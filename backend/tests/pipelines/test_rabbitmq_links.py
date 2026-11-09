"""RabbitMQ in pipelines: a stream and a queue read on, a queue and an
exchange taking rows (D335, D336), a queue's body fields named by the target
(D338), an exchange read through the link's own queue (D337)."""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import aio_pika
import httpx
import psycopg
import pytest
from httpx import AsyncClient

from app.adapters.fetch import FetchColumn
from app.adapters.protocol import AdapterError
from app.adapters.rabbitmq import link_queues
from app.adapters.reading_on import Bookmark
from app.adapters.relation import ColumnType
from app.adapters.update import InsertRowsRequest, RowsInserted
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.main import app
from app.pipelines.models import Link, reader_of
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
    order,
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


# --- a queue's body fields, named by the target (D338) ------------------------------


async def _fresh_queue(vhost: str, bodies: list[bytes]) -> str:
    """A queue of its own holding exactly `bodies`."""
    name = f"fields-{uuid.uuid4().hex[:8]}"
    connection = await aio_pika.connect(
        host=amqp_host(),
        port=amqp_port(),
        login=user(),
        password=password(),
        virtualhost=vhost,
    )
    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(name, durable=True)
    await _publish(vhost, name, bodies)
    return name


async def test_a_queue_answers_the_fields_the_target_names(vhost: str) -> None:
    taken = await adapter(options(vhost)).moving_columns(
        _id("queue", vhost, QUEUE), None, _given("price", "body", "side", "")
    )
    assert taken is not None
    names_taken = [column.name for column in taken]
    # Its own columns first, `body` once, then a field for each other name.
    assert names_taken[:8] == [
        "redelivered",
        "exchange",
        "routing_key",
        "timestamp",
        "content_type",
        "headers",
        "properties",
        "body",
    ]
    assert names_taken[8:] == ["price", "side"]
    # A stream keeps the fields of its page.
    assert (
        await adapter(options(vhost)).moving_columns(
            _id("stream", vhost, STREAM), None, _given("price")
        )
        is None
    )


async def test_a_queue_s_body_fields_are_cells_and_nulls(vhost: str) -> None:
    name = await _fresh_queue(
        vhost,
        [
            json.dumps(
                {"price": 65000.5, "paid": True, "side": "buy", "detail": {"a": [1]}}
            ).encode(),
            json.dumps({"side": "sell"}).encode(),
            b"not json at all",
            b"[1, 2]",
        ],
    )
    reading = adapter(options(vhost))
    queue = _id("queue", vhost, name)
    span = await reading.unread(queue, "link", "earliest")
    block = await reading.read_on(
        queue, ["price", "paid", "side", "detail", "body"], span.start, span.line, 10
    )
    await reading.mark_read(queue, "link", block.after)

    assert block.rows[0][:4] == ["65000.5", "true", "buy", '{"a":[1]}']
    # A field missing, or a body that is not a JSON object, is null; the row
    # is still there, the body as it came.
    assert block.rows[1][:4] == [None, None, "sell", None]
    assert block.rows[2] == [None, None, None, None, "not json at all"]
    assert block.rows[3] == [None, None, None, None, "[1, 2]"]


async def test_a_link_from_a_queue_pairs_the_body_s_fields_by_name(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    vhost: str,
    schema: str,
) -> None:
    headers = normal_user_token_headers
    await run(f"CREATE TABLE {schema}.trades (price numeric, side text, body text)")  # noqa: S608 -- the fixture's own schema
    name = await _fresh_queue(
        vhost, [json.dumps({"price": 10.5, "side": "buy"}).encode(), b"plain"]
    )
    queue = _id("queue", vhost, name)
    table = f"{schema}.trades"
    rabbit = await _rabbit(client, headers, vhost)
    database = await connector(client, headers, "postgres", working_postgres_options())
    source = card(rabbit, [(queue, name, "amqp_queue")], name="RabbitMQ")
    target = card(database, [(table, "trades", "table")], x=400, name="Warehouse")
    canvas = await Canvas(client, headers).make()
    drawn = joined(
        end(source, queue),
        end(target, table),
        "rows_since_last",
        columns=[
            {"source": "price", "target": "price"},
            {"source": "side", "target": "side"},
            {"source": "body", "target": "body"},
        ],
    )
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text

    offers = await canvas.offers(end(source, queue), end(target, table))
    read = [column["name"] for column in offers["rows_since_last"]["source_columns"]]
    assert read[-2:] == ["price", "side"]
    assert read.count("body") == 1

    assert await _ran(canvas, str(drawn["id"])) == "2 new messages added to trades"
    async with await psycopg.AsyncConnection.connect(conninfo()) as conn:
        query = f"SELECT price::text, side, body FROM {table} ORDER BY body"  # noqa: S608 -- a test's own table
        rows = await (await conn.execute(query)).fetchall()
    assert rows[0] == (None, None, "plain")
    assert rows[1][:2] == ("10.5", "buy")


# --- an exchange, read through the link's own queue (D337) ------------------------


def _api() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=management() + "/api", auth=(user(), password()), timeout=10
    )


async def _to_exchange(vhost: str, routed: list[tuple[str, bytes]]) -> None:
    connection = await aio_pika.connect(
        host=amqp_host(),
        port=amqp_port(),
        login=user(),
        password=password(),
        virtualhost=vhost,
    )
    async with connection:
        channel = await connection.channel()
        exchange = await channel.get_exchange(EXCHANGE)
        for key, body in routed:
            await exchange.publish(aio_pika.Message(body), routing_key=key)


async def _link_queue(vhost: str, name: str) -> dict[str, Any] | None:
    async with _api() as api:
        found = await api.get(f"/queues/{_v(vhost)}/{quote(name, safe='')}")
        if found.status_code == 404:
            return None
        found.raise_for_status()
        result: dict[str, Any] = found.json()
        bound = await api.get(
            f"/bindings/{_v(vhost)}/e/{quote(EXCHANGE, safe='')}/q/{quote(name, safe='')}"
        )
        bound.raise_for_status()
        result["bound_by"] = sorted(one["routing_key"] for one in bound.json())
        return result


async def _exchange_link(
    client: AsyncClient,
    headers: dict[str, str],
    vhost: str,
    table: str,
    binding_key: str | None = None,
) -> tuple[Canvas, dict[str, Any], dict[str, Any], dict[str, Any]]:
    exchange = _id("exchange", vhost, EXCHANGE)
    rabbit = await _rabbit(client, headers, vhost)
    database = await connector(client, headers, "postgres", working_postgres_options())
    source = card(rabbit, [(exchange, EXCHANGE, "exchange")], name="RabbitMQ")
    target = card(database, [(table, "arrived", "table")], x=400, name="Warehouse")
    canvas = await Canvas(client, headers).make()
    drawn = joined(
        end(source, exchange),
        end(target, table),
        "rows_since_last",
        columns=[
            {"source": "id", "target": "id"},
            {"source": "routing_key", "target": "position"},
        ],
        binding_key=binding_key,
    )
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text
    return canvas, source, target, drawn


async def test_an_exchange_is_read_through_a_queue_of_the_link_s_own(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    vhost: str,
    table: str,
) -> None:
    canvas, _, _, drawn = await _exchange_link(
        client, normal_user_token_headers, vhost, table
    )
    link_id = str(drawn["id"])
    queue = f"dataplayer-link-{link_id}"
    # Saving never talks to the broker.
    assert await _link_queue(vhost, queue) is None

    first = await _ran(canvas, link_id)
    assert first == (
        "Nothing new since the last run; "
        "the link began reading now, and gets what arrives from here on"
    )
    made = await _link_queue(vhost, queue)
    assert made is not None
    assert made["durable"] and made["type"] == "classic"
    assert made["arguments"]["x-expires"] == link_queues.WEEK_MS
    assert made["arguments"]["x-max-length"] == link_queues.MAX_LENGTH
    assert made["arguments"]["x-overflow"] == "drop-head"
    # A topic exchange with no key named takes everything.
    assert made["bound_by"] == ["#"]

    await _to_exchange(
        vhost,
        [("orders.new", json.dumps(order(1)).encode()), ("other", b'{"id": "x"}')],
    )
    assert await _ran(canvas, link_id) == "2 new messages added to arrived"
    assert sorted(row[1] for row in await _rows(table)) == ["orders.new", "other"]
    # The queue the exchange also routes to keeps its own: the link took none.
    session = adapter()._session  # noqa: SLF001 - the exact count, not the API's sample
    assert await session.waiting(vhost, QUEUE) == WAITING + 1
    assert await session.waiting(vhost, queue) == 0
    assert await _ran(canvas, link_id) == "Nothing new since the last run"


async def test_an_exchange_s_link_makes_its_table_at_the_first_run(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    vhost: str,
    schema: str,
) -> None:
    """The first run made the queue, so it is the run that makes the table
    (D313), and the next adds to it."""
    headers = normal_user_token_headers
    exchange = _id("exchange", vhost, EXCHANGE)
    rabbit = await _rabbit(client, headers, vhost)
    database = await connector(client, headers, "postgres", working_postgres_options())
    source = card(rabbit, [(exchange, EXCHANGE, "exchange")], name="RabbitMQ")
    target = card(database, [(schema, schema, "schema")], x=400, name="Warehouse")
    canvas = await Canvas(client, headers).make()
    drawn = joined(
        end(source, exchange),
        end(target, schema),
        "rows_since_last_new",
        name="routed",
        columns=[
            {"source": "routing_key", "target": "routing_key", "type_code": "text"},
            {"source": "body", "target": "body", "type_code": "text"},
        ],
    )
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text
    link_id = str(drawn["id"])

    first = await _ran(canvas, link_id)
    assert first == (
        "Nothing new since the last run; the table was made; "
        "the link began reading now, and gets what arrives from here on"
    )
    await _to_exchange(vhost, [("orders.new", b"{}")])
    assert await _ran(canvas, link_id) == "1 new messages added to routed"
    assert len(await _rows(f"{schema}.routed")) == 1


async def test_a_key_changed_is_bound_at_the_next_run_and_the_old_one_removed(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    vhost: str,
    table: str,
) -> None:
    canvas, source, target, drawn = await _exchange_link(
        client, normal_user_token_headers, vhost, table
    )
    link_id = str(drawn["id"])
    queue = f"dataplayer-link-{link_id}"
    await _ran(canvas, link_id)
    drawn["binding_key"] = "orders.paid"
    saved = await canvas.save([source, target], [drawn])
    assert saved.status_code == 200, saved.text

    # Bound anew before the step reads anything.
    assert await _ran(canvas, link_id) == "Nothing new since the last run"
    found = await _link_queue(vhost, queue)
    assert found is not None and found["bound_by"] == ["orders.paid"]
    await _to_exchange(vhost, [("orders.paid", b"{}"), ("orders.new", b"{}")])
    assert await _ran(canvas, link_id) == "1 new messages added to arrived"


async def test_the_form_asks_an_exchange_s_key_and_tells_a_queue_it_shares(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    vhost: str,
    table: str,
) -> None:
    canvas, source, target, _ = await _exchange_link(
        client, normal_user_token_headers, vhost, table
    )
    offers = await canvas.offers(
        end(source, _id("exchange", vhost, EXCHANGE)), end(target, table)
    )
    reading = offers["rows_since_last"]["reading"]
    assert reading["asks_binding_key"] is True
    assert reading["default_binding_key"] == "#"
    assert "queue of its own" in reading["note"]
    read = [column["name"] for column in offers["rows_since_last"]["source_columns"]]
    # The messages' own columns, and the body's fields the table names (D338).
    assert read[:3] == ["redelivered", "exchange", "routing_key"]
    assert read[-2:] == ["id", "position"]

    terms = await adapter(options(vhost)).reading_terms(_id("queue", vhost, QUEUE))
    assert terms.asks_binding_key is False
    assert terms.note is not None and "share" in terms.note
    # The default exchange takes no bindings, so it is not read on.
    assert not adapter(options(vhost)).reads_on(_id("exchange", vhost, ""))


def test_an_exchange_type_says_how_the_link_s_queue_is_bound() -> None:
    assert link_queues.wanted_binding("topic", None) == ("#", {})
    assert link_queues.wanted_binding("topic", "orders.*") == ("orders.*", {})
    assert link_queues.wanted_binding("direct", None) == ("", {})
    assert link_queues.wanted_binding("fanout", "ignored") == ("", {})
    assert link_queues.wanted_binding("headers", "ignored") == ("", {"x-match": "all"})


async def test_a_queue_of_that_name_with_other_settings_is_refused(vhost: str) -> None:
    reader = f"dataplayer-link-{uuid.uuid4()}"
    async with _api() as api:
        made = await api.put(
            f"/queues/{_v(vhost)}/{quote(reader, safe='')}", json={"durable": True}
        )
        made.raise_for_status()

    with pytest.raises(AdapterError) as refused:
        await adapter(options(vhost)).prepare_reader(
            _id("exchange", vhost, EXCHANGE), reader, None
        )

    assert refused.value.error_kind == "config"
    assert reader in refused.value.message


async def test_an_account_that_may_not_configure_is_told_which_permission(
    vhost: str,
) -> None:
    who, secret = f"dp-limited-{uuid.uuid4().hex[:8]}", "limited"
    async with _api() as api:
        (
            await api.put(f"/users/{who}", json={"password": secret, "tags": "management"})
        ).raise_for_status()
        (
            await api.put(
                f"/permissions/{_v(vhost)}/{who}",
                json={"configure": "^$", "write": ".*", "read": ".*"},
            )
        ).raise_for_status()
    try:
        limited = adapter(options(vhost, user=who, password=secret))
        with pytest.raises(AdapterError) as refused:
            await limited.prepare_reader(
                _id("exchange", vhost, EXCHANGE), "dataplayer-link-limited", None
            )
        assert refused.value.error_kind == "auth"
        assert "configure" in refused.value.message
    finally:
        async with _api() as api:
            await api.delete(f"/users/{who}")


def test_a_link_s_queue_is_named_by_the_link() -> None:
    link = Link.model_validate(
        {
            "id": str(uuid.uuid4()),
            "source": {"card_id": str(uuid.uuid4()), "node_id": "exchange:x/y"},
            "target": {"card_id": str(uuid.uuid4()), "node_id": "t"},
            "kind": "rows_since_last",
            "title": "t",
            "binding_key": "orders.#",
        }
    )
    assert reader_of(link) == f"dataplayer-link-{link.id}"


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
