from httpx import AsyncClient

from app.core.config import settings

BASE = f"{settings.API_V1_STR}/guide"


async def test_lists_every_page_by_key_and_title(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    assert response.status_code == 200
    titles = {item["key"]: item["title"] for item in response.json()}
    assert titles["connections"] == "Connections"
    assert titles["source-postgres"] == "PostgreSQL"


async def test_answers_one_page_as_markdown(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(f"{BASE}/source-redis", headers=normal_user_token_headers)

    assert response.status_code == 200
    assert response.json()["markdown"].startswith("# Redis")


async def test_a_page_that_is_not_there_is_not_found(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    for key in ("nothing-here", "..", "..%2Fconnections"):
        response = await client.get(f"{BASE}/{key}", headers=normal_user_token_headers)
        assert response.status_code == 404, key


async def test_the_guide_is_for_somebody_signed_in(client: AsyncClient) -> None:
    response = await client.get(f"{BASE}/connections")

    assert response.status_code == 401
