"""Which SSH connection a database goes through, and whose (D282)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import options as adapter_options
from app.adapters import registry
from app.adapters.protocol import AdapterError
from app.adapters.tunnels import reach
from app.connectors.tunnels import OwnerTunnels
from app.core.config import settings
from app.users import crud

CONNECTORS = f"{settings.API_V1_STR}/connectors"
SSH_OPTIONS = {
    "auth_method": "password",
    "host": "example.invalid",
    "username": "deploy",
    "password": "secret",
}


async def _owner_id(db: AsyncSession) -> uuid.UUID:
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    return user.id


async def _create(
    client: AsyncClient, headers: dict[str, str], adapter_type: str, options: dict[str, object]
) -> dict[str, object]:
    created = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"{adapter_type} {uuid.uuid4().hex[:8]}",
            "adapter_type": adapter_type,
            "options": options,
        },
    )
    assert created.status_code == 200, created.text
    body: dict[str, object] = created.json()
    return body


def test_every_source_with_an_address_names_its_tunnel_the_same_way() -> None:
    for name in ("postgres", "mysql", "clickhouse", "redis"):
        schema = registry.get(name).options_schema
        assert adapter_options.tunnel_reference_names(schema) == {"ssh_tunnel"}, name
    assert adapter_options.tunnel_reference_names(registry.get("ssh").options_schema) == set()


async def test_directly_is_the_address_itself_and_asks_nobody() -> None:
    assert await reach(None, "", "db.example", 5432) == ("db.example", 5432)


async def test_a_tunnel_with_nothing_to_open_it_is_refused() -> None:
    with pytest.raises(AdapterError) as refused:
        await reach(None, str(uuid.uuid4()), "db.example", 5432)

    assert refused.value.error_kind == "config"


async def test_a_tunnel_that_is_not_a_connection_id_is_refused_on_save(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=normal_user_token_headers,
        json={
            "name": "through nowhere",
            "adapter_type": "redis",
            "options": {"auth_method": "no_auth", "host": "redis", "ssh_tunnel": "../etc"},
        },
    )

    assert response.status_code == 422


async def test_somebody_elses_ssh_connection_carries_nothing(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    theirs = await _create(client, superuser_token_headers, "ssh", SSH_OPTIONS)
    mine = await _create(client, normal_user_token_headers, "ssh", SSH_OPTIONS)
    owner = await _owner_id(db)

    with pytest.raises(AdapterError) as refused:
        await OwnerTunnels(owner).endpoint(uuid.UUID(str(theirs["id"])), "db", 5432)

    assert refused.value.error_kind == "config"
    assert "gone" in refused.value.message
    for made, headers in ((theirs, superuser_token_headers), (mine, normal_user_token_headers)):
        await client.delete(f"{CONNECTORS}/{made['id']}", headers=headers)


async def test_a_switched_off_ssh_connection_carries_nothing(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    ssh = await _create(client, normal_user_token_headers, "ssh", SSH_OPTIONS)
    switched = await client.patch(
        f"{CONNECTORS}/{ssh['id']}", headers=normal_user_token_headers, json={"enabled": False}
    )
    assert switched.status_code == 200, switched.text

    with pytest.raises(AdapterError) as refused:
        await OwnerTunnels(await _owner_id(db)).endpoint(
            uuid.UUID(str(ssh["id"])), "db", 5432
        )

    assert "switched off" in refused.value.message
    await client.delete(f"{CONNECTORS}/{ssh['id']}", headers=normal_user_token_headers)


async def test_a_connection_that_is_not_ssh_carries_nothing(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    other = await _create(
        client, normal_user_token_headers, "redis", {"auth_method": "no_auth", "host": "redis"}
    )

    with pytest.raises(AdapterError) as refused:
        await OwnerTunnels(await _owner_id(db)).endpoint(
            uuid.UUID(str(other["id"])), "db", 5432
        )

    assert "cannot carry a tunnel" in refused.value.message
    await client.delete(f"{CONNECTORS}/{other['id']}", headers=normal_user_token_headers)


async def test_an_ssh_connection_a_database_goes_through_is_not_deleted(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    ssh = await _create(client, normal_user_token_headers, "ssh", SSH_OPTIONS)
    database = await _create(
        client,
        normal_user_token_headers,
        "redis",
        {"auth_method": "no_auth", "host": "redis", "ssh_tunnel": ssh["id"]},
    )

    refused = await client.delete(f"{CONNECTORS}/{ssh['id']}", headers=normal_user_token_headers)

    assert refused.status_code == 409
    assert str(database["name"]) in refused.text
    await client.delete(f"{CONNECTORS}/{database['id']}", headers=normal_user_token_headers)
    deleted = await client.delete(f"{CONNECTORS}/{ssh['id']}", headers=normal_user_token_headers)
    assert deleted.status_code == 200
