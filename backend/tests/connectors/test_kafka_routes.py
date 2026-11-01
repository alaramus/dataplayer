"""A Kafka connection through the routes a screen calls (D304–D306).

The adapter is tested on its own in tests/adapters/test_kafka.py; this is the
same cluster reached the way the catalog, the grid and the details panel
reach it.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.adapters.kafka_fixture import bootstrap, make, names, on_server, remove

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture(scope="module")
async def made() -> AsyncIterator[tuple[str, str]]:
    topic, group = names()
    await on_server(lambda: make(topic, group))
    yield topic, group
    await on_server(lambda: remove(topic, group))


async def test_a_connection_is_checked_browsed_and_read(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    made: tuple[str, str],
) -> None:
    topic, group = made
    headers = normal_user_token_headers
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"kafka {uuid.uuid4()}",
            "adapter_type": "kafka",
            "options": {"auth_method": "none", "bootstrap_servers": bootstrap()},
        },
    )
    assert response.status_code == 200, response.text
    connector = response.json()["id"]

    async def call(method: str, path: str, **kwargs: Any) -> Any:
        response = await client.request(
            method, f"{BASE}/{connector}/{path}", headers=headers, **kwargs
        )
        assert response.status_code == 200, response.text
        return response.json()

    assert (await call("POST", "check", json={}))["ok"]

    top = [node["id"] for node in await call("GET", "catalog")]
    assert top == ["topics", "groups", "internal"]
    listed = {
        node["name"]: node
        for node in await call("GET", "catalog", params={"node_id": "topics"})
    }
    assert listed[topic]["kind"] == "topic"

    page = await call("POST", "fetch", json={"node_id": f"topic:{topic}", "limit": 3})
    assert page["columns"][0]["name"] == "partition"
    assert page["row_handles"][0].count(":") == 1

    summary = await call("GET", "node-summary", params={"node_id": f"topic:{topic}"})
    assert summary["contents"]["kind"] == "kafka_topic"

    positions = await call("POST", "fetch", json={"node_id": f"group:{group}"})
    assert positions["rows"][0][0] == topic

    missing = await client.post(
        f"{BASE}/{connector}/fetch",
        headers=headers,
        json={"node_id": f"topic:{topic}.missing"},
    )
    assert missing.status_code == 404


async def test_the_options_refuse_a_broker_without_a_port(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": f"kafka {uuid.uuid4()}",
            "adapter_type": "kafka",
            "options": {
                "auth_method": "none",
                "bootstrap_servers": "kafka.example.com",
            },
        },
    )
    assert response.status_code == 422
