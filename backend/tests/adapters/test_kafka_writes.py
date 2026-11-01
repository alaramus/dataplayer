"""Writing to Kafka: messages as new rows, and actions on topics and groups (D308, D309)."""

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.adapters.actions import ActionRefused, JsonAction
from app.adapters.fetch import FetchRequest, InFilter
from app.adapters.kafka.actions import parse_settings
from app.adapters.kafka.writes import bytes_of
from app.adapters.summary import KafkaTopicContents
from app.adapters.update import (
    InsertRowRequest,
    InsertRowsRequest,
    InsertValue,
    RowsInserted,
    ValuesRejected,
)
from tests.adapters.kafka_fixture import (
    GROUP_READ,
    ORDERS,
    PARTITIONS,
    adapter,
    admin,
    make,
    names,
    on_server,
    remove,
    topics,
)


@pytest.fixture(scope="module")
async def made() -> AsyncIterator[tuple[str, str]]:
    topic, group = names()
    await on_server(lambda: make(topic, group))
    yield topic, group
    await on_server(lambda: remove(topic, group))


@pytest.fixture
async def scratch() -> AsyncIterator[str]:
    """A topic of its own for a test that changes one, removed afterwards."""
    name = names()[0] + ".scratch"
    yield name

    def drop() -> None:
        # Held while the futures resolve: a client dropped first cancels them.
        client = admin()
        if name in topics():
            for future in client.delete_topics([name]).values():
                future.result()

    await on_server(drop)


def _action(name: str) -> JsonAction[Any]:
    action = adapter().action(name)
    assert isinstance(action, JsonAction)
    return action


async def _make_topic(name: str, partitions: int = 1, settings: str = "") -> None:
    await _action("new_topic").perform(
        "topics", {"name": name, "partitions": partitions, "settings": settings}
    )


# --- messages as new rows (D308) -------------------------------------------------


async def test_a_message_is_sent_as_a_new_row_and_comes_back_as_one(
    made: tuple[str, str],
) -> None:
    topic = made[0]
    sent = await adapter().insert_row(
        InsertRowRequest(
            node_id=f"topic:{topic}",
            values=[
                InsertValue(column="partition", value="2"),
                InsertValue(column="key", value="by-hand"),
                InsertValue(column="value.price", value="12.5"),
                InsertValue(column="value.side", value="buy"),
                InsertValue(column="headers", value='{"origin": "test"}'),
            ],
        )
    )
    assert sent.row_handle is not None and sent.row_handle.startswith("2:")
    assert sent.values[0] == "2"
    assert json.loads(sent.values[4] or "") == {"price": 12.5, "side": "buy"}
    assert sent.values[5] == '{"origin": "test"}'
    page = await adapter().fetch(
        FetchRequest(
            node_id=f"topic:{topic}",
            limit=1,
            filters=[InFilter(column="partition", op="in", values=["2"])],
        )
    )
    assert page.rows[0][3] == "by-hand"
    assert page.insert_supported


async def test_a_block_is_read_whole_before_anything_is_sent(
    made: tuple[str, str],
) -> None:
    topic = made[0]
    before = (await adapter().node_summary(f"topic:{topic}")).contents
    assert isinstance(before, KafkaTopicContents)
    rejected = await adapter().insert_rows(
        InsertRowsRequest(
            node_id=f"topic:{topic}",
            columns=["key", "value.price", "partition"],
            rows=[["a", "1", None], ["b", "cheap", None], ["c", "3", "99"]],
        )
    )
    assert isinstance(rejected, ValuesRejected)
    assert [(cell.row, cell.column) for cell in rejected.cells] == [
        (1, "value.price"),
        (2, "partition"),
    ]
    after = (await adapter().node_summary(f"topic:{topic}")).contents
    assert isinstance(after, KafkaTopicContents)
    assert after.messages == before.messages


