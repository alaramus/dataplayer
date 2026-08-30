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
            "name": f"type {uuid.uuid4()}",
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
            "name": f"type files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _column(client: AsyncClient, headers: dict[str, str], connector_id: str, schema: str) -> None:
    response = await client.post(
        f"{BASE}/{connector_id}/columns",
        headers=headers,
        json={"node_id": f"{schema}.customers", "name": "score", "type_code": "text"},
    )
    assert response.status_code == 200, response.text


async def test_changes_a_column_type_through_the_owned_connector(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _column(client, normal_user_token_headers, connector_id, schema)

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/type",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "name": "score",
            "type_code": "integer",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "kind": "changed",
        "name": "score",
        "type_sql": "integer",
    }


async def test_values_the_new_type_cannot_read_are_answered_with_their_count(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    """A well-formed request about data the target cannot read is not an error."""
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await _column(client, normal_user_token_headers, connector_id, schema)
    await run(
        f"INSERT INTO {schema}.regions VALUES (1, 'EU')"  # noqa: S608 -- fixture-owned schema.
    )
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name, score) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'ann', 'x'), (1, 'EU', 'bob', 'y')"
    )

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/type",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "name": "score",
            "type_code": "integer",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "kind": "blocked",
        "name": "score",
        "rows_not_convertible": 2,
        "exact": True,
    }


async def test_a_conversion_that_does_not_exist_is_a_bad_request(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/type",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "name": "token",
            "type_code": "integer",
        },
    )

    assert response.status_code == 422
    assert "no conversion" in response.text


async def test_an_unknown_type_code_never_reaches_a_statement(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/type",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "name": "payload",
            "type_code": "text USING payload::text, DROP COLUMN tags",
        },
    )

    assert response.status_code == 422
    model = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        headers=normal_user_token_headers,
        params={"node_id": f"{schema}.customers"},
    )
    assert "tags" in {column["name"] for column in model.json()["columns"]}


async def test_a_relation_that_is_gone_is_not_a_failure(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/type",
        headers=normal_user_token_headers,
        json={"node_id": "public.no_such_table", "name": "x", "type_code": "text"},
    )

    assert response.status_code == 404


async def test_a_source_that_cannot_change_types_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.patch(
        f"{BASE}/{connector_id}/columns/type",
        headers=normal_user_token_headers,
        json={"node_id": "anything", "name": "note", "type_code": "text"},
    )

    assert response.status_code == 501


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.patch(
        f"{BASE}/{uuid.uuid4()}/columns/type",
        json={"node_id": "public.x", "name": "y", "type_code": "text"},
    )
    assert response.status_code == 401
