from httpx import AsyncClient

from app.core.config import settings
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


async def test_describes_a_draft_as_a_connection_string(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Composed from form values, so nothing has to be saved to see it."""
    response = await client.post(
        f"{BASE}/describe-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": working_postgres_options()},
    )

    assert response.status_code == 200
    url = response.json()["connection_string"]
    assert url.startswith("postgresql://")
    assert working_postgres_options()["database"] in url


async def test_the_described_draft_never_carries_the_password(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    options = {**working_postgres_options(), "password": "a-very-secret-value"}

    response = await client.post(
        f"{BASE}/describe-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": options},
    )

    assert "a-very-secret-value" not in response.text


async def test_a_source_with_no_connection_string_answers_501(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A personal directory is not addressed by a URL, and must not invent one."""
    response = await client.post(
        f"{BASE}/describe-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "file", "options": {"path": ""}},
    )

    assert response.status_code == 501


async def test_values_that_do_not_fit_the_schema_are_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A half-typed form must not reach the driver."""
    response = await client.post(
        f"{BASE}/describe-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": {"host": "db"}},
    )

    assert response.status_code == 422


async def test_unknown_adapter_type_is_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/describe-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "nope", "options": {}},
    )

    assert response.status_code == 422


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/describe-draft",
        json={"adapter_type": "postgres", "options": working_postgres_options()},
    )

    assert response.status_code == 401
