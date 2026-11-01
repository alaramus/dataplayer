"""Kafka's reports, metrics, search, kept names and export (D310)."""

from collections.abc import AsyncIterator

import pytest

from app.adapters.catalog import ReportNode
from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest, InFilter, ScalarFilter, Sort
from app.adapters.kafka.metrics import PRESETS
from app.adapters.kafka.reports import REPORTS
from app.adapters.protocol import NodeNotFound
from app.adapters.search import NodeSearchRequest, SearchBounds
from tests.adapters.kafka_fixture import (
    GROUP_READ,
    ORDERS,
    PARTITIONS,
    adapter,
    make,
    names,
    on_server,
    remove,
)


@pytest.fixture(scope="module")
async def made() -> AsyncIterator[tuple[str, str]]:
    topic, group = names()
    await on_server(lambda: make(topic, group))
    yield topic, group
    await on_server(lambda: remove(topic, group))


def _bounds() -> SearchBounds:
    return SearchBounds.within(30)


# --- reports -----------------------------------------------------------------------


async def test_the_cluster_section_holds_its_reports() -> None:
    section = await adapter().list_children("cluster")
    assert [node.id for node in section] == [report.node_id for report in REPORTS]
    assert all(isinstance(node, ReportNode) and node.description for node in section)
    assert [node.id for node in await adapter().path_to("report:brokers")] == [
        "cluster",
        "report:brokers",
    ]
    with pytest.raises(NodeNotFound):
        await adapter().fetch(FetchRequest(node_id="report:nothing"))


async def test_the_cluster_report_counts_brokers_topics_and_partitions(
    made: tuple[str, str],
) -> None:
    del made  # a topic of known partitions exists while the report is read
    rows = dict((await adapter().fetch(FetchRequest(node_id="report:cluster"))).rows)
    assert rows["Brokers"] == "1"
    assert int(rows["Topics"] or 0) >= 2
    assert int(rows["Partitions"] or 0) >= PARTITIONS
    assert rows["Partitions without a leader"] == "0"


async def test_every_broker_is_a_row_and_the_controller_is_marked() -> None:
    page = await adapter().fetch(FetchRequest(node_id="report:brokers"))
    assert len(page.rows) >= 1
    assert any("controller" in (value or "") for _, value in page.rows)
    assert not page.insert_supported


async def test_broker_settings_are_the_ones_set_and_secrets_hidden() -> None:
    rows = dict(
        (await adapter().fetch(FetchRequest(node_id="report:broker-settings"))).rows
    )
    assert "advertised.listeners" in rows
    # The test broker's SASL users are in its JAAS line, which Kafka keeps secret.
    secret = [value for name, value in rows.items() if "jaas" in name]
    assert all(value == "hidden by the broker" for value in secret)


async def test_a_healthy_cluster_has_no_partition_needing_attention() -> None:
    page = await adapter().fetch(FetchRequest(node_id="report:attention"))
    assert page.rows == []


# --- metrics ---------------------------------------------------------------------------


async def test_metrics_are_lag_by_group_growth_by_topic_and_health(
    made: tuple[str, str],
) -> None:
    topic, group = made
    samples = {
        (one.metric, one.field, one.label): one
        for one in await adapter().metric_samples()
    }
    produced = samples[("messages", "produced", topic)]
    assert produced.counter and produced.value >= ORDERS + 1
    assert samples[("lag", "messages", group)].value == float(
        # Partition 0 holds a third of the orders and the binary message.
        ORDERS // PARTITIONS + 1 - GROUP_READ[0]
    )
    assert samples[("cluster", "offline", "")].value == 0.0
    assert not any(label.startswith("_") for _, _, label in samples)


def test_the_preset_draws_what_is_measured() -> None:
    [preset] = PRESETS
    assert {recipe.metric for recipe in preset.recipes} == {
        "lag",
        "cluster",
        "messages",
    }


# --- search and kept names ----------------------------------------------------------------


async def test_topics_and_groups_are_found_by_name_where_they_lie(
    made: tuple[str, str],
) -> None:
    topic, group = made
    run = topic.split(".")[1]
    result = await adapter().search_nodes(NodeSearchRequest(query=run))
    found = {(match.node.kind, match.parent_id) for match in result.matches}
    assert found == {("topic", "topics"), ("consumer_group", "groups")}
    [topic_match] = [match for match in result.matches if match.node.kind == "topic"]
    assert getattr(topic_match.node, "messages", None) == ORDERS + 1
    assert result.complete


async def test_a_search_on_a_level_stays_on_it(made: tuple[str, str]) -> None:
    run = made[0].split(".")[1]
    result = await adapter().search_nodes(
        NodeSearchRequest(query=run, node_id="groups")
    )
    assert [match.node.kind for match in result.matches] == ["consumer_group"]


async def test_every_name_is_kept_scoped_to_its_level(made: tuple[str, str]) -> None:
    topic, group = made
    kept = [
        name
        async for batch in adapter().enumerate_names(10_000, _bounds())
        for name in batch.names
    ]
    scopes = {name.node.name: name.scope for name in kept}
    assert scopes[topic] == "topics"
    assert scopes[group] == "groups"
    assert scopes["__consumer_offsets"] == "internal"


# --- export ----------------------------------------------------------------------------------


async def test_a_topic_exports_what_its_page_would_show(made: tuple[str, str]) -> None:
    topic = made[0]
    request = ExportRequest(
        node_id=f"topic:{topic}",
        columns=["partition", "value.side"],
        filters=[
            InFilter(column="partition", op="in", values=["1"]),
            ScalarFilter(column="value.side", op="eq", value="buy"),
        ],
        sort=[Sort(column="timestamp")],
    )
    rows = [row async for batch in adapter().export_rows(request) for row in batch.rows]
    # Partition 1 holds the orders 1, 4, 7 …; every other one of them is odd.
    assert len(rows) == ORDERS // PARTITIONS // 2
    assert {tuple(row) for row in rows} == {("1", "buy")}
    with pytest.raises(ValueError):
        [
            row
            async for batch in adapter().export_rows(
                ExportRequest(node_id=f"topic:{topic}", columns=["nope"])
            )
            for row in batch.rows
        ]


async def test_a_group_exports_every_position(made: tuple[str, str]) -> None:
    group = made[1]
    rows = [
        row
        async for batch in adapter().export_rows(
            ExportRequest(node_id=f"group:{group}", columns=["partition", "committed"])
        )
        for row in batch.rows
    ]
    assert rows == [["0", str(GROUP_READ[0])]]


async def test_a_report_exports_its_rows() -> None:
    rows = [
        row
        async for batch in adapter().export_rows(
            ExportRequest(node_id="report:cluster", columns=["Setting"])
        )
        for row in batch.rows
    ]
    assert ["Brokers"] in rows
