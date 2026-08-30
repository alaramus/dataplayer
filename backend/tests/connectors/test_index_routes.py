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
            "name": f"index {uuid.uuid4()}",
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
            "name": f"index files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def test_creates_and_drops_an_index_the_source_named(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    created = await client.post(
        f"{BASE}/{connector_id}/indexes",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "columns": ["region_id", "region_code"],
            "method": "btree",
        },
    )

    assert created.status_code == 200, created.text
    body = created.json()
    assert body["kind"] == "created"
    assert body["name"] == "customers_region_id_region_code_idx"

    dropped = await client.request(
        "DELETE",
        f"{BASE}/{connector_id}/indexes",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.customers", "name": body["name"]},
    )

    assert dropped.status_code == 200, dropped.text
    assert dropped.json() == {"name": body["name"]}


async def test_repeating_values_are_answered_with_their_count(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    """A well-formed request about data that repeats is not an error."""
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await run(
        f"INSERT INTO {schema}.regions VALUES (1, 'EU'), (2, 'EU')"  # noqa: S608 -- fixture-owned schema.
    )

    response = await client.post(
        f"{BASE}/{connector_id}/indexes",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.regions",
            "columns": ["code"],
            "method": "btree",
            "unique": True,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "kind": "blocked",
        "duplicate_groups": 1,
        "exact": True,
    }


async def test_the_relation_publishes_the_methods_and_their_limits(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        headers=normal_user_token_headers,
        params={"node_id": f"{schema}.customers"},
    )

    body = response.json()
    assert body["index_changes_supported"] is True
    methods = {option["code"]: option for option in body["index_methods"]}
    assert methods["hash"]["unique_supported"] is False


async def test_an_unknown_method_never_reaches_a_statement(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/indexes",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "columns": ["name"],
            "method": "btree (name); DROP TABLE regions; --",
        },
    )

    assert response.status_code == 422
    model = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        headers=normal_user_token_headers,
        params={"node_id": f"{schema}.regions"},
    )
    assert model.status_code == 200


async def test_a_column_may_not_appear_twice(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/indexes",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "columns": ["name", "name"],
            "method": "btree",
        },
    )

    assert response.status_code == 422


async def test_a_relation_that_is_gone_is_not_a_failure(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/indexes",
        headers=normal_user_token_headers,
        json={"node_id": "public.no_such_table", "columns": ["x"], "method": "btree"},
    )

    assert response.status_code == 404


async def test_a_source_without_indexes_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    created = await client.post(
        f"{BASE}/{connector_id}/indexes",
        headers=normal_user_token_headers,
        json={"node_id": "anything", "columns": ["a"], "method": "btree"},
    )
    dropped = await client.request(
        "DELETE",
        f"{BASE}/{connector_id}/indexes",
        headers=normal_user_token_headers,
        json={"node_id": "anything", "name": "a_idx"},
    )

    assert created.status_code == 501
    assert dropped.status_code == 501


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/{uuid.uuid4()}/indexes",
        json={"node_id": "public.x", "columns": ["y"], "method": "btree"},
    )
    assert response.status_code == 401
