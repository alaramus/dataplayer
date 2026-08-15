from httpx import AsyncClient

from app.core.config import settings

BASE = f"{settings.API_V1_STR}/adapter-types"


async def test_lists_postgres_with_json_schema(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    assert response.status_code == 200
    types = {item["name"]: item for item in response.json()}
    assert types["postgres"]["title"] == "PostgreSQL"
    properties = types["postgres"]["options_schema"]["properties"]
    assert properties["host"]["title"] == "Host"
    assert properties["port"]["default"] == 5432


async def test_secret_fields_are_marked_as_password(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    postgres = next(item for item in response.json() if item["name"] == "postgres")
    assert postgres["options_schema"]["properties"]["password"]["format"] == "password"


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(f"{BASE}/")

    assert response.status_code == 401
