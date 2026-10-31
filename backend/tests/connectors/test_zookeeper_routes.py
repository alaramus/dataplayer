"""A ZooKeeper connection through the routes a screen calls (D297, D298).

The adapter is tested on its own in tests/adapters/test_zookeeper.py; this is
the same server reached the way the catalog, the editor and the details panel
reach it.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.adapters.zookeeper_fixture import (
    address,
    build_tree,
    new_root,
    on_server,
    remove_tree,
)

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture(scope="module")
async def root() -> AsyncIterator[str]:
    path = new_root()
    await on_server(lambda client: build_tree(client, path))
    yield path
    await on_server(lambda client: remove_tree(client, path))


async def _connector(client: AsyncClient, headers: dict[str, str], chroot: str) -> str:
    host, port = address()
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"zookeeper {uuid.uuid4()}",
            "adapter_type": "zookeeper",
            "options": {
                "auth_method": "anonymous",
                "host": host,
                "port": port,
                "chroot": chroot,
            },
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def test_a_connection_is_checked_browsed_read_and_edited(
    client: AsyncClient, normal_user_token_headers: dict[str, str], root: str
) -> None:
    headers = normal_user_token_headers
    connector = await _connector(client, headers, root)

    async def call(method: str, path: str, **kwargs: Any) -> Any:
        response = await client.request(
            method, f"{BASE}/{connector}/{path}", headers=headers, **kwargs
        )
        assert response.status_code == 200, response.text
        return response.json()

    assert (await call("POST", "check", json={}))["ok"]

    top = {node["name"]: node for node in await call("GET", "catalog")}
    assert top["config"]["kind"] == "znode"
    assert top["services"]["has_children"] is True
    assert top["secret"]["readable"] is False

    page = await call("POST", "fetch", json={"node_id": "/services", "limit": 5})
    assert [row[0] for row in page["rows"]] == [
        f"item-{index:02d}" for index in range(5)
    ]

    summary = await call("GET", "node-summary", params={"node_id": "/services"})
    assert summary["contents"]["kind"] == "znode"
    assert summary["contents"]["acl"][0]["scheme"] == "world"

    tree = await call(
        "POST", "content", json={"node_id": "/config", "representation": "tree"}
    )
    assert tree["kind"] == "json" and tree["value"]["kind"] == "object"

    editor = await call("POST", "content/editor", json={"node_id": "/text"})
    saved = await call(
        "PATCH",
        "content/editor",
        json={"node_id": "/text", "text": "new words", "version": editor["version"]},
    )
    assert saved["version"] != editor["version"]
    stale = await client.patch(
        f"{BASE}/{connector}/content/editor",
        headers=headers,
        json={"node_id": "/text", "text": "late", "version": editor["version"]},
    )
    assert stale.status_code == 409

    missing = await client.get(
        f"{BASE}/{connector}/catalog", headers=headers, params={"node_id": "/gone"}
    )
    assert missing.status_code == 422

    features = await call("GET", "features")
    assert features["server_version"].startswith("ZooKeeper ")


async def test_a_connect_string_fills_the_form(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/parse-url",
        headers=normal_user_token_headers,
        json={"adapter_type": "zookeeper", "url": "zk.example.com:2181/apps"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["options"]["chroot"] == "/apps"


async def test_znodes_are_made_and_deleted_through_the_routes(
    client: AsyncClient, normal_user_token_headers: dict[str, str], root: str
) -> None:
    headers = normal_user_token_headers
    connector = await _connector(client, headers, root)

    offered = await client.post(
        f"{BASE}/{connector}/actions", headers=headers, json={}
    )
    assert offered.status_code == 200, offered.text
    names = {action["name"] for action in offered.json()}
    assert {"new_top_znode", "new_child_znode", "delete_subtree", "change_acl"} <= names

    made = await client.post(
        f"{BASE}/{connector}/actions/new_child_znode",
        headers=headers,
        json={"node_id": "/services", "params": {"name": "via-route", "data": "x"}},
    )
    assert made.status_code == 200, made.text
    assert made.json()["created_node_id"] == "/services/via-route"

    hints = await client.post(
        f"{BASE}/{connector}/actions/change_acl/hints",
        headers=headers,
        json={"node_id": "/services/via-route", "params": {}},
    )
    assert hints.status_code == 200, hints.text
    assert hints.json()["values"]["acl"] == "world:anyone:cdrwa"

    gone = await client.post(
        f"{BASE}/{connector}/actions/delete_znode",
        headers=headers,
        json={"node_id": "/services/via-route", "params": {}},
    )
    assert gone.status_code == 200, gone.text


async def test_a_screen_says_what_it_shows_and_may_stop(
    client: AsyncClient, normal_user_token_headers: dict[str, str], root: str
) -> None:
    """The watch itself is tested in tests/adapters/test_zookeeper_watch.py (D303)."""
    headers = normal_user_token_headers
    connector = await _connector(client, headers, root)

    followed = await client.post(
        f"{BASE}/{connector}/changes/follow",
        headers=headers,
        json={"node_ids": [None, "/services"]},
    )
    assert followed.status_code == 204, followed.text
    stopped = await client.post(
        f"{BASE}/{connector}/changes/follow", headers=headers, json={"node_ids": []}
    )
    assert stopped.status_code == 204, stopped.text

    types = await client.get(f"{settings.API_V1_STR}/adapter-types/", headers=headers)
    [zookeeper] = [one for one in types.json() if one["name"] == "zookeeper"]
    assert "live_changes" in {one["code"] for one in zookeeper["capabilities"]}
    [redis] = [one for one in types.json() if one["name"] == "redis"]
    assert "live_changes" not in {one["code"] for one in redis["capabilities"]}
