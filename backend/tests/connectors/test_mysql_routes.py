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
from app.adapters.mysql.reports import PROCESSES_REPORT_ID
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


async def test_the_catalog_is_searched_and_a_process_is_named_by_its_number(
    client: AsyncClient, normal_user_token_headers: dict[str, str], target: Target
) -> None:
    headers = normal_user_token_headers
    connector = await _connector(client, headers, target)

    found = await client.get(
        f"{BASE}/{connector}/catalog/search",
        headers=headers,
        params={"query": "items", "node_id": ids.database_id(DATABASE)},
    )
    assert found.status_code == 200, found.text
    assert [match["node"]["id"] for match in found.json()["matches"]][0] == ITEMS

    refused = await client.post(
        f"{BASE}/{connector}/rows/command",
        headers=headers,
        json={"node_id": PROCESSES_REPORT_ID, "name": "kill_query", "keys": ["1 OR 1"]},
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["message"] == "A connection is named by its number"


async def test_a_database_is_made_and_dropped_through_the_actions(
    client: AsyncClient, normal_user_token_headers: dict[str, str], target: Target
) -> None:
    headers = normal_user_token_headers
    connector = await _connector(client, headers, target)
    made = f"dp_route_{uuid.uuid4().hex[:8]}"

    offered = await client.post(f"{BASE}/{connector}/actions", headers=headers, json={})
    assert offered.status_code == 200, offered.text
    assert "create_database" in {action["name"] for action in offered.json()}

    created = await client.post(
        f"{BASE}/{connector}/actions/create_database",
        headers=headers,
        json={"params": {"name": made}},
    )
    assert created.status_code == 200, created.text
    dropped = await client.post(
        f"{BASE}/{connector}/actions/drop_database",
        headers=headers,
        json={"node_id": ids.database_id(made), "params": {}},
    )
    assert dropped.status_code == 200, dropped.text
    databases = await client.get(f"{BASE}/{connector}/catalog", headers=headers)
    assert made not in {node["name"] for node in databases.json()}


async def test_tables_are_offered_for_a_copy_with_their_structure(
    client: AsyncClient, normal_user_token_headers: dict[str, str], target: Target
) -> None:
    headers = normal_user_token_headers
    connector = await _connector(client, headers, target)
    pair = {
        "source_connector_id": connector,
        "source_node_ids": [ITEMS],
        "mode": "copy",
        "destination_node_id": ids.database_id(DATABASE),
    }

    offers = await client.post(f"{BASE}/{connector}/paste/offers", headers=headers, json=pair)
    preview = await client.post(f"{BASE}/{connector}/paste/tables", headers=headers, json=pair)

    assert offers.status_code == 200, offers.text
    assert "tables_copy" in {offer["kind"] for offer in offers.json()["offers"]}
    assert preview.status_code == 200, preview.text
    planned = preview.json()
    assert [table["name"] for table in planned["tables"]][0] == "items_copy"
    assert planned["problems"] == []
    assert planned["statements"][0]["sql"].startswith("CREATE TABLE `dp_test.mysql`.`items_copy`")
