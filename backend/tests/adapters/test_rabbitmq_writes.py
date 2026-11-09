"""Writing to RabbitMQ: messages as rows of a stream, and the actions (D329, D330)."""

import uuid
from collections.abc import AsyncIterator
from urllib.parse import quote

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.fetch import FetchRequest, Sort
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.rabbitmq.actions import offered, parse_arguments
from app.adapters.rabbitmq.adapter import RabbitmqAdapter
from app.adapters.resources import Pooling, ResourceStore
from app.adapters.update import (
    InsertRowRequest,
    InsertRowsRequest,
    InsertValue,
    RowsInserted,
    ValuesRejected,
)
from tests.adapters.rabbitmq_fixture import (
    EXCHANGE,
    ORDERS,
    QUEUE,
    QUORUM,
    STREAM,
    WAITING,
    make,
    names,
    options,
    remove,
)


@pytest.fixture(scope="module")
async def vhost() -> AsyncIterator[str]:
    made = names()
    await make(made)
    yield made
    await remove(made)


@pytest.fixture
async def store() -> AsyncIterator[ResourceStore]:
    kept = ResourceStore(max_entries=10, max_idle_seconds=600)
    yield kept
    await kept.aclose()


def _adapter(store: ResourceStore | None = None) -> RabbitmqAdapter:
    pooling = None if store is None else Pooling(store=store, connector_id=uuid.uuid4())
    return RabbitmqAdapter(options(), pooling)


def _v(vhost: str) -> str:
    return quote(vhost, safe="")


def _id(kind: str, vhost: str, name: str) -> str:
    return f"{kind}:{_v(vhost)}/{quote(name, safe='')}"


async def _newest(vhost: str, count: int) -> list[list[str | None]]:
    page = await _adapter().fetch(
        FetchRequest(node_id=_id("stream", vhost, STREAM), limit=count)
    )
    return page.rows


# --- messages as rows of a stream (D329) -------------------------------------------


async def test_a_page_of_a_stream_takes_new_rows(vhost: str) -> None:
    page = await _adapter().fetch(FetchRequest(node_id=_id("stream", vhost, STREAM)))
    assert page.insert_supported
    insertable = {column.name for column in page.columns if column.insertable}
    assert insertable >= {"timestamp", "content_type", "headers", "properties", "body"}
    assert not insertable & {"offset", "exchange", "routing_key"}


async def test_fields_without_a_body_are_sent_as_a_json_object(vhost: str) -> None:
    sent = await _adapter().insert_row(
        InsertRowRequest(
            node_id=_id("stream", vhost, STREAM),
            values=[
                InsertValue(column="body.id", value="999"),
                InsertValue(column="body.side", value="buy"),
            ],
        )
    )
    assert sent.values[7] == '{"id":999,"side":"buy"}'
    newest = (await _newest(vhost, 1))[0]
    assert newest[3] == STREAM
    assert newest[4] == "application/json"
    assert newest[7] == '{"id":999,"side":"buy"}'


async def test_a_block_with_a_cell_that_will_not_read_sends_nothing(vhost: str) -> None:
    before = (await _newest(vhost, 1))[0][0]
    answer = await _adapter().insert_rows(
        InsertRowsRequest(
            node_id=_id("stream", vhost, STREAM),
            columns=["body", "headers"],
            rows=[["fine", '{"a": "b"}'], ["no", "not json"]],
        )
    )
    assert isinstance(answer, ValuesRejected)
    assert [(cell.row, cell.column) for cell in answer.cells] == [(1, "headers")]
    assert (await _newest(vhost, 1))[0][0] == before


async def test_properties_and_bytes_are_sent_as_given(vhost: str) -> None:
    answer = await _adapter().insert_rows(
        InsertRowsRequest(
            node_id=_id("stream", vhost, STREAM),
            columns=["body", "properties", "timestamp"],
            rows=[
                [
                    "0x00ff",
                    '{"message_id": "m-7", "priority": 3}',
                    "2026-01-02T03:04:05Z",
                ]
            ],
        )
    )
    assert isinstance(answer, RowsInserted) and answer.inserted == 1
    newest = (await _newest(vhost, 1))[0]
    assert newest[7] == "0x00ff"
    assert newest[1] == "2026-01-02T03:04:05.000Z"
    assert '"message_id": "m-7"' in (newest[6] or "")
    assert '"priority": 3' in (newest[6] or "")


