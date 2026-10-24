"""A SQLite connection through the routes a screen calls (D247–D251).

The adapter is tested on its own in tests/adapters/test_sqlite.py; this is the
file of the signed-in person's storage reached the way the catalog, the grid
and the details panel reach it.
"""

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
    assert [node["id"] for node in schemas] == ["main"]
    relations = await get("catalog", node_id="main")
    assert {node["name"] for node in relations} >= {"items", "labels", "cheap"}

    page = await post("fetch", {"node_id": "main.items", "limit": 2})
    assert [row[0] for row in page["rows"]] == ["1", "2"]
    assert page["has_more"] is True
    assert page["update_supported"] is False

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
async def test_what_it_does_not_do_is_refused_as_not_implemented(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector = await _connector(client, normal_user_token_headers, {"path": FILE})

    response = await client.request(
        "DELETE",
        f"{BASE}/{connector}/rows",
        headers=normal_user_token_headers,
        json={"node_id": "main.items", "row_handles": ["x"]},
    )

    # Rows are read only in this slice, and the capability is not claimed (D2).
    assert response.status_code == 501, response.text
