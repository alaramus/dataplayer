import uuid

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.models import Connector
from app.core.config import settings

PASSWORD = "top-secret-value"
BASE = f"{settings.API_V1_STR}/connectors"


def _payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "adapter_type": "postgres",
        "options": {
            "auth_method": "user_password",
            "host": "localhost",
            "port": 5432,
            "database": "app",
            "user": "postgres",
            "password": PASSWORD,
        },
    }


async def test_create_returns_connector_without_secrets(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json=_payload("created")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "created"
    assert body["tab_color"] is None
    assert body["adapter_type"] == "postgres"
    assert body["config"]["host"] == "localhost"
    assert "secrets" not in body
    assert PASSWORD not in response.text


async def test_tab_color_is_stored_listed_changed_and_reset(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    created = await client.post(
        f"{BASE}/",
        headers=headers,
        json={**_payload("colored"), "tab_color": "#246AbC"},
    )
    assert created.status_code == 200
    assert created.json()["tab_color"] == "#246AbC"
    connector_id = created.json()["id"]
    url = f"{BASE}/{connector_id}"

    listed = await client.get(f"{BASE}/", headers=headers)
    assert next(
        item for item in listed.json()["data"] if item["id"] == connector_id
    )["tab_color"] == "#246AbC"

    renamed = await client.patch(url, headers=headers, json={"name": "still colored"})
    assert renamed.status_code == 200
    assert renamed.json()["tab_color"] == "#246AbC"

    changed = await client.patch(url, headers=headers, json={"tab_color": "#000000"})
    assert changed.status_code == 200
    assert changed.json()["tab_color"] == "#000000"
    reread = await client.get(url, headers=headers)
    assert reread.json()["tab_color"] == "#000000"

    cleared = await client.patch(url, headers=headers, json={"tab_color": None})
    assert cleared.status_code == 200
    assert cleared.json()["tab_color"] is None
    assert cleared.json()["name"] == "still colored"
    reread = await client.get(url, headers=headers)
    assert reread.json()["tab_color"] is None


@pytest.mark.parametrize(
    "color", ["red", "#abc", "#12345678", "#zzzzzz", "#123456\n", "", 123]
)
async def test_invalid_tab_colors_are_rejected_on_create_and_update(
    client: AsyncClient, normal_user_token_headers: dict[str, str], color: object
) -> None:
    headers = normal_user_token_headers
    refused = await client.post(
        f"{BASE}/",
        headers=headers,
        json={**_payload("invalid color"), "tab_color": color},
    )
    assert refused.status_code == 422
    created = await client.post(f"{BASE}/", headers=headers, json=_payload("valid"))
    assert created.status_code == 200
    refused = await client.patch(
        f"{BASE}/{created.json()['id']}",
        headers=headers,
        json={"tab_color": color},
    )
    assert refused.status_code == 422


async def test_execution_policy_is_decided_with_the_connection(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Whoever registers a source says what may be written through it (D66).

    Answering afterwards was the only way once, so a connection was open to
    writing for as long as it took somebody to go back and close it.
    """
    default = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json=_payload("unstated")
    )
    assert default.status_code == 200
    assert default.json()["execution_policy"] == "confirm_writes"

    chosen = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={**_payload("read only"), "execution_policy": "read_only"},
    )
    assert chosen.status_code == 200
    assert chosen.json()["execution_policy"] == "read_only"

    refused = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={**_payload("nonsense"), "execution_policy": "whatever"},
    )
    assert refused.status_code == 422


async def test_stored_secrets_are_encrypted(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    response = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json=_payload("encrypted")
    )
    connector_id = uuid.UUID(response.json()["id"])

    stored = await db.get(Connector, connector_id)

    assert stored is not None
    assert PASSWORD.encode() not in stored.secrets
    assert "password" not in stored.config


async def test_unknown_adapter_type_is_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    payload = _payload("bad type") | {"adapter_type": "nope"}

    response = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json=payload
    )

    assert response.status_code == 422


async def test_invalid_options_are_rejected_with_field_path(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    payload = _payload("bad options")
    payload["options"] = {"auth_method": "user_password", "host": "localhost"}

    response = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json=payload
    )

    assert response.status_code == 422
    locations = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert any("database" in location for location in locations)


async def test_list_returns_only_own_connectors(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    await client.post(
        f"{BASE}/", headers=superuser_token_headers, json=_payload("superuser only")
    )

    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    assert response.status_code == 200
    names = [item["name"] for item in response.json()["data"]]
    assert "superuser only" not in names


async def test_foreign_connector_returns_404(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    created = await client.post(
        f"{BASE}/", headers=superuser_token_headers, json=_payload("foreign")
    )
    connector_id = created.json()["id"]

    response = await client.get(
        f"{BASE}/{connector_id}", headers=normal_user_token_headers
    )

    assert response.status_code == 404


async def test_patch_without_options_preserves_secrets(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    created = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json=_payload("renamed")
    )
    connector_id = uuid.UUID(created.json()["id"])
    before = await db.get(Connector, connector_id)
    assert before is not None
    secrets_before = before.secrets

    response = await client.patch(
        f"{BASE}/{connector_id}",
        headers=normal_user_token_headers,
        json={"name": "renamed twice"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "renamed twice"
    await db.refresh(before)
    assert before.secrets == secrets_before


async def test_patch_with_partial_options_keeps_stored_password(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    created = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json=_payload("port change")
    )
    connector_id = uuid.UUID(created.json()["id"])

    response = await client.patch(
        f"{BASE}/{connector_id}",
        headers=normal_user_token_headers,
        json={
            "options": {
                "auth_method": "user_password",
                "host": "localhost",
                "port": 6543,
                "database": "app",
                "user": "postgres",
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["config"]["port"] == 6543
    stored = await db.get(Connector, connector_id)
    assert stored is not None
    assert PASSWORD.encode() not in stored.secrets


async def test_delete_removes_connector(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    created = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json=_payload("deleted")
    )
    connector_id = uuid.UUID(created.json()["id"])

    response = await client.delete(
        f"{BASE}/{connector_id}", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    result = await db.exec(select(Connector).where(Connector.id == connector_id))
    assert result.first() is None


async def test_unauthenticated_request_is_rejected(client: AsyncClient) -> None:
    response = await client.get(f"{BASE}/")

    assert response.status_code == 401
