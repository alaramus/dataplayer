"""A SQLite connection through the routes a screen calls (D247–D251).

The adapter is tested on its own in tests/adapters/test_sqlite.py; this is the
file of the signed-in person's storage reached the way the catalog, the grid
and the details panel reach it.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud, storage
from tests.adapters.sqlite_fixture import FILE, build

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def home(db: AsyncSession) -> Path:
    """The personal directory of the user the route tests sign in as."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    home = storage.create_home(user.id)
    build(home)
    return home


async def _connector(
    client: AsyncClient, headers: dict[str, str], options: dict[str, Any]
) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={"name": f"sqlite {uuid.uuid4()}", "adapter_type": "sqlite", "options": options},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


@pytest.mark.usefixtures("home")
async def test_a_file_is_checked_browsed_read_and_described(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    connector = await _connector(client, headers, {"path": FILE})

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

    schemas = await get("catalog")
    assert [node["id"] for node in schemas] == ["main", "\\system"]
    relations = await get("catalog", node_id="main")
    assert {node["name"] for node in relations} >= {"items", "labels", "cheap"}

    page = await post("fetch", {"node_id": "main.items", "limit": 2})
    assert [row[0] for row in page["rows"]] == ["1", "2"]
    assert page["has_more"] is True
    assert page["update_supported"] is True

    model = await get("relation-model", node_id="main.items")
    assert model["kind"] == "table"
    summary = await get("node-summary", node_id="main.items")
    assert summary["contents"]["schema_name"] == "main"
    ddl = await post("content", {"node_id": "main.items", "representation": "sql"})
    assert ddl["text"].startswith('CREATE TABLE "items"')
    features = await get("features")
    assert features["server_version"].startswith("SQLite ")


@pytest.mark.usefixtures("home")
async def test_a_path_out_of_the_storage_is_refused_by_the_form(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": f"sqlite {uuid.uuid4()}",
            "adapter_type": "sqlite",
            "options": {"path": "../someone-else/their.db"},
        },
    )

    assert response.status_code == 422, response.text


@pytest.mark.usefixtures("home")
async def test_a_row_is_edited_through_the_grids_routes(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    connector = await _connector(client, headers, {"path": FILE})

    page = await client.post(
        f"{BASE}/{connector}/fetch", headers=headers, json={"node_id": "main.items", "limit": 1}
    )
    handle = page.json()["row_handles"][0]
    edited = await client.patch(
        f"{BASE}/{connector}/rows/cell",
        headers=headers,
        json={"node_id": "main.items", "row_handle": handle, "column": "name", "value": "uno"},
    )
    stale = await client.patch(
        f"{BASE}/{connector}/rows/cell",
        headers=headers,
        json={"node_id": "main.items", "row_handle": handle, "column": "name", "value": "eins"},
    )
    forged = await client.request(
        "DELETE",
        f"{BASE}/{connector}/rows",
        headers=headers,
        json={"node_id": "main.items", "row_handles": ["x"]},
    )

    assert edited.status_code == 200, edited.text
    assert edited.json()["values"][1] == "uno"
    # The handle read before the edit names a version that is gone.
    assert stale.status_code == 409, stale.text
    assert forged.status_code in (400, 422), forged.text


@pytest.mark.usefixtures("home")
async def test_the_console_runs_and_rehearses(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    connector = await _connector(client, headers, {"path": FILE})
    queries = f"{settings.API_V1_STR}/queries"

    profile = await client.get(f"{queries}/connectors/{connector}/profile", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["supports_explain"] is True
    # Structure changes are transactional in SQLite, so they are rehearsed (D253).
    assert profile.json()["supports_rehearsal"] is True

    started = await client.post(
        f"{queries}/runs",
        headers=headers,
        json={
            "run_id": str(uuid.uuid4()),
            "connector_id": connector,
            "text": "SELECT id, name FROM items ORDER BY id",
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
    assert page.json()["rows"][0] == ["1", "one"]


@pytest.mark.usefixtures("home")
async def test_a_database_is_made_here_with_its_connection(
    client: AsyncClient, normal_user_token_headers: dict[str, str], home: Path
) -> None:
    """The counterpart of starting a server here, for a type that starts nothing (D263)."""
    headers = normal_user_token_headers
    name = f"lab {uuid.uuid4().hex[:8]}"

    types = await client.get(f"{settings.API_V1_STR}/adapter-types/", headers=headers)
    made = await client.post(
        f"{BASE}/made-here",
        headers=headers,
        json={"adapter_type": "sqlite", "choice": {"name": name, "folder": "work", "wal": True}},
    )

    assert {item["name"]: item["makes_here"] for item in types.json()}["sqlite"] is True
    assert {item["name"]: item["makes_here"] for item in types.json()}["postgres"] is False
    assert made.status_code == 200, made.text
    connector = made.json()
    file = f"work/{name.replace(' ', '-')}.db"
    assert connector["name"] == name
    assert connector["config"]["path"] == file
    assert (home / file).is_file()
    tables = await client.get(f"{BASE}/{connector['id']}/catalog", headers=headers, params={"node_id": "main"})
    assert "tasks" in {node["name"] for node in tables.json()}


@pytest.mark.usefixtures("home")
async def test_left_to_the_server_it_is_named_after_its_file(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    made = await client.post(
        f"{BASE}/made-here", headers=normal_user_token_headers, json={"adapter_type": "sqlite"}
    )

    assert made.status_code == 200, made.text
    assert made.json()["name"].startswith("dataplayer")
    assert made.json()["config"]["path"].startswith("databases/dataplayer")


@pytest.mark.usefixtures("home")
async def test_a_folder_outside_the_storage_is_refused_and_nothing_is_saved(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    before = (await client.get(f"{BASE}/", headers=normal_user_token_headers)).json()["count"]

    made = await client.post(
        f"{BASE}/made-here",
        headers=normal_user_token_headers,
        json={"adapter_type": "sqlite", "choice": {"folder": "../elsewhere"}},
    )

    assert made.status_code == 422, made.text
    after = (await client.get(f"{BASE}/", headers=normal_user_token_headers)).json()["count"]
    assert after == before


@pytest.mark.usefixtures("home")
async def test_a_type_that_needs_a_server_is_not_made_here(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/made-here",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "choice": {"name": "nope"}},
    )

    assert response.status_code == 501, response.text
