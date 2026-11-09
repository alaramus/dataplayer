"""RabbitMQ as a source: reaching it, its catalog, a stream's messages and the
bindings (D325–D327)."""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from urllib.parse import quote

import aio_pika
import pytest

from app.adapters.catalog import AmqpQueueNode, AmqpStreamNode, ExchangeNode
from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.protocol import NodeNotFound
from app.adapters.rabbitmq.adapter import RabbitmqAdapter
from app.adapters.rabbitmq.options import RabbitmqOptions
from app.adapters.rabbitmq.streams import DEPTH_CEILING
from app.adapters.summary import (
    AmqpExchangeContents,
    AmqpQueueContents,
    AmqpStreamContents,
)
from tests.adapters.rabbitmq_fixture import (
    BINARY_BODY,
    EXCHANGE,
    ORDERS,
    QUEUE,
    QUORUM,
    ROUTING_KEY,
    STREAM,
    WAITING,
    adapter,
    amqp_host,
    amqp_port,
    make,
    names,
    options,
    password,
    remove,
    user,
)


@pytest.fixture(scope="module")
async def vhost() -> AsyncIterator[str]:
    made = names()
    await make(made)
    yield made
    await remove(made)


def _v(vhost: str) -> str:
    return quote(vhost, safe="")


def stream_id(vhost: str) -> str:
    return f"stream:{_v(vhost)}/{quote(STREAM, safe='')}"


def queue_id(vhost: str, name: str = QUEUE) -> str:
    return f"queue:{_v(vhost)}/{quote(name, safe='')}"


def exchange_id(vhost: str, name: str = EXCHANGE) -> str:
    return f"exchange:{_v(vhost)}/{quote(name, safe='')}"


async def _page(
    request: FetchRequest,
) -> tuple[list[str], list[list[str | None]], bool]:
    result = await adapter().fetch(request)
    return [column.name for column in result.columns], result.rows, result.has_more


async def _waiting(vhost: str, queue: str) -> int:
    """Messages in a queue as AMQP counts them now, not as the API last did."""
    connection = await aio_pika.connect(
        host=amqp_host(),
        port=amqp_port(),
        login=user(),
        password=password(),
        virtualhost=vhost,
    )
    async with connection:
        channel = await connection.channel()
        declared = await channel.declare_queue(queue, passive=True)
        count = declared.declaration_result.message_count
        return int(count or 0)


async def _eventually[T](read: Callable[[], Awaitable[T]], wanted: T) -> T:
    """What the management API says, once its next sample has it (D326)."""
    deadline = time.monotonic() + 20
    found = await read()
    while found != wanted and time.monotonic() < deadline:
        await asyncio.sleep(1)
        found = await read()
    return found


# --- reaching it (D325) ---------------------------------------------------------


async def test_a_connection_is_checked() -> None:
    result = await adapter().check_connection()
    assert result.ok, result.message
    assert result.message == "Connection successful"


async def test_a_broker_that_does_not_answer_is_a_network_failure() -> None:
    result = await adapter(
        options(management_url="http://127.0.0.1:9", port=9)
    ).check_connection()
    assert not result.ok
    assert result.error_kind == "network"
    assert "127.0.0.1" not in result.message
    assert "management plugin" in result.message


async def test_a_wrong_password_is_refused_as_such_and_never_repeated() -> None:
    result = await adapter(options(password="not-the-password")).check_connection()
    assert not result.ok
    assert result.error_kind == "auth"
    assert "not-the-password" not in result.message


async def test_amqp_refused_with_the_api_answering_still_saves() -> None:
    """A virtual host AMQP will not open is said, and the catalog still works."""
    result = await adapter(options(vhost="no such vhost")).check_connection()
    assert result.ok
    assert result.message != "Connection successful"
    assert "virtual host" in result.message


def test_a_connection_string_fills_the_form_and_is_written_back() -> None:
    parsed = RabbitmqAdapter.options_from_url(
        "amqps://ann:s%40cret@mq.example:5671/%2F"
    )
    assert parsed == {
        "host": "mq.example",
        "port": 5671,
        "tls": True,
        "user": "ann",
        "password": "s@cret",
        "vhost": "/",
    }
    assert RabbitmqAdapter.options_from_url("amqp://mq.example")["port"] == 5672
    assert "vhost" not in RabbitmqAdapter.options_from_url("amqp://mq.example/")
    composed = RabbitmqAdapter.draft_connection_string(parsed)
    assert composed == "amqps://ann@mq.example:5671/%2F"
    with pytest.raises(ValueError):
        RabbitmqAdapter.options_from_url("kafka://mq.example:9092")


