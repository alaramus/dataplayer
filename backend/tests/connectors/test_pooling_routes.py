"""What the application actually keeps between requests."""

import uuid

import pytest
from httpx import AsyncClient

from app.adapters.resources import ResourceStore
from app.core.config import settings
from app.main import app
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


def resources() -> ResourceStore:
    store = app.state.resources
    assert isinstance(store, ResourceStore)
    return store


async def _postgres_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"pooled {uuid.uuid4()}",
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
            "name": f"files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


@pytest.mark.usefixtures("client")
async def test_the_application_holds_a_store() -> None:
    """Without the lifespan there is nowhere to keep a pool, and every request
    would quietly go back to opening its own connection."""
    assert isinstance(app.state.resources, ResourceStore)


async def test_browsing_twice_keeps_one_pool(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    await resources().aclose()
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    for _ in range(2):
        response = await client.get(
            f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
        )
        assert response.status_code == 200

    assert await resources().size() == 1

    await resources().aclose()


async def test_reading_rows_uses_the_pool_of_the_same_connector(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    await resources().aclose()
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )
    rows = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": "pg_catalog.pg_class", "limit": 1},
    )

    assert rows.status_code == 200
    assert await resources().size() == 1

    await resources().aclose()


async def test_a_draft_check_keeps_nothing(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A draft has no identity to key a pool by, and a check is meant to
    exercise the credentials rather than report that a pool is alive."""
    await resources().aclose()

    response = await client.post(
        f"{BASE}/check-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": working_postgres_options()},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert await resources().size() == 0


async def test_checking_a_stored_connector_keeps_nothing(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    await resources().aclose()

    response = await client.post(
        f"{BASE}/{connector_id}/check", headers=normal_user_token_headers
    )

    assert response.json()["ok"] is True
    assert await resources().size() == 0


async def test_a_source_without_connections_keeps_nothing(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)
    await resources().aclose()

    response = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    assert await resources().size() == 0
