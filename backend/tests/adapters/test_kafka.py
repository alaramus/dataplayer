"""Kafka as a source: reaching it, its catalog, a topic's messages and a group's positions (D304–D306)."""

from collections.abc import AsyncIterator

import pytest

from app.adapters.catalog import ConsumerGroupNode, DirectoryNode, TopicNode
from app.adapters.fetch import FetchRequest, InFilter, NullFilter, ScalarFilter, Sort
from app.adapters.kafka.messages import DEPTH_CEILING
from app.adapters.kafka.options import KafkaNoAuth, KafkaPlain, checked_servers
from app.adapters.kafka.session import BROWSING_GROUP
from app.adapters.protocol import NodeNotFound
from app.adapters.summary import KafkaGroupContents, KafkaTopicContents
from tests.adapters.kafka_fixture import (
    GROUP_READ,
    ORDERS,
    PARTITIONS,
    SASL_PASSWORD,
    SASL_USER,
    adapter,
    groups,
    make,
    names,
    on_server,
    remove,
    sasl_bootstrap,
    topics,
)


@pytest.fixture(scope="module")
async def made() -> AsyncIterator[tuple[str, str]]:
    topic, group = names()
    await on_server(lambda: make(topic, group))
    yield topic, group
    await on_server(lambda: remove(topic, group))


@pytest.fixture
def topic(made: tuple[str, str]) -> str:
    return made[0]


@pytest.fixture
def group(made: tuple[str, str]) -> str:
    return made[1]


async def _page(
    request: FetchRequest,
) -> tuple[list[str], list[list[str | None]], bool]:
    result = await adapter().fetch(request)
    return [column.name for column in result.columns], result.rows, result.has_more


# --- reaching it (D304) -------------------------------------------------------


async def test_a_connection_is_checked() -> None:
    result = await adapter().check_connection()
    assert result.ok, result.message
    assert result.latency_ms is not None


async def test_a_broker_that_does_not_answer_is_a_network_failure() -> None:
    result = await adapter(
        KafkaNoAuth(bootstrap_servers="127.0.0.1:9")
    ).check_connection()
    assert not result.ok
    assert result.error_kind == "network"
    assert "127.0.0.1" not in result.message


async def test_a_sasl_user_is_let_in() -> None:
    options = KafkaPlain(
        bootstrap_servers=sasl_bootstrap(), user=SASL_USER, password=SASL_PASSWORD
    )
    result = await adapter(options).check_connection()
    assert result.ok, result.message


async def test_a_wrong_password_is_refused_as_such_and_never_repeated() -> None:
    options = KafkaPlain(
        bootstrap_servers=sasl_bootstrap(), user=SASL_USER, password="not-the-password"
    )
    result = await adapter(options).check_connection()
    assert not result.ok
    assert result.error_kind == "auth"
    assert "not-the-password" not in result.message


def test_brokers_are_host_and_port_pairs() -> None:
    assert checked_servers(" a:9092 , b:9093,") == "a:9092,b:9093"
    for wrong in ["", "a", "a:port", "a:0", "a:70000", "kafka://a:9092", ":9092"]:
        with pytest.raises(ValueError):
            checked_servers(wrong)


# --- the catalog (D305) -------------------------------------------------------


async def test_the_top_is_topics_groups_and_internal_topics() -> None:
    top = await adapter().list_children(None)
    assert [node.id for node in top] == ["topics", "groups", "internal"]
    assert all(isinstance(node, DirectoryNode) for node in top)


async def test_a_topic_is_listed_with_its_partitions_and_messages(topic: str) -> None:
    listed = {node.name: node for node in await adapter().list_children("topics")}
    node = listed[topic]
    assert isinstance(node, TopicNode)
    assert node.partitions == PARTITIONS
    assert node.messages == ORDERS + 1
    assert node.summarizable
    assert not any(name.startswith("_") for name in listed)


async def test_kafka_s_own_topics_are_kept_apart(topic: str) -> None:
    internal = [node.name for node in await adapter().list_children("internal")]
    assert "__consumer_offsets" in internal
    assert topic not in internal


