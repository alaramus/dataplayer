"""A RabbitMQ connection through the routes a screen calls (D325–D327).

The adapter is tested on its own in tests/adapters/test_rabbitmq.py; this is
the same broker reached the way the catalog, the grid and the details panel
reach it.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.adapters.rabbitmq_fixture import (
    QUEUE,
    STREAM,
    amqp_host,
    amqp_port,
    make,
    management,
    names,
    password,
    remove,
    user,
)

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture(scope="module")
async def vhost() -> AsyncIterator[str]:
    made = names()
    await make(made)
    yield made
    await remove(made)


async def test_a_connection_is_checked_browsed_and_read(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    vhost: str,
) -> None:
    headers = normal_user_token_headers
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"rabbitmq {uuid.uuid4()}",
            "adapter_type": "rabbitmq",
            "options": {
                "host": amqp_host(),
                "port": amqp_port(),
                "management_url": management(),
                "user": user(),
                "password": password(),
                "vhost": vhost,
            },
        },
    )
    assert response.status_code == 200, response.text
    connector = response.json()["id"]
    assert "password" not in response.json()["config"]

    async def call(method: str, path: str, **kwargs: Any) -> Any:
        response = await client.request(
            method, f"{BASE}/{connector}/{path}", headers=headers, **kwargs
        )
        assert response.status_code == 200, response.text
        return response.json()

    assert (await call("POST", "check", json={}))["ok"]

    v = quote(vhost, safe="")
    top = [node["id"] for node in await call("GET", "catalog")]
    assert top == ["broker", f"queues:{v}", f"streams:{v}", f"exchanges:{v}"]
    streams = await call("GET", "catalog", params={"node_id": f"streams:{v}"})
    assert [node["kind"] for node in streams] == ["amqp_stream"]
    stream = streams[0]["id"]

    page = await call("POST", "fetch", json={"node_id": stream, "limit": 3})
    assert page["columns"][0]["name"] == "offset"
    assert page["row_handles"][0].isdigit()
    # A message is sent as a new row of a stream (D329).
    assert page["insert_supported"]

    summary = await call("GET", "node-summary", params={"node_id": stream})
    assert summary["contents"]["kind"] == "amqp_stream"
    assert summary["name"] == STREAM

    queue = f"queue:{v}/{quote(QUEUE, safe='')}"
    bindings = await call("POST", "fetch", json={"node_id": queue})
    assert bindings["columns"][0]["name"] == "exchange"
    summary = await call("GET", "node-summary", params={"node_id": queue})
    assert summary["contents"]["kind"] == "amqp_queue"


async def test_a_stream_that_is_not_there_is_a_404(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    headers = normal_user_token_headers
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"rabbitmq {uuid.uuid4()}",
            "adapter_type": "rabbitmq",
            "options": {
                "host": amqp_host(),
                "port": amqp_port(),
                "management_url": management(),
                "user": user(),
                "password": password(),
            },
        },
    )
    assert response.status_code == 200, response.text
    connector = response.json()["id"]
    response = await client.post(
        f"{BASE}/{connector}/fetch",
        headers=headers,
        json={"node_id": "stream:%2F/no-such-stream"},
    )
    assert response.status_code == 404, response.text
