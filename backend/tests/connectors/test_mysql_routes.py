"""A MySQL connection through the routes a screen calls (D228–D231).

The adapter is tested on its own in tests/adapters/test_mysql.py; this is the
same server reached the way the catalog, the grid and the details panel reach
it, pooled and cached as they are.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.adapters.mysql import ids
from app.core.config import settings
from tests.adapters.mysql_fixture import DATABASE, TARGETS, Target, build, tear_down

BASE = f"{settings.API_V1_STR}/connectors"
ITEMS = ids.relation_id(DATABASE, "items")


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    yield chosen
    await tear_down(chosen)


async def _connector(
    client: AsyncClient, headers: dict[str, str], target: Target
) -> str:
    options = target.options(database=DATABASE)
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"mysql {uuid.uuid4()}",
            "adapter_type": "mysql",
            "options": {
                **options.model_dump(exclude={"password"}),
                "password": options.password.get_secret_value(),
            },
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def test_a_connection_is_checked_browsed_read_and_described(
    client: AsyncClient, normal_user_token_headers: dict[str, str], target: Target
) -> None:
    headers = normal_user_token_headers
    connector = await _connector(client, headers, target)

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
    relations = await get("catalog", node_id=ids.database_id(DATABASE))
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
    assert features["server_version"]


async def test_a_row_handle_the_source_did_not_issue_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str], target: Target
) -> None:
    connector = await _connector(client, normal_user_token_headers, target)

    response = await client.request(
        "DELETE",
        f"{BASE}/{connector}/rows",
        headers=normal_user_token_headers,
        json={"node_id": ITEMS, "row_handles": ["x"]},
    )

    assert response.status_code in (400, 422), response.text


async def test_the_console_runs_and_says_what_it_cannot_do(
    client: AsyncClient, normal_user_token_headers: dict[str, str], target: Target
) -> None:
    headers = normal_user_token_headers
    connector = await _connector(client, headers, target)
    queries = f"{settings.API_V1_STR}/queries"

    profile = await client.get(f"{queries}/connectors/{connector}/profile", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["supports_explain"] is True
    assert profile.json()["supports_rehearsal"] is False

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
