"""What a user chose, read back and changed through their own routes."""

from httpx import AsyncClient

from app.core.config import settings
from app.users.preferences import (
    CHECK_SECONDS,
    DEFAULT_CHECK_INTERVAL,
    as_interval,
    check_seconds,
)

PREFERENCES = f"{settings.API_V1_STR}/users/me/preferences"


async def test_somebody_who_never_chose_gets_the_default(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """There is no row until something is chosen, and no empty screen either."""
    response = await client.get(PREFERENCES, headers=normal_user_token_headers)

    assert response.status_code == 200
    assert response.json()["connector_checks"] == DEFAULT_CHECK_INTERVAL


async def test_a_choice_is_kept(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    saved = await client.patch(
        PREFERENCES,
        headers=normal_user_token_headers,
        json={"connector_checks": "5m"},
    )
    read_back = await client.get(PREFERENCES, headers=normal_user_token_headers)

    assert saved.status_code == 200
    assert saved.json()["connector_checks"] == "5m"
    assert read_back.json()["connector_checks"] == "5m"

    await client.patch(
        PREFERENCES,
        headers=normal_user_token_headers,
        json={"connector_checks": DEFAULT_CHECK_INTERVAL},
    )


async def test_an_interval_nobody_offers_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The set is closed, so a number typed into the request is not a choice."""
    response = await client.patch(
        PREFERENCES,
        headers=normal_user_token_headers,
        json={"connector_checks": "1s"},
    )

    assert response.status_code == 422


async def test_preferences_are_a_user_s_own(client: AsyncClient) -> None:
    assert (await client.get(PREFERENCES)).status_code == 401


def test_every_offered_interval_says_how_many_seconds_it_is() -> None:
    """The one table, so a choice cannot be offered and then mean nothing."""
    assert check_seconds("off") is None
    assert check_seconds("5m") == 300.0
    for choice in CHECK_SECONDS:
        assert as_interval(choice) == choice


def test_a_value_from_another_version_reads_as_the_default() -> None:
    """A column holds text, and unrecognised text must not stop the probing."""
    assert as_interval("every fortnight") == DEFAULT_CHECK_INTERVAL
    assert check_seconds("every fortnight") == CHECK_SECONDS[DEFAULT_CHECK_INTERVAL]
