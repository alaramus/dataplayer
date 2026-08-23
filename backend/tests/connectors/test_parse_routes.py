"""Turning a pasted connection string back into form values.

The question is asked of a *type*: there are no options yet, and parsing is
what produces them. Nothing is opened — this route is the inverse of
`describe-draft`, and costs the server the parse and nothing more.
"""

from httpx import AsyncClient

from app.core.config import settings

BASE = f"{settings.API_V1_STR}/connectors"


async def _parse(
    client: AsyncClient, headers: dict[str, str], url: str, adapter_type: str = "postgres"
) -> tuple[int, dict[str, object]]:
    response = await client.post(
        f"{BASE}/parse-url",
        headers=headers,
        json={"adapter_type": adapter_type, "url": url},
    )
    return response.status_code, response.json()


async def test_a_url_becomes_the_fields_of_the_form(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The three renamings that would each be a bug: dbname, port, password."""
    status, body = await _parse(
        client, normal_user_token_headers, "postgresql://ann:pw@db:6543/app"
    )

    assert status == 200
    assert body["options"] == {
        "auth_method": "user_password",
        "host": "db",
        "port": 6543,
        "database": "app",
        "user": "ann",
        "password": "pw",
    }


async def test_the_port_comes_back_as_a_number(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """libpq answers with a string, and a string would fail the form's schema."""
    _, body = await _parse(
        client, normal_user_token_headers, "postgresql://ann:pw@db:6543/app"
    )

    options = body["options"]
    assert isinstance(options, dict)
    assert options["port"] == 6543


async def test_a_url_without_a_password_names_the_other_variant(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Inferred by the driver, never by the form.

    A form guessing the way of connecting from a substring is the
    `isFieldShowing` of the old application, which is where this started.
    """
    _, body = await _parse(client, normal_user_token_headers, "postgresql://ann@db/app")

    assert body["options"] == {
        "auth_method": "no_auth",
        "host": "db",
        "database": "app",
        "user": "ann",
    }


async def test_the_keyword_form_is_a_connection_string_too(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """What counts as one is the driver's rule, not a scheme check here."""
    status, body = await _parse(
        client, normal_user_token_headers, "host=db dbname=app user=ann"
    )

    assert status == 200
    assert body["options"]["host"] == "db"  # type: ignore[index]


async def test_a_string_that_is_not_one_is_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    status, _ = await _parse(client, normal_user_token_headers, "nonsense")

    assert status == 422


async def test_an_empty_string_names_nothing_and_is_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """libpq reads it happily as an empty set; it would blank the whole form."""
    status, _ = await _parse(client, normal_user_token_headers, "")

    assert status == 422


async def test_a_string_that_names_no_host_is_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    status, _ = await _parse(client, normal_user_token_headers, "dbname=app")

    assert status == 422


async def test_a_port_that_is_not_a_number_is_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    status, _ = await _parse(
        client, normal_user_token_headers, "postgresql://db:nope/app"
    )

    assert status == 422


async def test_the_message_of_a_refusal_never_repeats_the_string(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A rejected string may still have carried a password."""
    response = await client.post(
        f"{BASE}/parse-url",
        headers=normal_user_token_headers,
        json={
            "adapter_type": "postgres",
            "url": "postgresql://ann:hunter2@db:nope/app",
        },
    )

    assert response.status_code == 422
    assert "hunter2" not in response.text


async def test_a_source_that_parses_nothing_answers_501(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A personal directory has no URL to take apart — the same shape as O8."""
    status, _ = await _parse(
        client, normal_user_token_headers, "file:///tmp", adapter_type="file"
    )

    assert status == 501


async def test_unknown_adapter_type_is_rejected(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    status, _ = await _parse(
        client, normal_user_token_headers, "postgresql://db/app", adapter_type="nope"
    )

    assert status == 422


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/parse-url",
        json={"adapter_type": "postgres", "url": "postgresql://db/app"},
    )

    assert response.status_code == 401
