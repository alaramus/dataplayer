"""A map of what a person's connections can give each other (D174)."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.redis.options import RedisPassword
from app.connectors.models import Connector
from app.connectors.paste import map as interaction_map
from app.core.config import settings
from app.users import crud
from app.users.models import User
from tests.utils.database import working_postgres_options
from tests.utils.keyspace import redis_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/connectors"
MAP = f"{settings.API_V1_STR}/interactions/map"


async def _connector(
    client: AsyncClient, headers: dict[str, str], adapter_type: str, options: dict[str, Any]
) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={"name": f"map {uuid.uuid4()}", "adapter_type": adapter_type, "options": options},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


def _between(answer: dict[str, Any], ids: set[str]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """The arrows among these connections, each by its two ends."""
    return {
        (arrow["source_connector_id"], arrow["destination_connector_id"]): arrow["operations"]
        for arrow in answer["arrows"]
        if {arrow["source_connector_id"], arrow["destination_connector_id"]} <= ids
    }


def _titles(operations: list[dict[str, Any]]) -> list[str]:
    return [operation["title"] for operation in operations]


async def test_the_map_says_what_each_connection_gives_each_other(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    database = await _connector(client, headers, "postgres", working_postgres_options())
    files = await _connector(client, headers, "file", {"path": "/"})
    more_files = await _connector(client, headers, "file", {"path": "/"})
    redis = redis_options()
    redis_written: dict[str, Any] = redis.model_dump(mode="json")
    if isinstance(redis, RedisPassword):
        redis_written["password"] = redis.password.get_secret_value()
    keys = await _connector(client, headers, "redis", redis_written)

    response = await client.get(MAP, headers=headers)

    assert response.status_code == 200, response.text
    answer = response.json()
    nodes = {node["id"]: node for node in answer["connections"]}
    assert nodes[database]["type_title"] == "PostgreSQL"
    assert nodes[database]["category"] == "sql"
    assert nodes[files]["access"] == "own"
    arrows = _between(answer, {database, files, more_files, keys})
    assert _titles(arrows[(files, more_files)]) == ["Copy files", "Move files"]
    assert _titles(arrows[(more_files, files)]) == ["Copy files", "Move files"]
    assert _titles(arrows[(database, files)]) == ["Save as CSV"]
    assert _titles(arrows[(files, database)]) == ["Create a table", "Add rows to a table"]
    assert all(
        operation["available"] for operations in arrows.values() for operation in operations
    )
    assert _titles(arrows[(keys, files)]) == ["Save as CSV"]
    assert _titles(arrows[(files, keys)]) == ["Add rows to a table"]
    assert _titles(arrows[(keys, database)]) == ["Create a table", "Add rows to a table"]
    assert _titles(arrows[(database, keys)]) == ["Add rows to a table"]


async def test_what_a_grant_does_not_reach_says_what_it_needs(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    db: AsyncSession,
) -> None:
    owner = normal_user_token_headers
    email = random_email()
    theirs = await authentication_token_from_email(client=client, email=email, db=db)
    colleague = await crud.get_user_by_email(session=db, email=email)
    assert isinstance(colleague, User)
    shared = await _connector(client, owner, "postgres", working_postgres_options())
    granted = await client.put(
        f"{BASE}/{shared}/grants",
        headers=owner,
        json={"user_id": str(colleague.id), "access": "read"},
    )
    assert granted.status_code == 200, granted.text
    own = await _connector(client, theirs, "file", {"path": "/"})
    switched_off = await _connector(client, theirs, "file", {"path": "/"})
    stored = await db.get(Connector, uuid.UUID(switched_off))
    assert stored is not None
    stored.enabled = False
    db.add(stored)
    await db.commit()

    answer = (await client.get(MAP, headers=theirs)).json()

    assert {node["id"] for node in answer["connections"]} == {shared, own}
    assert {node["id"]: node["access"] for node in answer["connections"]}[shared] == "read"
    arrows = _between(answer, {shared, own})
    into = {operation["title"]: operation for operation in arrows[(own, shared)]}
    assert into["Create a table"]["available"] is False
    assert into["Create a table"]["reason"].startswith("Needs structure access to map ")
    assert into["Add rows to a table"]["reason"].startswith("Needs write access to map ")
    # Reading it is all saving it as CSV asks of it.
    assert [(op["title"], op["available"]) for op in arrows[(shared, own)]] == [
        ("Save as CSV", True)
    ]


async def test_more_connections_than_a_graph_holds_are_refused(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _connector(client, normal_user_token_headers, "file", {"path": "/"})
    await _connector(client, normal_user_token_headers, "file", {"path": "/"})
    monkeypatch.setattr(interaction_map, "MAX_MAP_CONNECTIONS", 1)

    response = await client.get(MAP, headers=normal_user_token_headers)

    assert response.status_code == 422
    assert "cannot be drawn" in response.json()["detail"]["message"]
