import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


async def _postgres_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"nullability {uuid.uuid4()}",
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
            "name": f"nullability files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def test_a_column_stops_requiring_a_value(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/nullability",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.customers", "name": "name", "nullable": True},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"kind": "changed", "name": "name", "nullable": True}


async def test_rows_in_the_way_are_answered_with_their_count(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    """A well-formed request about data that is not ready is not an error."""
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await run(
        f"INSERT INTO {schema}.regions VALUES (1, 'EU')"  # noqa: S608 -- fixture-owned schema.
    )
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'ann'), (1, 'EU', 'bob'), (1, 'EU', 'cai')"
    )

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/nullability",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.customers", "name": "tags", "nullable": False},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "kind": "blocked",
        "name": "tags",
        "rows_without_value": 3,
        "exact": True,
    }


async def test_an_unknown_column_is_a_bad_request(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/nullability",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.customers", "name": "missing", "nullable": True},
    )

    assert response.status_code == 422


async def test_a_relation_that_is_gone_is_not_a_failure(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/nullability",
        headers=normal_user_token_headers,
        json={"node_id": "public.no_such_table", "name": "x", "nullable": True},
    )

    assert response.status_code == 404


async def test_a_source_that_cannot_change_nullability_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/nullability",
        headers=normal_user_token_headers,
        json={"node_id": "anything", "name": "note", "nullable": True},
    )

    assert response.status_code == 501


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.patch(
        f"{BASE}/{uuid.uuid4()}/columns/nullability",
        json={"node_id": "public.x", "name": "y", "nullable": True},
    )
    assert response.status_code == 401