async def test_a_block_of_rows_is_sent_and_counted(scratch: str) -> None:
    await _make_topic(scratch)
    inserted = await adapter().insert_rows(
        InsertRowsRequest(
            node_id=f"topic:{scratch}",
            columns=["key", "value"],
            rows=[[f"k{index}", f"line {index}"] for index in range(30)],
        )
    )
    assert inserted == RowsInserted(inserted=30)
    page = await adapter().fetch(FetchRequest(node_id=f"topic:{scratch}", limit=50))
    assert len(page.rows) == 30


def test_hex_is_bytes_and_anything_else_is_text() -> None:
    assert bytes_of("0x00ff") == b"\x00\xff"
    assert bytes_of("0xzz") == b"0xzz"
    assert bytes_of("0x1") == b"0x1"
    assert bytes_of("plain") == b"plain"


async def test_kafka_s_own_topics_take_no_message() -> None:
    page = await adapter().fetch(
        FetchRequest(node_id="topic:__consumer_offsets", limit=1)
    )
    assert not page.insert_supported and page.insert_reason
    with pytest.raises(ValueError):
        await adapter().insert_row(
            InsertRowRequest(
                node_id="topic:__consumer_offsets",
                values=[InsertValue(column="value", value="x")],
            )
        )


# --- topics (D309) -----------------------------------------------------------------


def test_settings_are_name_and_value_per_line() -> None:
    assert parse_settings(
        "# kept a day\nretention.ms = 86400000\n\ncleanup.policy=compact"
    ) == {
        "retention.ms": "86400000",
        "cleanup.policy": "compact",
    }
    for wrong in ["retention.ms", "Retention=1", "a=1\na=2", "a b=1"]:
        with pytest.raises(ValueError):
            parse_settings(wrong)


async def test_what_is_offered_where(made: tuple[str, str]) -> None:
    def named(actions: list[Any]) -> list[str]:
        return [action.name for action in actions]

    assert named(await adapter().available("topics"))[0] == "new_topic"
    assert "delete_topic" in named(await adapter().available(f"topic:{made[0]}"))
    assert named(await adapter().available("internal")) == []
    assert named(await adapter().available("topic:__consumer_offsets")) == []
    assert named(await adapter().available(f"group:{made[1]}")) == [
        "move_group_positions"
    ]
    assert named(await adapter().available(None)) == []


async def test_a_topic_is_made_with_its_settings(scratch: str) -> None:
    result = await _action("new_topic").perform(
        "topics", {"name": scratch, "partitions": 2, "settings": "retention.ms=3600000"}
    )
    assert result.created_node_id == f"topic:{scratch}"
    summary = (await adapter().node_summary(f"topic:{scratch}")).contents
    assert isinstance(summary, KafkaTopicContents)
    assert len(summary.partitions) == 2
    assert [(one.name, one.value) for one in summary.settings] == [
        ("retention.ms", "3600000")
    ]
    with pytest.raises(Exception, match="already exists"):
        await _make_topic(scratch)


async def test_a_name_kafka_keeps_for_itself_is_refused() -> None:
    with pytest.raises(ValueError):
        await _action("new_topic").perform("topics", {"name": "_mine"})
    with pytest.raises(ValueError):
        await _action("new_topic").perform("topics", {"name": "a b"})


async def test_settings_open_with_what_the_topic_has_and_change_one_by_one(
    scratch: str,
) -> None:
    await _make_topic(scratch, settings="retention.ms=3600000\ncleanup.policy=delete")
    action = _action("change_topic_settings")
    hints = await action.field_hints(f"topic:{scratch}")  # type: ignore[attr-defined]  # offers hints
    assert hints.values["settings"] == "cleanup.policy=delete\nretention.ms=3600000"
    params = {"settings": "retention.ms=7200000"}
    preview = await action.preview(f"topic:{scratch}", params)
    assert preview.items == [
        "retention.ms=7200000",
        "cleanup.policy returns to the broker's default",
    ]
    await action.perform(f"topic:{scratch}", params)
    summary = (await adapter().node_summary(f"topic:{scratch}")).contents
    assert isinstance(summary, KafkaTopicContents)
    assert [(one.name, one.value) for one in summary.settings] == [
        ("retention.ms", "7200000")
    ]
    unchanged = await action.preview(f"topic:{scratch}", params)
    assert unchanged.blocked


