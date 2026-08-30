from httpx import AsyncClient

from app.core.config import settings


async def test_an_unusable_token_is_not_authenticated(client: AsyncClient) -> None:
    """401 and not 403: the server does not know who this is.

    The distinction is load-bearing rather than pedantic. The client signs a
    user out when the server rejects who they are, so a level refused on a
    connection — which is a 403 — must not look like this.
    """
    response = await client.get(
        f"{settings.API_V1_STR}/users/me",
        headers={"Authorization": "Bearer not-a-token"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_a_known_caller_without_rights_is_forbidden(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """403: the server knows exactly who this is, and this is not theirs."""
    response = await client.get(
        f"{settings.API_V1_STR}/users/", headers=normal_user_token_headers
    )

    assert response.status_code == 403
