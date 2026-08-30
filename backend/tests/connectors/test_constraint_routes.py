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
            "name": f"constraint {uuid.uuid4()}",
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
            "name": f"constraint files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def test_adds_a_unique_constraint_and_drops_it(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    created = await client.post(
        f"{BASE}/{connector_id}/constraints",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.regions",
            "constraint": {"kind": "unique", "columns": ["code"]},
        },
    )

    assert created.status_code == 200, created.text
    body = created.json()
    assert body["kind"] == "created"
    assert body["name"] == "regions_code_key"

    dropped = await client.request(
        "DELETE",
        f"{BASE}/{connector_id}/constraints",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.regions", "name": body["name"]},
    )

    assert dropped.status_code == 200, dropped.text
    assert dropped.json() == {"name": body["name"]}


async def test_adds_a_foreign_key_to_a_published_candidate_key(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    model = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        headers=normal_user_token_headers,
        params={"node_id": f"{schema}.regions"},
    )
    key = model.json()["candidate_keys"][0]
    assert key["columns"] == ["id", "code"]

    response = await client.post(
        f"{BASE}/{connector_id}/constraints",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.events",
            "constraint": {
                "kind": "foreign_key",
                "columns": ["id", "happened"],
                "target_node_id": f"{schema}.regions",
                "target_columns": key["columns"],
                "on_delete": "cascade",
            },
        },
    )

    # events.happened is a date and regions.code is a varchar, so PostgreSQL
    # refuses the comparison — named, not relayed.
    assert response.status_code == 422
    assert "cannot be compared" in response.text


async def test_repeating_values_are_answered_with_their_count(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await run(
        f"INSERT INTO {schema}.regions VALUES (1, 'EU'), (2, 'EU')"  # noqa: S608 -- fixture-owned schema.
    )

    response = await client.post(
        f"{BASE}/{connector_id}/constraints",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.regions",
            "constraint": {"kind": "unique", "columns": ["code"]},
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"kind": "repeating", "groups": 1, "exact": True}


async def test_a_target_without_a_matching_key_is_a_bad_request(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/constraints",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "constraint": {
                "kind": "foreign_key",
                "columns": ["region_code"],
                "target_node_id": f"{schema}.regions",
                "target_columns": ["code"],
            },
        },
    )

    assert response.status_code == 422
    assert "no unique key" in response.text


async def test_an_unknown_constraint_kind_is_refused_by_the_union(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/constraints",
        headers=normal_user_token_headers,
        json={
            "node_id": f"{schema}.customers",
            "constraint": {"kind": "check", "expression": "1 = 1"},
        },
    )

    assert response.status_code == 422


async def test_a_relation_that_is_gone_is_not_a_failure(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{connector_id}/constraints",
        headers=normal_user_token_headers,
        json={
            "node_id": "public.no_such_table",
            "constraint": {"kind": "unique", "columns": ["x"]},
        },
    )

    assert response.status_code == 404


async def test_a_source_without_constraints_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)

    created = await client.post(
        f"{BASE}/{connector_id}/constraints",
        headers=normal_user_token_headers,
        json={
            "node_id": "anything",
            "constraint": {"kind": "unique", "columns": ["a"]},
        },
    )
    dropped = await client.request(
        "DELETE",
        f"{BASE}/{connector_id}/constraints",
        headers=normal_user_token_headers,
        json={"node_id": "anything", "name": "a_key"},
    )

    assert created.status_code == 501
    assert dropped.status_code == 501


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/{uuid.uuid4()}/constraints",
        json={
            "node_id": "public.x",
            "constraint": {"kind": "unique", "columns": ["y"]},
        },
    )
    assert response.status_code == 401
