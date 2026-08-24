"""A disabled connector stays in the list and stops being a source.

Disabling is not deleting: the row is still there, still readable, still
editable, and can be switched back on. What it loses is the right to be turned
into a live adapter — so every route that reaches the source refuses at once,
rather than each route remembering to ask.
"""

import uuid

from httpx import AsyncClient

from app.core.config import settings
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


async def _create_connector(
    client: AsyncClient, headers: dict[str, str], name: str
) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": name,
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _disabled_connector(
    client: AsyncClient, headers: dict[str, str], name: str
) -> str:
    connector_id = await _create_connector(client, headers, name)
    response = await client.patch(
        f"{BASE}/{connector_id}", headers=headers, json={"enabled": False}
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    return connector_id


async def test_new_connector_is_enabled(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _create_connector(
        client, normal_user_token_headers, f"enabled by default {uuid.uuid4()}"
    )

    response = await client.get(
        f"{BASE}/{connector_id}", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is True


async def test_disabled_connector_refuses_catalog(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _disabled_connector(
        client, normal_user_token_headers, f"disabled catalog {uuid.uuid4()}"
    )

    response = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )

    assert response.status_code == 409


async def test_disabled_connector_refuses_fetch(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _disabled_connector(
        client, normal_user_token_headers, f"disabled fetch {uuid.uuid4()}"
    )

    response = await client.post(
        f"{BASE}/{connector_id}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": "public.connector"},
    )

    assert response.status_code == 409


async def test_disabled_connector_refuses_actions(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _disabled_connector(
        client, normal_user_token_headers, f"disabled actions {uuid.uuid4()}"
    )

    response = await client.post(
        f"{BASE}/{connector_id}/actions", headers=normal_user_token_headers, json={}
    )

    assert response.status_code == 409


async def test_disabled_connector_refuses_check(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Not even the manual check: the point is to stop touching the server."""
    connector_id = await _disabled_connector(
        client, normal_user_token_headers, f"disabled check {uuid.uuid4()}"
    )

    response = await client.post(
        f"{BASE}/{connector_id}/check", headers=normal_user_token_headers
    )

    assert response.status_code == 409


async def test_disabled_connector_is_still_readable_and_editable(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _disabled_connector(
        client, normal_user_token_headers, f"disabled readable {uuid.uuid4()}"
    )

    listed = await client.get(f"{BASE}/", headers=normal_user_token_headers)
    renamed = await client.patch(
        f"{BASE}/{connector_id}",
        headers=normal_user_token_headers,
        json={"name": f"renamed while off {uuid.uuid4()}"},
    )

    assert connector_id in [item["id"] for item in listed.json()["data"]]
    assert renamed.status_code == 200
    assert renamed.json()["enabled"] is False


async def test_re_enabled_connector_works_again(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _disabled_connector(
        client, normal_user_token_headers, f"switched back on {uuid.uuid4()}"
    )

    await client.patch(
        f"{BASE}/{connector_id}",
        headers=normal_user_token_headers,
        json={"enabled": True},
    )
    response = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=normal_user_token_headers
    )

    assert response.status_code == 200