async def test_a_group_is_listed_with_its_state(group: str) -> None:
    listed = {node.name: node for node in await adapter().list_children("groups")}
    node = listed[group]
    assert isinstance(node, ConsumerGroupNode)
    assert node.state == "empty"
    assert node.members == 0


async def test_a_topic_is_found_under_its_level(topic: str) -> None:
    path = await adapter().path_to(f"topic:{topic}")
    assert [node.id for node in path] == ["topics", f"topic:{topic}"]


async def test_a_name_that_is_not_a_topic_is_refused() -> None:
    for wrong in ["topic:", "topic:a b", "topic:" + "x" * 250, "other"]:
        with pytest.raises(ValueError):
            await adapter().list_children(wrong)


# --- a topic's messages (D306) ------------------------------------------------


async def test_the_newest_messages_come_first_across_partitions(topic: str) -> None:
    columns, rows, has_more = await _page(
        FetchRequest(node_id=f"topic:{topic}", limit=4)
    )
    assert columns[:6] == [
        "partition",
        "offset",
        "timestamp",
        "key",
        "value",
        "headers",
    ]
    assert columns[6:] == ["value.id", "value.price", "value.side"]
    assert has_more
    newest, *orders = rows
    assert newest[2] == "2023-11-14T22:15:00.000Z"
    assert newest[3] == "0xff00"
    assert newest[6:] == [None, None, None]
    assert [row[6] for row in orders] == [
        str(ORDERS - 1),
        str(ORDERS - 2),
        str(ORDERS - 3),
    ]
    assert orders[0][5] == '{"source": "fixture"}'
    assert orders[0][8] == "buy"


async def test_a_page_further_on_continues_where_the_last_stopped(topic: str) -> None:
    _, first, _ = await _page(FetchRequest(node_id=f"topic:{topic}", limit=10))
    _, second, _ = await _page(
        FetchRequest(node_id=f"topic:{topic}", limit=10, offset=10)
    )
    seen = {(row[0], row[1]) for row in first}
    assert not seen & {(row[0], row[1]) for row in second}
    assert second[0][2] is not None and first[-1][2] is not None
    assert second[0][2] <= first[-1][2]


async def test_the_oldest_come_first_when_asked(topic: str) -> None:
    _, rows, _ = await _page(
        FetchRequest(node_id=f"topic:{topic}", limit=3, sort=[Sort(column="timestamp")])
    )
    assert [row[6] for row in rows] == ["0", "1", "2"]


async def test_messages_are_ordered_by_time_and_nothing_else(topic: str) -> None:
    with pytest.raises(ValueError):
        await adapter().fetch(
            FetchRequest(node_id=f"topic:{topic}", sort=[Sort(column="offset")])
        )


async def test_a_partition_is_read_alone(topic: str) -> None:
    _, rows, _ = await _page(
        FetchRequest(
            node_id=f"topic:{topic}",
            limit=50,
            filters=[InFilter(column="partition", op="in", values=["1"])],
        )
    )
    assert {row[0] for row in rows} == {"1"}
    assert len(rows) == ORDERS // PARTITIONS


async def test_reading_starts_at_a_time(topic: str) -> None:
    _, rows, _ = await _page(
        FetchRequest(
            node_id=f"topic:{topic}",
            limit=50,
            sort=[Sort(column="timestamp")],
            filters=[
                ScalarFilter(column="timestamp", op="gte", value="2023-11-14T22:14:10Z")
            ],
        )
    )
    # 22:13:20 is T0, so ten seconds before the last order and the binary one.
    assert rows[0][6] == str(ORDERS - 10)
    assert len(rows) == 11


async def test_reading_stops_at_an_offset(topic: str) -> None:
    _, rows, _ = await _page(
        FetchRequest(
            node_id=f"topic:{topic}",
            limit=50,
            filters=[
                ScalarFilter(column="partition", op="eq", value="2"),
                ScalarFilter(column="offset", op="lt", value="5"),
            ],
        )
    )
    assert [row[1] for row in rows] == ["4", "3", "2", "1", "0"]