async def test_partitions_are_added_and_never_taken_away(scratch: str) -> None:
    await _make_topic(scratch, partitions=2)
    action = _action("add_partitions")
    fewer = await action.preview(f"topic:{scratch}", {"total": 2})
    assert fewer.blocked
    with pytest.raises(ActionRefused):
        await action.perform(f"topic:{scratch}", {"total": 1})
    await action.perform(f"topic:{scratch}", {"total": 4})
    node = (await adapter().path_to(f"topic:{scratch}"))[-1]
    assert getattr(node, "partitions", None) == 4


async def test_messages_before_a_time_are_deleted_and_the_rest_kept(
    scratch: str,
) -> None:
    await _make_topic(scratch)
    await adapter().insert_rows(
        InsertRowsRequest(
            node_id=f"topic:{scratch}",
            columns=["timestamp", "value"],
            rows=[
                ["2024-01-01T00:00:00Z", "old"],
                ["2024-01-02T00:00:00Z", "old"],
                ["2025-01-01T00:00:00Z", "new"],
            ],
        )
    )
    action = _action("delete_records")
    params = {"before": "2024-06-01T00:00:00Z"}
    preview = await action.preview(f"topic:{scratch}", params)
    assert preview.items == ["Partition 0: 2 messages"]
    await action.perform(f"topic:{scratch}", params)
    page = await adapter().fetch(FetchRequest(node_id=f"topic:{scratch}"))
    assert [row[4] for row in page.rows] == ["new"]
    with pytest.raises(ValueError):
        await action.perform(f"topic:{scratch}", {"before": "last week"})


async def test_a_deleted_topic_is_gone_and_its_readers_were_named(
    made: tuple[str, str],
) -> None:
    topic, group = made
    preview = await _action("delete_topic").preview(f"topic:{topic}", {})
    # The fixture's messages and the ones the tests above sent.
    count = int(preview.summary.split(" its ")[1].split()[0])
    assert count >= ORDERS + 1
    assert any(group in item for item in preview.items)


async def test_deleting_a_topic_removes_it(scratch: str) -> None:
    await _make_topic(scratch)
    await _action("delete_topic").perform(f"topic:{scratch}", {})
    assert scratch not in await on_server(topics)


# --- groups (D309) --------------------------------------------------------------------


async def test_a_group_s_positions_move_to_the_start_and_back(
    made: tuple[str, str],
) -> None:
    topic, group = made
    action = _action("move_group_positions")
    hints = await action.field_hints(f"group:{group}")  # type: ignore[attr-defined]  # offers hints
    assert [choice.value for choice in hints.choices["to"]] == ["start", "end", "time"]
    assert topic in [choice.value for choice in hints.choices["topic"]]

    preview = await action.preview(f"group:{group}", {"to": "start"})
    committed = GROUP_READ[0]
    assert preview.items == [f"{topic} 0: {committed} → 0, {committed + 1} behind"]
    await action.perform(f"group:{group}", {"to": "start"})
    rows = (await adapter().fetch(FetchRequest(node_id=f"group:{group}"))).rows
    assert [row[2] for row in rows] == ["0"]

    await action.perform(f"group:{group}", {"to": "end", "topic": topic})
    rows = (await adapter().fetch(FetchRequest(node_id=f"group:{group}"))).rows
    assert len(rows) == PARTITIONS
    assert {row[4] for row in rows} == {"0"}

    await action.perform(
        f"group:{group}", {"to": "time", "at": "2023-11-14T22:13:20Z", "topic": topic}
    )
    rows = (await adapter().fetch(FetchRequest(node_id=f"group:{group}"))).rows
    assert {row[2] for row in rows} == {"0"}


async def test_a_time_is_needed_to_move_to_one(made: tuple[str, str]) -> None:
    with pytest.raises(ValueError):
        await _action("move_group_positions").perform(
            f"group:{made[1]}", {"to": "time"}
        )
    with pytest.raises(ValueError):
        await _action("move_group_positions").perform(
            f"group:{made[1]}", {"to": "nowhere"}
        )
