"""RabbitMQ's reports, metrics and search (D331)."""

import asyncio
import time
from collections.abc import AsyncIterator
from urllib.parse import quote

import aio_pika
import pytest

from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import NodeNotFound
from app.adapters.rabbitmq.metrics import PRESETS
from app.adapters.rabbitmq.reports import REPORTS
from app.adapters.search import NodeSearchRequest, SearchBounds
from tests.adapters.rabbitmq_fixture import (
    EXCHANGE,
    QUEUE,
    QUORUM,
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


# --- reports ---------------------------------------------------------------------------


async def test_the_broker_section_holds_every_report() -> None:
    reports = await adapter().list_children("broker")
    assert [node.id for node in reports] == [report.node_id for report in REPORTS]
    assert all(node.kind == "report" and not node.has_children for node in reports)
    path = await adapter().path_to("report:nodes")
    assert [node.id for node in path] == ["broker", "report:nodes"]
    with pytest.raises(NodeNotFound):
        await adapter().path_to("report:nothing")


async def test_the_overview_names_the_release_and_counts() -> None:
    page = await adapter().fetch(FetchRequest(node_id="report:overview"))
    rows = {row[0]: row[1] for row in page.rows}
    assert (rows["Release"] or "").startswith("RabbitMQ 4.")
    assert rows["Queues"] not in {None, "—"}
    assert page.refresh_seconds == 10
    assert [column.name for column in page.columns] == ["Setting", "Value"]


async def test_each_node_says_its_memory_and_disk() -> None:
    page = await adapter().fetch(FetchRequest(node_id="report:nodes"))
    assert page.rows
    assert all("memory" in (row[1] or "") for row in page.rows)


async def test_no_alarm_is_an_empty_report() -> None:
    page = await adapter().fetch(FetchRequest(node_id="report:alarms"))
    assert page.rows == []


async def test_an_open_connection_and_its_channel_are_listed(vhost: str) -> None:
    connection = await aio_pika.connect(
        host=amqp_host(),
        port=amqp_port(),
        login=user(),
        password=password(),
        virtualhost=vhost,
        client_properties={"connection_name": "dp-reports-test"},
    )
    async with connection:
        await connection.channel()
        # The management API learns of a connection with its next sample.
        deadline = time.monotonic() + 20
        connections: list[list[str | None]] = []
        while time.monotonic() < deadline:
            page = await adapter().fetch(FetchRequest(node_id="report:connections"))
            connections = [row for row in page.rows if vhost in (row[1] or "")]
            # Its channels and state come with a later sample than its name.
            if connections and "1 channels" in (connections[0][1] or ""):
                break
            await asyncio.sleep(1)
        assert connections
        assert "1 channels" in (connections[0][1] or "")
        channels = await adapter().fetch(FetchRequest(node_id="report:channels"))
        assert any(vhost in (row[1] or "") for row in channels.rows)


async def test_a_report_is_exported() -> None:
    rows = [
        row
        async for batch in adapter().export_rows(
            ExportRequest(node_id="report:overview", columns=["Setting", "Value"])
        )
        for row in batch.rows
    ]
    assert rows[0][0] == "Release"


# --- metrics ---------------------------------------------------------------------------


async def test_the_broker_and_each_queue_are_measured(vhost: str) -> None:
    samples = await adapter(options(vhost)).metric_samples()
    by = {(one.metric, one.field, one.label): one for one in samples}
    assert ("broker", "queues", "") in by
    assert ("broker", "alarms", "") in by
    assert by[("messages", "publish", "")].counter
    assert by[("queue", "ready", f"{vhost}/{QUEUE}")].value == WAITING
    assert ("queue", "unacknowledged", f"{vhost}/{QUORUM}") in by
    assert ("queue", "stream", f"{vhost}/{STREAM}") in by


def test_the_preset_draws_what_is_measured() -> None:
    [preset] = PRESETS
    drawn = {
        (recipe.metric, field)
        for recipe in preset.recipes
        for field in recipe.fields or ()
    }
    assert drawn >= {
        ("queue", "ready"),
        ("broker", "connections"),
        ("messages", "publish"),
    }


# --- search ----------------------------------------------------------------------------


async def test_names_are_found_with_where_they_are(vhost: str) -> None:
    found = await adapter().search_nodes(NodeSearchRequest(query=QUEUE))
    match = next(
        one for one in found.matches if one.node.id.endswith(f"{_v(vhost)}/{QUEUE}")
    )
    assert match.parent_id == f"queues:{_v(vhost)}"
    assert match.location.startswith(vhost)
    assert [one.node_id for one in match.ancestors] == [
        f"vhost:{_v(vhost)}",
        f"queues:{_v(vhost)}",
    ]


async def test_a_search_on_a_level_stays_on_it(vhost: str) -> None:
    found = await adapter(options(vhost)).search_nodes(
        NodeSearchRequest(query="dp", node_id=f"exchanges:{_v(vhost)}")
    )
    assert [one.node.name for one in found.matches] == [EXCHANGE]
    assert found.matches[0].ancestors[0].node_id == f"exchanges:{_v(vhost)}"


async def test_every_name_is_kept_with_its_level(vhost: str) -> None:
    kept = [
        name
        async for batch in adapter(options(vhost)).enumerate_names(
            1000, SearchBounds.within(30)
        )
        for name in batch.names
    ]
    scopes = {name.node.name: name.scope for name in kept}
    assert scopes[QUEUE] == f"queues:{_v(vhost)}"
    assert scopes[STREAM] == f"streams:{_v(vhost)}"
    assert scopes[EXCHANGE] == f"exchanges:{_v(vhost)}"


async def test_an_empty_search_is_refused() -> None:
    with pytest.raises(ValueError):
        await adapter().search_nodes(NodeSearchRequest(query="   "))
