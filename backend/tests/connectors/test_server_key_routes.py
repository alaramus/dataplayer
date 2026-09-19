"""The key a server proves itself with, as the connection form asks about it (D145)."""

from urllib.parse import urlsplit

from httpx import AsyncClient

from app.adapters.ssh import keys
from app.core.config import settings
from tests.utils import services

ROUTE = f"{settings.API_V1_STR}/connectors/server-key"


async def test_a_source_that_pins_no_server_key_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        ROUTE,
        headers=normal_user_token_headers,
        json={"adapter_type": "postgres", "options": {}},
    )

    assert response.status_code == 501


async def test_what_the_form_trusts_is_described_without_asking_the_server(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    pinned = keys.generate("ed25519", None).facts

    response = await client.post(
        ROUTE,
        headers=normal_user_token_headers,
        json={"adapter_type": "ssh", "options": {"host_key": pinned.public_key}},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["pinned"]["fingerprint"] == pinned.fingerprint
    assert body["presented"] is None
    assert body["matches"] is None


async def test_asking_the_server_needs_an_address(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        ROUTE,
        headers=normal_user_token_headers,
        json={"adapter_type": "ssh", "options": {}, "fetch": True},
    )

    assert response.status_code == 422


async def test_the_server_is_asked_and_compared_with_what_is_trusted(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    parts = urlsplit(services.SSH.require())
    address = {"host": parts.hostname, "port": parts.port}

    first = await client.post(
        ROUTE,
        headers=normal_user_token_headers,
        json={"adapter_type": "ssh", "options": address, "fetch": True},
    )
    presented = first.json()["presented"]
    again = await client.post(
        ROUTE,
        headers=normal_user_token_headers,
        json={
            "adapter_type": "ssh",
            "options": address | {"host_key": presented["public_key"]},
            "fetch": True,
        },
    )
    other = await client.post(
        ROUTE,
        headers=normal_user_token_headers,
        json={
            "adapter_type": "ssh",
            "options": address
            | {"host_key": keys.generate("ed25519", None).facts.public_key},
            "fetch": True,
        },
    )

    assert first.status_code == 200
    assert first.json()["matches"] is None
    assert again.json()["matches"] is True
    assert other.json()["matches"] is False