def test_the_management_address_is_a_plain_http_one() -> None:
    assert options().management().startswith("http")
    made = RabbitmqOptions(host="mq.example", tls=True)
    assert made.management() == "https://mq.example:15672"
    for wrong in ["ftp://mq", "http://ann:pw@mq:15672", "mq.example:15672"]:
        with pytest.raises(ValueError):
            RabbitmqOptions(host="mq", management_url=wrong)
    with pytest.raises(ValueError):
        RabbitmqOptions(host="mq/x")


# --- the catalog (D326) ----------------------------------------------------------


async def test_several_virtual_hosts_are_the_top(vhost: str) -> None:
    top = await adapter().list_children(None)
    # The broker's own section first (D331), then a level per virtual host.
    assert top[0].id == "broker"
    assert {node.name for node in top[1:]} >= {"/", vhost}
    assert all(node.kind == "directory" for node in top[1:])
    inside = await adapter().list_children(f"vhost:{_v(vhost)}")
    assert [node.id for node in inside] == [
        f"queues:{_v(vhost)}",
        f"streams:{_v(vhost)}",
        f"exchanges:{_v(vhost)}",
    ]


async def test_a_named_virtual_host_is_the_top_itself(vhost: str) -> None:
    top = await adapter(options(vhost)).list_children(None)
    assert [node.id for node in top] == [
        "broker",
        f"queues:{_v(vhost)}",
        f"streams:{_v(vhost)}",
        f"exchanges:{_v(vhost)}",
    ]


async def test_queues_and_streams_are_listed_apart(vhost: str) -> None:
    queues = await adapter().list_children(f"queues:{_v(vhost)}")
    by_name = {node.name: node for node in queues}
    assert set(by_name) == {QUEUE, QUORUM}
    billing = by_name[QUEUE]
    assert isinstance(billing, AmqpQueueNode)
    assert billing.queue_type == "classic"
    quorum = by_name[QUORUM]
    assert isinstance(quorum, AmqpQueueNode)
    assert quorum.queue_type == "quorum"
    streams = await adapter().list_children(f"streams:{_v(vhost)}")
    assert [node.name for node in streams] == [STREAM]
    assert isinstance(streams[0], AmqpStreamNode)
    assert streams[0].id == stream_id(vhost)


async def test_the_user_s_exchanges_come_before_the_built_in_ones(vhost: str) -> None:
    exchanges = await adapter().list_children(f"exchanges:{_v(vhost)}")
    assert exchanges[0].name == EXCHANGE
    first = exchanges[0]
    assert isinstance(first, ExchangeNode)
    assert first.exchange_type == "topic"
    assert not first.is_system
    rest = [node for node in exchanges[1:] if isinstance(node, ExchangeNode)]
    assert all(node.is_system for node in rest)
    assert "(default)" in {node.name for node in rest}


async def test_a_node_is_found_under_its_levels(vhost: str) -> None:
    path = await adapter().path_to(stream_id(vhost))
    assert [node.id for node in path] == [
        f"vhost:{_v(vhost)}",
        f"streams:{_v(vhost)}",
        stream_id(vhost),
    ]
    path = await adapter(options(vhost)).path_to(exchange_id(vhost))
    assert [node.id for node in path] == [f"exchanges:{_v(vhost)}", exchange_id(vhost)]


async def test_a_queue_asked_for_as_a_stream_is_missing(vhost: str) -> None:
    wrong = f"stream:{_v(vhost)}/{QUEUE}"
    with pytest.raises(NodeNotFound):
        await adapter().path_to(wrong)
    with pytest.raises(NodeNotFound):
        await adapter().fetch(FetchRequest(node_id=wrong))


async def test_reading_a_queue_as_a_stream_takes_nothing_from_it(vhost: str) -> None:
    """The check comes before any consumer: a consumer on a classic queue
    would take its messages for good (D327)."""
    with pytest.raises(NodeNotFound):
        await adapter().fetch(FetchRequest(node_id=f"stream:{_v(vhost)}/{QUEUE}"))
    assert await _waiting(vhost, QUEUE) == WAITING


async def test_a_name_that_is_not_this_source_s_is_refused() -> None:
    for wrong in ["topic:orders", "queue:", "queue:%2F", "vhost:a/b", "nothing"]:
        with pytest.raises(ValueError):
            await adapter().list_children(wrong)


