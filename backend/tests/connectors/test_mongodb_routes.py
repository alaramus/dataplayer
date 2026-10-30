"""A MongoDB connection through the routes a screen calls (D283–D285).

The adapter is tested on its own in tests/adapters/test_mongodb.py; this is
the same server reached the way the catalog, the grid and the details panel
reach it, its client kept and its answers cached as they are.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.adapters.database_ids import database_id, relation_id
from app.core.config import settings
from tests.adapters.mongodb_fixture import DATABASE, build, options, tear_down
from tests.utils.services import MONGODB

BASE = f"{settings.API_V1_STR}/connectors"
PEOPLE = relation_id(DATABASE, "people")


@pytest.fixture(scope="module")
async def server() -> AsyncIterator[None]:
    MONGODB.require()
    await build()
    yield
    await tear_down()


async def _connector(client: AsyncClient, headers: dict[str, str]) -> str:
    chosen = options(database=DATABASE)
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"mongodb {uuid.uuid4()}",
            "adapter_type": "mongodb",
            "options": {
                **chosen.model_dump(exclude={"password"}),
                "password": chosen.password.get_secret_value(),
            },
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


@pytest.mark.usefixtures("server")
async def test_a_connection_is_checked_browsed_read_and_described(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    connector = await _connector(client, headers)

    async def get(path: str, **params: Any) -> Any:
        response = await client.get(f"{BASE}/{connector}/{path}", headers=headers, params=params)
        assert response.status_code == 200, response.text
        return response.json()

    async def post(path: str, body: dict[str, Any]) -> Any:
        response = await client.post(f"{BASE}/{connector}/{path}", headers=headers, json=body)
        assert response.status_code == 200, response.text
        return response.json()

    check = await post("check", {})
    assert check["ok"], check

    databases = await get("catalog")
    assert databases[0]["name"] == DATABASE
    collections = await get("catalog", node_id=database_id(DATABASE))
    by_name = {node["name"]: node for node in collections}
    assert by_name["people"]["term"] == "collection"
    assert by_name["adults"]["kind"] == "view"

    page = await post("fetch", {"node_id": PEOPLE, "limit": 2})
    assert [row[1] for row in page["rows"]] == ["Ann", "Bob"]
    assert page["has_more"] is True
    assert page["update_supported"] is True

    model = await get("relation-model", node_id=PEOPLE)
    assert model["columns"][0]["name"] == "_id"
    summary = await get("node-summary", node_id=PEOPLE)
    assert summary["contents"]["schema_name"] == DATABASE
    definition = await post("content", {"node_id": PEOPLE, "representation": "json"})
    assert definition["kind"] == "json"
    features = await get("features")
    assert features["server_version"].startswith("MongoDB ")


@pytest.mark.usefixtures("server")
async def test_a_connection_string_fills_the_form(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/parse-url",
        headers=normal_user_token_headers,
        json={"adapter_type": "mongodb", "url": "mongodb://ann:secret@db.example.com/shop"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["options"]["auth_source"] == "shop"


@pytest.mark.usefixtures("server")
async def test_a_field_is_edited_and_a_document_deleted_through_the_routes(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Named by `_id` and a digest of the document, as the grid sends it back (D287)."""
    headers = normal_user_token_headers
    connector = await _connector(client, headers)
    numbers = relation_id(DATABASE, "numbers")

    page = await client.post(
        f"{BASE}/{connector}/fetch", headers=headers, json={"node_id": numbers, "limit": 2}
    )
    assert page.status_code == 200, page.text
    handles = page.json()["row_handles"]

    edited = await client.patch(
        f"{BASE}/{connector}/rows/cell",
        headers=headers,
        json={"node_id": numbers, "row_handle": handles[0], "column": "label", "value": "first"},
    )
    assert edited.status_code == 200, edited.text
    assert "first" in edited.json()["values"]
    stale = await client.patch(
        f"{BASE}/{connector}/rows/cell",
        headers=headers,
        json={"node_id": numbers, "row_handle": handles[0], "column": "label", "value": "again"},
    )
    assert stale.status_code == 409, stale.text
    deleted = await client.request(
        "DELETE",
        f"{BASE}/{connector}/rows",
        headers=headers,
        json={"node_id": numbers, "row_handles": [handles[1]]},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 1
