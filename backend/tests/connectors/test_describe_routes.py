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


async def test_a_half_typed_form_is_described_as_far_as_it_goes(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A host and a port are already an address worth showing.

    Composed here rather than on the client for the same reason the finished
    one is: the grammar of the address belongs to the driver, and a second
    implementation would differ from it in the escaping first.
    """
    response = await client.post(
        f"{BASE}/describe-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": {"host": "db", "port": 6543}},
    )

    assert response.status_code == 200
    assert response.json()["connection_string"] == "postgresql://db:6543"


async def test_a_form_with_nothing_in_it_yet_is_described_as_nothing(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """An empty string rather than 501: the source does have addresses."""
    response = await client.post(
        f"{BASE}/describe-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": {}},
    )

    assert response.status_code == 200
    assert response.json()["connection_string"] == ""


async def test_a_half_typed_draft_never_carries_the_password(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/describe-draft",
        headers=normal_user_token_headers,
        json={
            "adapter_type": "postgres",
            "options": {"host": "db", "user": "ann", "password": "a-very-secret-value"},
        },
    )

    assert "a-very-secret-value" not in response.text


async def test_an_ssh_draft_is_described_as_an_ssh_url(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/describe-draft",
        headers=normal_user_token_headers,
        json={
            "adapter_type": "ssh",
            "options": {"host": "server.example", "port": 2222, "username": "a@b"},
        },
    )

    assert response.status_code == 200
    assert response.json()["connection_string"] == "ssh://a%40b@server.example:2222"


async def test_a_half_typed_form_for_a_source_with_no_address_still_answers_501(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Incomplete is not the same answer as "this source has no address"."""
    response = await client.post(
        f"{BASE}/describe-draft",
        headers=normal_user_token_headers,
        json={"adapter_type": "file", "options": {}},
    )

    assert response.status_code == 501


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
