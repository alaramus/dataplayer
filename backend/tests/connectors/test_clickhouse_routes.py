"""A ClickHouse connection through the routes a screen calls (D267–D269).

The adapter is tested on its own in tests/adapters/test_clickhouse.py; this is
the same server reached the way the catalog, the grid and the details panel
reach it, its client kept and its answers cached as they are.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.adapters.database_ids import database_id, relation_id
from app.core.config import settings
from tests.adapters.clickhouse_fixture import DATABASE, build, options, tear_down
from tests.utils.services import CLICKHOUSE

BASE = f"{settings.API_V1_STR}/connectors"
ITEMS = relation_id(DATABASE, "items")


@pytest.fixture(scope="module")
async def server() -> AsyncIterator[None]:
    CLICKHOUSE.require()
    await build()
    yield
    await tear_down()


async def _connector(client: AsyncClient, headers: dict[str, str]) -> str:
    chosen = options(database=DATABASE)
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"clickhouse {uuid.uuid4()}",
            "adapter_type": "clickhouse",
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
    relations = await get("catalog", node_id=database_id(DATABASE))
    assert {node["name"] for node in relations} >= {"items", "item_labels"}

    page = await post("fetch", {"node_id": ITEMS, "limit": 2})
    assert [row[0] for row in page["rows"]] == ["1", "2"]
    assert page["has_more"] is True
    assert page["update_supported"] is True

    model = await get("relation-model", node_id=ITEMS)
    assert model["kind"] == "table"
    summary = await get("node-summary", node_id=ITEMS)
    assert summary["contents"]["schema_name"] == DATABASE
    ddl = await post("content", {"node_id": ITEMS, "representation": "sql"})
    assert ddl["text"].startswith("CREATE TABLE")
    features = await get("features")
    assert features["server_version"].startswith("ClickHouse ")


@pytest.mark.usefixtures("server")
async def test_a_cell_is_edited_and_a_row_deleted_through_the_routes(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Named by the whole row, as the grid sends it back (D272)."""
    headers = normal_user_token_headers
    connector = await _connector(client, headers)
    dupes = relation_id(DATABASE, "dupes")

    page = await client.post(
        f"{BASE}/{connector}/fetch", headers=headers, json={"node_id": dupes, "limit": 10}
    )
    assert page.status_code == 200, page.text
    rows = page.json()["rows"]
    handles = page.json()["row_handles"]
    zero = handles[rows.index(["0", "z"])]

    edited = await client.patch(
        f"{BASE}/{connector}/rows/cell",
        headers=headers,
        json={"node_id": dupes, "row_handle": zero, "column": "b", "value": "y"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["values"] == ["0", "y"]
    deleted = await client.request(
        "DELETE",
        f"{BASE}/{connector}/rows",
        headers=headers,
        json={"node_id": dupes, "row_handles": [edited.json()["row_handle"]]},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 1


@pytest.mark.usefixtures("server")
async def test_the_console_runs_and_says_what_it_cannot_do(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    connector = await _connector(client, headers)
    queries = f"{settings.API_V1_STR}/queries"

    profile = await client.get(f"{queries}/connectors/{connector}/profile", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["supports_explain"] is True
    assert profile.json()["supports_rehearsal"] is False
    assert profile.json()["parameter_syntax"] == "named_braces"

    started = await client.post(
        f"{queries}/runs",
        headers=headers,
        json={
            "run_id": str(uuid.uuid4()),
            "connector_id": connector,
            "text": "SELECT id, label FROM items ORDER BY id",
        },
    )
    assert started.status_code == 200, started.text
    run_id = started.json()["id"]
    deadline = asyncio.get_running_loop().time() + 15
    while True:
        run = (await client.get(f"{queries}/runs/{run_id}", headers=headers)).json()
        if run["status"] not in {"accepted", "running", "cancelling"}:
            break
        assert asyncio.get_running_loop().time() < deadline, run
        await asyncio.sleep(0.05)

    assert run["status"] == "succeeded", run
    [statement] = run["statements"]
    page = await client.get(f"{queries}/results/{statement['result_id']}", headers=headers)
    assert page.json()["rows"][0] == ["1", "alpha"]
