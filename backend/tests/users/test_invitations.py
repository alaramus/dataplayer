"""A new account chooses its own password through a link that works once."""

from datetime import timedelta
from unittest.mock import patch

from httpx import AsyncClient

from app.core import security
from app.core.config import settings
from tests.utils.utils import random_email

API = settings.API_V1_STR


async def _invite(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str, str]:
    email = random_email()
    r = await client.post(f"{API}/users/", headers=headers, json={"email": email})
    assert r.status_code == 200
    body = r.json()
    token = body["invitation"]["url"].split("token=", 1)[1]
    return email, body["user"]["id"], token


async def _sign_in(client: AsyncClient, email: str, password: str) -> int:
    r = await client.post(
        f"{API}/login/access-token", data={"username": email, "password": password}
    )
    return r.status_code


async def test_nobody_signs_in_before_the_password_is_chosen(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    email, _, _ = await _invite(client, superuser_token_headers)

    assert await _sign_in(client, email, "") == 422
    assert await _sign_in(client, email, "anything-at-all") == 400


async def test_the_link_names_its_holder_and_sets_the_password_once(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    email, _, token = await _invite(client, superuser_token_headers)

    holder = await client.post(f"{API}/invitation/holder", json={"token": token})
    assert holder.status_code == 200
    assert holder.json()["email"] == email

    accepted = await client.post(
        f"{API}/invitation/accept", json={"token": token, "new_password": "chosen-by-me"}
    )
    assert accepted.status_code == 200
    assert await _sign_in(client, email, "chosen-by-me") == 200

    again = await client.post(
        f"{API}/invitation/accept", json={"token": token, "new_password": "someone-else"}
    )
    assert again.status_code == 400
    assert await _sign_in(client, email, "chosen-by-me") == 200


async def test_a_new_link_retires_the_old_one(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    _, user_id, old = await _invite(client, superuser_token_headers)

    reissued = await client.post(
        f"{API}/users/{user_id}/invitation", headers=superuser_token_headers
    )
    assert reissued.status_code == 200
    new = reissued.json()["url"].split("token=", 1)[1]

    assert (await client.post(f"{API}/invitation/holder", json={"token": old})).status_code == 400
    assert (await client.post(f"{API}/invitation/holder", json={"token": new})).status_code == 200


async def test_a_link_for_an_account_with_a_password_resets_it(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    email, user_id, token = await _invite(client, superuser_token_headers)
    await client.post(f"{API}/invitation/accept", json={"token": token, "new_password": "first-one"})

    r = await client.post(f"{API}/users/{user_id}/invitation", headers=superuser_token_headers)

    assert r.status_code == 200
    assert await _sign_in(client, email, "first-one") == 400


async def test_an_expired_link_does_not_work(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    with patch.object(settings, "INVITATION_EXPIRE_HOURS", -1):
        _, _, token = await _invite(client, superuser_token_headers)

    r = await client.post(f"{API}/invitation/holder", json={"token": token})

    assert r.status_code == 400


async def test_a_link_is_never_a_session(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    """It names the account it is for, as a session token does."""
    _, user_id, token = await _invite(client, superuser_token_headers)

    r = await client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    # Nor is a session token a link.
    session = security.create_access_token(user_id, timedelta(minutes=5))
    holder = await client.post(f"{API}/invitation/holder", json={"token": session})
    assert holder.status_code == 400


async def test_only_a_superuser_issues_a_link(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
) -> None:
    _, user_id, _ = await _invite(client, superuser_token_headers)

    r = await client.post(f"{API}/users/{user_id}/invitation", headers=normal_user_token_headers)

    assert r.status_code == 403