async def test_a_field_of_the_values_filters_what_was_read(topic: str) -> None:
    _, rows, _ = await _page(
        FetchRequest(
            node_id=f"topic:{topic}",
            limit=50,
            filters=[
                ScalarFilter(column="value.price", op="gte", value="80"),
                ScalarFilter(column="value.side", op="eq", value="sell"),
            ],
        )
    )
    assert [row[6] for row in rows] == ["58", "56", "54"]


async def test_text_is_looked_for_without_regard_to_case(topic: str) -> None:
    _, rows, _ = await _page(
        FetchRequest(
            node_id=f"topic:{topic}",
            limit=50,
            filters=[ScalarFilter(column="value", op="contains", value="NOT JSON")],
        )
    )
    assert len(rows) == 1 and rows[0][3] == "0xff00"
    _, keyless, _ = await _page(
        FetchRequest(
            node_id=f"topic:{topic}",
            filters=[NullFilter(column="headers", op="is_null")],
        )
    )
    assert [row[3] for row in keyless] == ["0xff00"]


async def test_a_filter_on_an_unknown_column_is_refused(topic: str) -> None:
    for wrong in [
        ScalarFilter(column="value.nope", op="eq", value="1"),
        ScalarFilter(column="partition", op="contains", value="1"),
        ScalarFilter(column="timestamp", op="gte", value="yesterday"),
        ScalarFilter(column="value.price", op="gt", value="cheap"),
    ]:
        with pytest.raises(ValueError):
            await adapter().fetch(
                FetchRequest(node_id=f"topic:{topic}", filters=[wrong])
            )


async def test_a_page_does_not_reach_past_its_depth(topic: str) -> None:
    with pytest.raises(ValueError):
        await adapter().fetch(
            FetchRequest(node_id=f"topic:{topic}", limit=100, offset=DEPTH_CEILING)
        )


async def test_reading_a_topic_leaves_no_group_behind(topic: str) -> None:
    await adapter().fetch(FetchRequest(node_id=f"topic:{topic}", limit=5))
    assert BROWSING_GROUP not in await on_server(groups)


async def test_a_topic_that_is_not_there_is_not_made_by_asking(
    made: tuple[str, str],
) -> None:
    missing = made[0] + ".missing"
    with pytest.raises(NodeNotFound):
        await adapter().fetch(FetchRequest(node_id=f"topic:{missing}"))
    with pytest.raises(NodeNotFound):
        await adapter().node_summary(f"topic:{missing}")
    assert missing not in await on_server(topics)


async def test_a_topic_summary_shows_its_partitions_and_own_settings(
    topic: str,
) -> None:
    summary = await adapter().node_summary(f"topic:{topic}")
    contents = summary.contents
    assert isinstance(contents, KafkaTopicContents)
    assert contents.messages == ORDERS + 1
    assert [one.partition for one in contents.partitions] == list(range(PARTITIONS))
    first = contents.partitions[0]
    assert first.leader is not None and first.in_sync == [first.leader]
    assert (first.first_offset, first.end_offset) == (0, ORDERS // PARTITIONS + 1)
    assert [(one.name, one.value) for one in contents.settings] == [
        ("retention.ms", "-1")
    ]


# --- a group's positions (D305) -----------------------------------------------


async def test_a_group_shows_where_it_stands_and_how_far_behind(group: str) -> None:
    result = await adapter().fetch(FetchRequest(node_id=f"group:{group}"))
    committed = GROUP_READ[0]
    assert [row[1:5] for row in result.rows] == [
        ["0", str(committed), str(committed + 1), "1"]
    ]
    assert result.refresh_seconds is not None


async def test_a_group_summary_sums_its_lag(topic: str, group: str) -> None:
    summary = await adapter().node_summary(f"group:{group}")
    contents = summary.contents
    assert isinstance(contents, KafkaGroupContents)
    assert contents.state == "empty"
    assert contents.members == 0
    assert contents.topics == [topic]
    assert contents.lag == 1


async def test_a_group_that_is_not_there_is_a_missing_node() -> None:
    with pytest.raises(NodeNotFound):
        await adapter().fetch(FetchRequest(node_id="group:dp-test-nobody-ever"))
