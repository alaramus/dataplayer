"""Declaring a table over a Redis folder through the API (D170)."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import redis.asyncio as redis
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.redis.keyspace import database_id, folder_id, key_id, table_id
from app.adapters.redis.options import RedisPassword
from app.core.config import settings
from app.users import crud
from app.users.models import User
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/connectors"
DB = chosen_database()
USERS = folder_id(DB, "user:")
TABLE = table_id(DB, "user:")


@pytest.fixture(autouse=True)
async def keyspace() -> AsyncGenerator[None]:
    async for _ in empty_keyspace():
        yield


@pytest.fixture
async def colleague(
    client: AsyncClient, db: AsyncSession
) -> tuple[User, dict[str, str]]:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await crud.get_user_by_email(session=db, email=email)
    assert user is not None
    return user, headers


def _options() -> dict[str, Any]:
    options = redis_options()
    written: dict[str, Any] = options.model_dump(mode="json")
    if isinstance(options, RedisPassword):
        written["password"] = options.password.get_secret_value()
    return written


async def _connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"redis {uuid.uuid4()}",
            "adapter_type": "redis",
            "options": _options(),
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _seed() -> None:
    options = redis_options()
    client = redis.Redis(host=options.host, port=options.port, db=options.database)
    try:
        await client.hset("user:1", mapping={"name": "Ada", "email": "ada@example.com"})
        await client.hset("user:2", mapping={"name": "Grace"})
    finally:
        await client.aclose()


async def _grant(
    client: AsyncClient, headers: dict[str, str], connector_id: str, user: User, access: str
) -> None:
    response = await client.put(
        f"{BASE}/{connector_id}/grants",
        headers=headers,
        json={"user_id": str(user.id), "access": access},
    )
    assert response.status_code == 200, response.text


def _declaration(node_id: str = USERS, **changes: Any) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "name": "users",
        "columns": [{"name": "name", "type": "text"}, {"name": "email", "type": "text"}],
        **changes,
    }


async def test_a_declared_table_stands_beside_its_folder_and_reads_as_rows(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    await _seed()
    headers = normal_user_token_headers
    connector_id = await _connector(client, headers)

    offer = await client.post(
        f"{BASE}/{connector_id}/tables/offer", headers=headers, json={"node_id": USERS}
    )
    proposal = await client.post(
        f"{BASE}/{connector_id}/tables/proposal", headers=headers, json={"node_id": USERS}
    )
    declared = await client.put(
        f"{BASE}/{connector_id}/tables", headers=headers, json=_declaration()
    )
    listed = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=headers,
        params={"node_id": database_id(DB)},
    )
    rows = await client.post(
        f"{BASE}/{connector_id}/fetch", headers=headers, json={"node_id": TABLE}
    )

    assert offer.json() == {"available": True, "reason": None, "declared": False}
    assert proposal.status_code == 200
    assert [column["name"] for column in proposal.json()["columns"]] == ["name", "email"]
    assert declared.status_code == 200, declared.text
    assert declared.json() == {
        "message": "users declared",
        "reload_node_ids": [database_id(DB)],
    }
    assert [(node["kind"], node["name"]) for node in listed.json()] == [
        ("directory", "user:"),
        ("table", "users"),
    ]
    assert rows.status_code == 200, rows.text
    assert rows.json()["rows"] == [["1", "Ada", "ada@example.com"], ["2", "Grace", None]]
    # Every node of it can now be saved whole (D171).
    assert rows.json()["export_supported"] is True


async def test_changing_it_replaces_the_one_over_the_same_folder(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    connector_id = await _connector(client, headers)
    await client.put(f"{BASE}/{connector_id}/tables", headers=headers, json=_declaration())

    changed = await client.put(
        f"{BASE}/{connector_id}/tables",
        headers=headers,
        json=_declaration(TABLE, name="people", columns=[{"name": "name"}]),
    )
    offer = await client.post(
        f"{BASE}/{connector_id}/tables/offer", headers=headers, json={"node_id": TABLE}
    )
    listed = await client.get(
        f"{BASE}/{connector_id}/catalog",
        headers=headers,
        params={"node_id": database_id(DB)},
    )

    assert changed.json()["message"] == "people changed"
    assert offer.json()["declared"] is True
    assert [node["name"] for node in listed.json() if node["kind"] == "table"] == ["people"]


async def test_removing_it_leaves_every_key(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    await _seed()
    headers = normal_user_token_headers
    connector_id = await _connector(client, headers)
    await client.put(f"{BASE}/{connector_id}/tables", headers=headers, json=_declaration())

    removed = await client.delete(
        f"{BASE}/{connector_id}/tables", headers=headers, params={"node_id": TABLE}
    )
    again = await client.delete(
        f"{BASE}/{connector_id}/tables", headers=headers, params={"node_id": USERS}
    )
    listed = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=headers, params={"node_id": USERS}
    )

    assert removed.status_code == 200
    assert removed.json()["message"] == "users removed; its keys are as they were"
    assert again.status_code == 404
    assert {node["id"] for node in listed.json()} == {
        key_id(DB, "user:1"),
        key_id(DB, "user:2"),
    }


async def test_only_structure_declares_and_everybody_who_reads_sees_it(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    headers = normal_user_token_headers
    user, theirs = colleague
    connector_id = await _connector(client, headers)
    await client.put(f"{BASE}/{connector_id}/tables", headers=headers, json=_declaration())
    await _grant(client, headers, connector_id, user, "write")

    listed = await client.get(
        f"{BASE}/{connector_id}/catalog", headers=theirs, params={"node_id": database_id(DB)}
    )
    offer = await client.post(
        f"{BASE}/{connector_id}/tables/offer", headers=theirs, json={"node_id": TABLE}
    )
    change = await client.put(
        f"{BASE}/{connector_id}/tables", headers=theirs, json=_declaration(name="mine")
    )
    removal = await client.delete(
        f"{BASE}/{connector_id}/tables", headers=theirs, params={"node_id": TABLE}
    )
    proposal = await client.post(
        f"{BASE}/{connector_id}/tables/proposal", headers=theirs, json={"node_id": USERS}
    )

    assert [node["name"] for node in listed.json() if node["kind"] == "table"] == ["users"]
    assert offer.json() == {
        "available": False,
        "reason": "This needs structure access to the connection",
        "declared": True,
    }
    assert (change.status_code, removal.status_code, proposal.status_code) == (403, 403, 403)

    await _grant(client, headers, connector_id, user, "structure")
    allowed = await client.put(
        f"{BASE}/{connector_id}/tables", headers=theirs, json=_declaration(name="mine")
    )
    assert allowed.status_code == 200, allowed.text


async def test_what_cannot_carry_a_table_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    connector_id = await _connector(client, headers)

    nothing = await client.post(
        f"{BASE}/{connector_id}/tables/offer", headers=headers, json={}
    )
    a_key = await client.post(
        f"{BASE}/{connector_id}/tables/offer",
        headers=headers,
        json={"node_id": key_id(DB, "user:1")},
    )
    declared_on_a_key = await client.put(
        f"{BASE}/{connector_id}/tables",
        headers=headers,
        json=_declaration(key_id(DB, "user:1")),
    )
    called_key = await client.put(
        f"{BASE}/{connector_id}/tables",
        headers=headers,
        json=_declaration(columns=[{"name": "key"}]),
    )

    assert nothing.json()["reason"] == "Select a folder to describe as a table"
    assert a_key.json()["reason"] == "Select a folder to describe as a table"
    assert declared_on_a_key.status_code == 422
    assert called_key.status_code == 422
    assert "cannot be called key" in called_key.json()["detail"]["message"]


async def test_a_source_without_the_capability_answers_501(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={"name": f"files {uuid.uuid4()}", "adapter_type": "file", "options": {"path": "/"}},
    )
    connector_id = response.json()["id"]

    offer = await client.post(
        f"{BASE}/{connector_id}/tables/offer",
        headers=normal_user_token_headers,
        json={"node_id": "reports"},
    )

    assert offer.status_code == 501