async def test_properties_amqp_does_not_name_are_refused(vhost: str) -> None:
    answer = await _adapter().insert_rows(
        InsertRowsRequest(
            node_id=_id("stream", vhost, STREAM),
            columns=["properties"],
            rows=[['{"colour": "red"}']],
        )
    )
    assert isinstance(answer, ValuesRejected)


async def test_a_queue_takes_no_rows(vhost: str) -> None:
    with pytest.raises(ValueError):
        await _adapter().insert_row(
            InsertRowRequest(
                node_id=_id("queue", vhost, QUEUE),
                values=[InsertValue(column="body", value="x")],
            )
        )


# --- the actions (D330) -------------------------------------------------------------


def test_arguments_are_json_when_they_read_as_json() -> None:
    assert parse_arguments(
        "x-max-length=1000\n# a comment\nx-overflow=reject-publish"
    ) == {
        "x-max-length": 1000,
        "x-overflow": "reject-publish",
    }
    for wrong in ["no equals", "bad name!=1", "a=1\na=2"]:
        with pytest.raises(ValueError):
            parse_arguments(wrong)


def test_each_level_and_node_offers_its_own() -> None:
    assert offered("queues:%2F")[0] == "new_queue"
    assert "peek" in offered("queue:%2F/billing")
    assert "peek" not in offered("stream:%2F/log")
    assert "purge" not in offered("stream:%2F/log")
    assert offered("exchange:%2F/") == ["publish", "open_management"]
    assert "delete" not in offered("exchange:%2F/amq.topic")
    assert offered("vhost:%2F") == ["open_management"]
    assert offered(None) == ["open_management"]


async def test_a_queue_is_made_bound_published_to_and_deleted(vhost: str) -> None:
    adapter = _adapter()
    made = await adapter.action("new_queue").perform(
        f"queues:{_v(vhost)}",
        {"name": "made.here", "queue_type": "quorum", "arguments": "x-max-length=50"},
    )
    queue = _id("queue", vhost, "made.here")
    assert made.created_node_id == queue
    hints = await adapter.action("bind").field_hints(queue)
    choices = [choice.value for choice in hints.choices["other"]]
    assert choices[0] == f"exchange:{EXCHANGE}"
    await adapter.action("bind").perform(
        queue, {"other": f"exchange:{EXCHANGE}", "routing_key": "made.#"}
    )
    await adapter.action("publish").perform(
        _id("exchange", vhost, EXCHANGE), {"routing_key": "made.one", "body": "hi"}
    )
    preview = await adapter.action("delete").preview(queue, {})
    assert "1 messages" in preview.summary
    assert any(EXCHANGE in item for item in preview.items)
    await adapter.action("delete").perform(queue, {})
    with pytest.raises(NodeNotFound):
        await adapter.node_summary(queue)


async def test_a_message_routed_nowhere_is_said_to_be_lost(vhost: str) -> None:
    with pytest.raises(ActionRefused) as refused:
        await (
            _adapter()
            .action("publish")
            .perform(
                _id("exchange", vhost, EXCHANGE),
                {"routing_key": "nobody.here", "body": "x"},
            )
        )
    assert "lost" in refused.value.message


async def test_a_name_taken_with_other_settings_is_said(vhost: str) -> None:
    with pytest.raises(AdapterError) as failed:
        await (
            _adapter()
            .action("new_queue")
            .perform(f"queues:{_v(vhost)}", {"name": QUEUE, "durable": False})
        )
    assert failed.value.error_kind == "config"
    with pytest.raises(ValueError):
        await (
            _adapter()
            .action("new_exchange")
            .perform(f"exchanges:{_v(vhost)}", {"name": "amq.mine"})
        )


async def test_a_stream_and_an_exchange_are_made_where_they_belong(vhost: str) -> None:
    adapter = _adapter()
    with pytest.raises(ActionRefused):
        await adapter.action("new_stream").perform(f"queues:{_v(vhost)}", {"name": "x"})
    await adapter.action("new_stream").perform(
        f"streams:{_v(vhost)}", {"name": "kept.week", "max_age": "7D"}
    )
    summary = await adapter.node_summary(_id("stream", vhost, "kept.week"))
    assert summary.kind == "amqp_stream"
    await adapter.action("new_exchange").perform(
        f"exchanges:{_v(vhost)}", {"name": "fan", "exchange_type": "fanout"}
    )
    with pytest.raises(ActionRefused):
        await adapter.action("new_exchange").perform(
            f"exchanges:{_v(vhost)}", {"name": "odd", "exchange_type": "no-such-type"}
        )


