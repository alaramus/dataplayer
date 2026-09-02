"""What a client may know about the services this server can start."""

from httpx import AsyncClient

from app.core.config import settings

BASE = f"{settings.API_V1_STR}/services"


async def test_the_templates_are_listed_with_what_each_one_becomes(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(f"{BASE}/templates", headers=normal_user_token_headers)

    assert response.status_code == 200
    postgres = next(item for item in response.json() if item["key"] == "postgres")
    assert postgres["title"] == "PostgreSQL"
    assert postgres["image"] == "postgres:18"
    assert postgres["adapter_type"] == "postgres"
    # The words for a source type are the server's, so a screen showing what a
    # service becomes does not keep a second name for it.
    assert postgres["adapter_title"] == "PostgreSQL"
    # What a person will not be asked for.
    assert postgres["generated"] == ["password"]


async def test_nothing_about_the_container_is_published(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Publishing the environment or the volume would invite the belief that a
    request could steer them."""
    response = await client.get(f"{BASE}/templates", headers=normal_user_token_headers)

    listed = response.json()[0]
    assert set(listed) == {
        "key",
        "title",
        "description",
        "image",
        "container_port",
        "adapter_type",
        "adapter_title",
        "generated",
    }


async def test_a_stranger_is_not_told_what_this_server_can_start(
    client: AsyncClient,
) -> None:
    response = await client.get(f"{BASE}/templates")

    assert response.status_code == 401
