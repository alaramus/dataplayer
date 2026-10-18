"""What a user chose, read back and changed through their own routes."""

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users.preferences import (
    CHECK_SECONDS,
    DEFAULT_CHECK_INTERVAL,
    as_interval,
    as_language,
    as_theme,
    check_seconds,
)
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

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


async def test_the_welcome_tour_is_seen_once_per_account(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Kept on the account, apart from the other choices: marking it leaves them."""
    headers = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    assert (await client.get(PREFERENCES, headers=headers)).json()["welcome_tour_done"] is False
    await client.patch(PREFERENCES, headers=headers, json={"connector_checks": "5m"})

    done = await client.patch(
        PREFERENCES, headers=headers, json={"welcome_tour_done": True}
    )

    assert done.status_code == 200
    assert done.json() == {
        "connector_checks": "5m",
        "welcome_tour_done": True,
        "language": None,
        "theme": None,
    }
    read_back = await client.get(PREFERENCES, headers=headers)
    assert read_back.json()["welcome_tour_done"] is True


async def test_a_language_is_kept_and_null_returns_to_the_browsers(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """None is a choice of its own (D224): the browser's language. Leaving the
    field out must not be read as choosing it."""
    before = await client.get(PREFERENCES, headers=normal_user_token_headers)
    assert before.json()["language"] is None

    chosen = await client.patch(
        PREFERENCES, headers=normal_user_token_headers, json={"language": "ru"}
    )
    untouched = await client.patch(
        PREFERENCES, headers=normal_user_token_headers, json={"connector_checks": "1m"}
    )
    cleared = await client.patch(
        PREFERENCES, headers=normal_user_token_headers, json={"language": None}
    )

    assert chosen.json()["language"] == "ru"
    assert untouched.json()["language"] == "ru"
    assert cleared.json()["language"] is None

    await client.patch(
        PREFERENCES,
        headers=normal_user_token_headers,
        json={"connector_checks": DEFAULT_CHECK_INTERVAL},
    )


async def test_a_language_nobody_translated_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.patch(
        PREFERENCES, headers=normal_user_token_headers, json={"language": "xx"}
    )

    assert response.status_code == 422


def test_a_stored_language_this_version_does_not_offer_reads_as_the_browsers() -> None:
    assert as_language("ru") == "ru"
    assert as_language("de") == "de"
    assert as_language("tlh") is None
    assert as_language(None) is None


async def test_a_theme_is_kept_on_the_account_and_null_returns_to_the_systems(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The theme follows the person, as the language does: two people in one
    browser each get their own."""
    chosen = await client.patch(
        PREFERENCES, headers=normal_user_token_headers, json={"theme": "midnight"}
    )
    untouched = await client.patch(
        PREFERENCES, headers=normal_user_token_headers, json={"language": "ru"}
    )
    cleared = await client.patch(
        PREFERENCES,
        headers=normal_user_token_headers,
        json={"theme": None, "language": None},
    )

    assert chosen.json()["theme"] == "midnight"
    assert untouched.json()["theme"] == "midnight"
    assert cleared.json()["theme"] is None


async def test_a_theme_nobody_draws_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.patch(
        PREFERENCES, headers=normal_user_token_headers, json={"theme": "neon"}
    )

    assert response.status_code == 422


def test_a_stored_theme_this_version_no_longer_draws_reads_as_the_systems() -> None:
    assert as_theme("paper") == "paper"
    assert as_theme("sepia") is None
    assert as_theme(None) is None