async def test_the_broker_s_exchanges_are_not_deleted(vhost: str) -> None:
    preview = (
        await _adapter()
        .action("delete")
        .preview(_id("exchange", vhost, "amq.topic"), {})
    )
    assert preview.blocked


async def test_unbinding_chooses_among_the_node_s_own(vhost: str) -> None:
    adapter = _adapter()
    queue = _id("queue", vhost, QUORUM)
    await adapter.action("bind").perform(
        queue, {"other": f"exchange:{EXCHANGE}", "routing_key": "audit.#"}
    )
    hints = await adapter.action("unbind").field_hints(queue)
    [choice] = hints.choices["binding"]
    assert choice.label == f"from {EXCHANGE} by audit.#"
    await adapter.action("unbind").perform(queue, {"binding": choice.value})
    assert (await adapter.action("unbind").field_hints(queue)).choices["binding"] == []
    preview = await adapter.action("unbind").preview(queue, {"binding": choice.value})
    assert preview.blocked


async def test_peek_keeps_a_snapshot_and_puts_the_messages_back(
    vhost: str, store: ResourceStore
) -> None:
    adapter = _adapter(store)
    queue = _id("queue", vhost, QUEUE)
    preview = await adapter.action("peek").preview(queue, {"count": 2})
    assert preview.summary.startswith(f"2 of {WAITING} ready messages")
    done = await adapter.action("peek").perform(queue, {"count": 2})
    assert done.open_node_id is not None
    page = await adapter.fetch(FetchRequest(node_id=done.open_node_id))
    assert [row[0] for row in page.rows] == ["1", "2"]
    assert page.rows[0][2] == EXCHANGE
    assert "body.id" in [column.name for column in page.columns]
    path = await adapter.path_to(done.open_node_id)
    assert [node.id for node in path][-2:] == [queue, done.open_node_id]
    # Put back: the queue holds as many as before, now marked redelivered.
    again = await adapter.action("peek").perform(queue, {"count": 1})
    assert again.open_node_id is not None
    looked = await adapter.fetch(FetchRequest(node_id=again.open_node_id))
    assert looked.rows[0][1] == "true"
    assert (await adapter.action("purge").preview(queue, {})).summary.startswith(
        f"{WAITING} ready"
    )
    with pytest.raises(ValueError):
        await adapter.fetch(
            FetchRequest(node_id=done.open_node_id, sort=[Sort(column="position")])
        )


async def test_a_look_is_kept_only_where_there_is_a_store(vhost: str) -> None:
    with pytest.raises(ActionRefused):
        await (
            _adapter().action("peek").perform(_id("queue", vhost, QUEUE), {"count": 1})
        )
    with pytest.raises(NodeNotFound):
        await _adapter().fetch(FetchRequest(node_id=f"peek:{_v(vhost)}/{QUEUE}/1"))


async def test_purge_empties_a_queue(vhost: str) -> None:
    adapter = _adapter()
    queue = _id("queue", vhost, "to.purge")
    await adapter.action("new_queue").perform(
        f"queues:{_v(vhost)}", {"name": "to.purge"}
    )
    for _ in range(2):
        await adapter.action("publish").perform(queue, {"body": "x"})
    preview = await adapter.action("purge").preview(queue, {})
    assert preview.summary.startswith("2 ready")
    await adapter.action("purge").perform(queue, {})
    assert (await adapter.action("purge").preview(queue, {})).summary.startswith(
        "0 ready"
    )


async def test_a_stream_is_not_peeked_or_purged(vhost: str) -> None:
    with pytest.raises(ActionRefused):
        await (
            _adapter()
            .action("peek")
            .perform(_id("stream", vhost, STREAM), {"count": 1})
        )
    assert ORDERS > 0


async def test_the_management_page_is_opened_from_every_level(vhost: str) -> None:
    """It changes nothing and needs no form (D334)."""
    assert "open_management" in offered(None)
    assert "open_management" in offered(f"queue:{_v(vhost)}/{QUEUE}")
    assert "open_management" in offered("report:overview")
    action = _adapter().action("open_management")
    assert action.opens_address and action.requires == "read"
    done = await action.perform(None, {})
    assert done.open_url == options().management()
    told = RabbitmqAdapter(options(browser_url="http://127.0.0.1:49301"))
    done = await told.action("open_management").perform(None, {})
    assert done.open_url == "http://127.0.0.1:49301"