async def test_another_virtual_host_is_not_this_connection_s(vhost: str) -> None:
    with pytest.raises(NodeNotFound):
        await adapter(options(vhost)).list_children("queues:%2F")


# --- bindings ----------------------------------------------------------------------


async def test_a_queue_shows_what_routes_to_it(vhost: str) -> None:
    columns, rows, more = await _page(FetchRequest(node_id=queue_id(vhost)))
    assert columns == ["exchange", "routing_key", "arguments"]
    # The default exchange's binding by the queue's name, then its own.
    assert rows == [["", QUEUE, None], [EXCHANGE, ROUTING_KEY, None]]
    assert not more


async def test_an_exchange_shows_where_it_routes(vhost: str) -> None:
    columns, rows, _ = await _page(FetchRequest(node_id=exchange_id(vhost)))
    assert columns == ["destination", "destination_type", "routing_key", "arguments"]
    assert rows == [[QUEUE, "queue", ROUTING_KEY, None]]
    default = await _page(FetchRequest(node_id=f"exchange:{_v(vhost)}/"))
    assert {row[0] for row in default[1]} == {QUEUE, QUORUM, STREAM}


async def test_bindings_are_not_filtered(vhost: str) -> None:
    with pytest.raises(ValueError):
        await adapter().fetch(
            FetchRequest(
                node_id=queue_id(vhost),
                filters=[ScalarFilter(column="routing_key", op="eq", value="x")],
            )
        )


# --- a stream's messages (D327) -------------------------------------------------------


async def test_the_newest_messages_come_first(vhost: str) -> None:
    columns, rows, more = await _page(FetchRequest(node_id=stream_id(vhost), limit=3))
    assert columns[:8] == [
        "offset",
        "timestamp",
        "exchange",
        "routing_key",
        "content_type",
        "headers",
        "properties",
        "body",
    ]
    assert columns[8:] == ["body.id", "body.price", "body.side"]
    assert [row[0] for row in rows] == [str(ORDERS), str(ORDERS - 1), str(ORDERS - 2)]
    assert rows[0][7] == "0x" + BINARY_BODY.hex()
    newest_order = rows[1]
    assert newest_order[3] == STREAM
    assert newest_order[4] == "application/json"
    assert newest_order[5] == '{"source": "fixture"}'
    assert newest_order[8] == str(ORDERS - 1)
    assert newest_order[1] is not None and newest_order[1].endswith("Z")
    assert more


async def test_a_page_further_on_continues_where_the_last_stopped(vhost: str) -> None:
    _, rows, _ = await _page(FetchRequest(node_id=stream_id(vhost), offset=3, limit=3))
    assert [row[0] for row in rows] == [
        str(ORDERS - 3),
        str(ORDERS - 4),
        str(ORDERS - 5),
    ]


async def test_the_oldest_come_first_when_asked(vhost: str) -> None:
    _, rows, _ = await _page(
        FetchRequest(
            node_id=stream_id(vhost),
            limit=3,
            sort=[Sort(column="offset", descending=False)],
        )
    )
    assert [row[0] for row in rows] == ["0", "1", "2"]


async def test_messages_are_ordered_by_offset_and_nothing_else(vhost: str) -> None:
    with pytest.raises(ValueError):
        await adapter().fetch(
            FetchRequest(node_id=stream_id(vhost), sort=[Sort(column="body")])
        )


async def test_reading_is_bounded_by_offsets(vhost: str) -> None:
    _, rows, more = await _page(
        FetchRequest(
            node_id=stream_id(vhost),
            filters=[
                ScalarFilter(column="offset", op="gte", value="10"),
                ScalarFilter(column="offset", op="lt", value="13"),
            ],
        )
    )
    assert [row[0] for row in rows] == ["12", "11", "10"]
    assert not more


async def test_a_field_of_the_bodies_filters_what_was_read(vhost: str) -> None:
    _, rows, _ = await _page(
        FetchRequest(
            node_id=stream_id(vhost),
            limit=50,
            filters=[ScalarFilter(column="body.side", op="eq", value="buy")],
        )
    )
    assert len(rows) == ORDERS // 2
    assert all(int(row[8] or 0) % 2 == 1 for row in rows)


