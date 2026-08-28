import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


async def _connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"rename {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def test_renames_a_column_through_the_owned_connector(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)

    response = await client.patch(
        f"{BASE}/{connector_id}/columns",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "name": "region_id",
            "new_name": "area_id",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"name": "area_id"}


async def test_cannot_rename_a_column_through_somebody_elses_connector(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _connector(client, superuser_token_headers)

    response = await client.patch(
        f"{BASE}/{connector_id}/columns",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "name": "region_id",
            "new_name": "area_id",
        },
    )

    assert response.status_code == 404
