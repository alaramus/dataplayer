import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud, storage
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def home(db: AsyncSession) -> Path:
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    home = storage.create_home(user.id)
    (home / "searched").mkdir(exist_ok=True)
    (home / "searched" / "findme.txt").write_text("top\n", encoding="utf-8")
    (home / "searched" / "deeper").mkdir(exist_ok=True)
    (home / "searched" / "deeper" / "findme-too.txt").write_text("x\n", encoding="utf-8")
    return home


async def _file_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"search files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


@pytest.mark.usefixtures("home")
async def test_a_search_answers_with_nodes_and_where_they_are(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/catalog/search",
        params={"node_id": "searched", "query": "findme"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["complete"] is True
    names = [match["node"]["name"] for match in body["matches"]]
    assert names == ["findme.txt", "findme-too.txt"]
    deeper = body["matches"][1]
    assert deeper["parent_id"] == "searched/deeper"
    assert deeper["location"] == "searched/deeper"
    # The same node the listing gives, so a found row opens like any other.
    assert deeper["node"]["kind"] == "file"
    assert deeper["node"]["representations"][0]["kind"] == "text"


@pytest.mark.usefixtures("home")
async def test_a_ceiling_is_answered_as_an_incomplete_search(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/catalog/search",
        params={"node_id": "searched", "query": "findme", "limit": 1},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["matches"]) == 1
    assert body["complete"] is False
    assert body["notice"]


@pytest.mark.usefixtures("home")
@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"query": ""}, 422),
        ({"query": "x" * 500}, 422),
        ({"query": "findme", "limit": 0}, 422),
        ({"query": "findme", "limit": 5000}, 422),
        ({"query": "findme", "node_id": "../../etc"}, 422),
        ({"query": "findme", "node_id": "searched/findme.txt"}, 422),
        ({"query": "findme", "node_id": "nowhere"}, 404),
    ],
)
async def test_what_a_search_refuses(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    params: dict[str, object],
    status: int,
) -> None:
    """Every bound is the route's or the source's, and none is the caller's."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/catalog/search",
        params=params,
        headers=normal_user_token_headers,
    )

    assert response.status_code == status


async def test_a_source_that_cannot_be_searched_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": f"search postgres {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert created.status_code == 200

    response = await client.get(
        f"{BASE}/{created.json()['id']}/catalog/search",
        params={"query": "users"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 501


async def test_the_type_catalog_says_which_sources_can_be_searched(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A code rather than a title: a screen switches on it (D76)."""
    response = await client.get(
        f"{settings.API_V1_STR}/adapter-types/", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    codes = {
        adapter["name"]: {
            capability["code"] for capability in adapter["capabilities"]
        }
        for adapter in response.json()
    }
    assert "search" in codes["file"]
    assert "search" not in codes["postgres"]