async def test_text_is_looked_for_without_regard_to_case(vhost: str) -> None:
    _, rows, _ = await _page(
        FetchRequest(
            node_id=stream_id(vhost),
            limit=100,
            filters=[ScalarFilter(column="body", op="contains", value='"BUY"')],
        )
    )
    assert len(rows) == ORDERS // 2
    # A body that is not text is looked through as the hex it is shown as.
    _, rows, _ = await _page(
        FetchRequest(
            node_id=stream_id(vhost),
            filters=[ScalarFilter(column="body", op="starts_with", value="0XFF00")],
        )
    )
    assert [row[0] for row in rows] == [str(ORDERS)]


async def test_reading_starts_at_a_moment_of_the_stream_s_own(vhost: str) -> None:
    later = await _page(
        FetchRequest(
            node_id=stream_id(vhost),
            filters=[
                ScalarFilter(column="timestamp", op="gte", value="2999-01-01T00:00:00Z")
            ],
        )
    )
    assert later[1] == []
    earlier = await _page(
        FetchRequest(
            node_id=stream_id(vhost),
            limit=3,
            filters=[
                ScalarFilter(column="timestamp", op="gte", value="2000-01-01T00:00:00Z")
            ],
        )
    )
    assert [row[0] for row in earlier[1]] == [
        str(ORDERS),
        str(ORDERS - 1),
        str(ORDERS - 2),
    ]


async def test_a_filter_on_an_unknown_column_is_refused(vhost: str) -> None:
    with pytest.raises(ValueError):
        await adapter().fetch(
            FetchRequest(
                node_id=stream_id(vhost),
                filters=[ScalarFilter(column="nope", op="eq", value="1")],
            )
        )


async def test_a_page_does_not_reach_past_its_depth(vhost: str) -> None:
    with pytest.raises(ValueError):
        await adapter().fetch(
            FetchRequest(node_id=stream_id(vhost), offset=DEPTH_CEILING, limit=10)
        )


async def test_reading_a_stream_takes_nothing_from_it(vhost: str) -> None:
    await _page(FetchRequest(node_id=stream_id(vhost), limit=10))
    _, rows, _ = await _page(
        FetchRequest(
            node_id=stream_id(vhost),
            limit=5,
            sort=[Sort(column="offset", descending=False)],
        )
    )
    assert rows[0][0] == "0"


async def test_a_stream_is_exported_in_its_page_s_order(vhost: str) -> None:
    batches = [
        batch
        async for batch in adapter().export_rows(
            ExportRequest(node_id=stream_id(vhost), columns=["offset", "body.id"])
        )
    ]
    rows = [row for batch in batches for row in batch.rows]
    assert len(rows) == ORDERS + 1
    assert rows[0] == [str(ORDERS), None]
    assert rows[-1] == ["0", "0"]


# --- summaries ----------------------------------------------------------------------


async def test_a_queue_summary_counts_what_waits(vhost: str) -> None:
    async def ready() -> int | None:
        summary = await adapter().node_summary(queue_id(vhost))
        assert isinstance(summary.contents, AmqpQueueContents)
        return summary.contents.ready

    assert await _eventually(ready, WAITING) == WAITING
    summary = await adapter().node_summary(queue_id(vhost))
    contents = summary.contents
    assert isinstance(contents, AmqpQueueContents)
    assert contents.queue_type == "classic"
    assert contents.consumers == []
    assert [one.title for one in summary.representations] == ["View the bindings"]


async def test_a_stream_summary_shows_its_members(vhost: str) -> None:
    async def messages() -> int | None:
        summary = await adapter().node_summary(stream_id(vhost))
        assert isinstance(summary.contents, AmqpStreamContents)
        return summary.contents.messages

    assert await _eventually(messages, ORDERS + 1) == ORDERS + 1
    summary = await adapter().node_summary(stream_id(vhost))
    contents = summary.contents
    assert isinstance(contents, AmqpStreamContents)
    assert contents.leader is not None
    assert contents.members
    assert {one.name for one in contents.arguments} >= {"x-queue-type"}


async def test_an_exchange_summary_says_its_type(vhost: str) -> None:
    summary = await adapter().node_summary(exchange_id(vhost))
    contents = summary.contents
    assert isinstance(contents, AmqpExchangeContents)
    assert contents.exchange_type == "topic"
    assert contents.durable


async def test_a_queue_that_is_not_there_is_a_missing_node(vhost: str) -> None:
    with pytest.raises(NodeNotFound):
        await adapter().node_summary(queue_id(vhost, "nope"))
    with pytest.raises(NodeNotFound):
        await adapter().fetch(FetchRequest(node_id=queue_id(vhost, "nope")))
