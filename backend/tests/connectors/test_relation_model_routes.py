import uuid

from httpx import AsyncClient

from app.core.config import settings
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


async def _postgres_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"relation {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _file_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"relation files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def test_describes_a_relation(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        params={"node_id": "pg_catalog.pg_class"},
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "pg_class"
    assert body["kind"] == "table"
    names = [column["name"] for column in body["columns"]]
    assert "relname" in names
    relname = next(c for c in body["columns"] if c["name"] == "relname")
    assert relname["type"]["sql"] == "name"
    assert relname["type"]["category"] == "string"


async def test_a_relation_that_is_gone_is_not_a_failure(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        params={"node_id": "public.no_such_table"},
        headers=normal_user_token_headers,
    )
    assert response.status_code == 404


async def test_a_source_without_relations_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)
    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        params={"node_id": "anything"},
        headers=normal_user_token_headers,
    )
    assert response.status_code == 501


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(
        f"{BASE}/{uuid.uuid4()}/relation-model",
        params={"node_id": "public.x"},
    )
    assert response.status_code == 401
