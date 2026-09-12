import uuid

from httpx import AsyncClient

from app.core.config import settings
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"
WRONG_PASSWORD = "definitely-not-the-password"


async def test_check_draft_succeeds_with_valid_options(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/check-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": working_postgres_options()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["latency_ms"] is not None


async def test_check_draft_reports_auth_failure_without_leaking_password(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    options = working_postgres_options() | {"password": WRONG_PASSWORD}

    response = await client.post(
        f"{BASE}/check-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": options},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error_kind"] == "auth"
    assert WRONG_PASSWORD not in response.text


async def test_check_draft_uses_stored_secret_when_password_omitted(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": "draft check",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    connector_id = created.json()["id"]
    options_without_password = {
        key: value
        for key, value in working_postgres_options().items()
        if key != "password"
    }

    response = await client.post(
        f"{BASE}/check-draft",
        headers=normal_user_token_headers,
        json={
            "adapter_type": "postgres",
            "options": options_without_password,
            "connector_id": connector_id,
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True


async def test_check_draft_rejects_foreign_connector_id(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    created = await client.post(
        f"{BASE}/",
        headers=superuser_token_headers,
        json={
            "name": "foreign for check",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    connector_id = created.json()["id"]

    response = await client.post(
        f"{BASE}/check-draft",
        headers=normal_user_token_headers,
        json={
            "adapter_type": "postgres",
            "options": {},
            "connector_id": connector_id,
        },
    )

    assert response.status_code == 404


async def test_check_saved_connector_succeeds(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "name": "saved check",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    connector_id = created.json()["id"]

    response = await client.post(
        f"{BASE}/{connector_id}/check", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True


async def test_check_unknown_connector_returns_404(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/{uuid.uuid4()}/check", headers=normal_user_token_headers
    )

    assert response.status_code == 404


async def test_a_pressed_check_says_what_the_server_is(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The answer to "what am I about to work on", beside whether it answered.

    A version and not a sentence: what PostgreSQL calls itself in full carries
    the build, the distribution and the compiler, none of which was asked.
    """
    response = await client.post(
        f"{BASE}/check-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": working_postgres_options()},
    )

    said = response.json()["features"]
    assert said is not None
    assert said["server_version"]
    assert " " not in said["server_version"]
    assert [feature["code"] for feature in said["features"]] == ["timescaledb"]


async def test_a_check_that_failed_says_nothing_about_the_server(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Nothing answered, so there is nothing it could have said about itself."""
    options = working_postgres_options() | {"password": WRONG_PASSWORD}

    response = await client.post(
        f"{BASE}/check-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": options},
    )

    assert response.json()["ok"] is False
    assert response.json()["features"] is None
