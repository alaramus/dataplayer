"""Declaring a table over a Redis folder through the API (D170), and
referencing its key from another source (D172)."""

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
from app.users import crud, storage
from app.users.models import User
from tests.utils.database import working_postgres_options
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options
from tests.utils.relation_fixture import make_schema, run
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/connectors"
DECLARED = f"{settings.API_V1_STR}/declared-references"
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


# --- a reference to its key (D172) ----------------------------------------


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


async def test_its_key_is_an_end_of_a_reference_followed_both_ways(
    client: AsyncClient, normal_user_token_headers: dict[str, str], schema: str
) -> None:
    headers = normal_user_token_headers
    options = redis_options()
    keys = redis.Redis(host=options.host, port=options.port, db=options.database)
    try:
        await keys.hset("region:north", mapping={"label": "Northern"})
        await keys.hset("region:south", mapping={"label": "Southern"})
    finally:
        await keys.aclose()
    await run(
        f"INSERT INTO {schema}.regions (id, code) "  # noqa: S608 -- fixture-owned.
        "VALUES (7, 'north'), (8, 'south')"
    )
    redis_id = await _connector(client, headers)
    await client.put(
        f"{BASE}/{redis_id}/tables",
        headers=headers,
        json=_declaration(folder_id(DB, "region:"), name="regions", columns=[{"name": "label"}]),
    )
    created = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"declared {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    postgres_id = str(created.json()["id"])
    regions = table_id(DB, "region:")

    def end(connector_id: str, node_id: str, column: str) -> dict[str, str]:
        return {"connector_id": connector_id, "node_id": node_id, "column": column}

    refused = await client.post(
        f"{DECLARED}/",
        headers=headers,
        json={"ends": [end(postgres_id, f"{schema}.regions", "code"), end(redis_id, regions, "label")]},
    )
    drawn = await client.post(
        f"{DECLARED}/",
        headers=headers,
        json={"ends": [end(postgres_id, f"{schema}.regions", "code"), end(redis_id, regions, "key")]},
    )
    assert refused.status_code == 422
    assert "cannot look up" in refused.text
    assert drawn.status_code == 200, drawn.text
    reference = drawn.json()["id"]

    into_redis = await client.post(
        f"{BASE}/{postgres_id}/references",
        headers=headers,
        json={
            "node_id": f"{schema}.regions",
            "reference": f"declared:{reference}:a",
            "values": [{"column": "code", "value": "north"}],
        },
    )
    target = into_redis.json()
    rows = await client.post(
        f"{BASE}/{redis_id}/fetch",
        headers=headers,
        json={"node_id": target["node"]["id"], "filters": target["filters"]},
    )
    arrow = await client.post(
        f"{BASE}/{redis_id}/fetch", headers=headers, json={"node_id": regions}
    )
    back = await client.post(
        f"{BASE}/{redis_id}/references",
        headers=headers,
        json={
            "node_id": regions,
            "reference": f"declared:{reference}:b",
            "values": [{"column": "key", "value": "south"}],
        },
    )

    assert target["node"] == {**target["node"], "id": regions, "kind": "table"}
    assert target["filters"] == [{"column": "key", "op": "eq", "value": "north"}]
    assert rows.json()["rows"] == [["north", "Northern"]]
    assert [ref["columns"] for ref in arrow.json()["references"]] == [["key"]]
    assert back.json()["node"]["id"] == f"{schema}.regions"
    assert back.json()["filters"] == [{"column": "code", "op": "eq", "value": "south"}]


# --- rows added to it from elsewhere (D173) ---------------------------------


async def test_rows_from_a_csv_become_hashes_of_the_table(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    headers = normal_user_token_headers
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    filename = f"users-{uuid.uuid4().hex}.csv"
    (storage.create_home(user.id) / filename).write_text("id,name\n7,Eve\n8,Bob\n")
    redis_id = await _connector(client, headers)
    declared = await client.put(
        f"{BASE}/{redis_id}/tables", headers=headers, json=_declaration(columns=[{"name": "name"}])
    )
    assert declared.status_code == 200, declared.text
    made = await client.post(
        f"{BASE}/",
        headers=headers,
        json={"name": f"files {uuid.uuid4()}", "adapter_type": "file", "options": {"path": "/"}},
    )
    files_id = made.json()["id"]
    pair = {
        "source_connector_id": files_id,
        "source_node_ids": [filename],
        "destination_node_id": database_id(DB),
        "target_node_id": TABLE,
        "mode": "copy",
    }

    offers = await client.post(f"{BASE}/{redis_id}/paste/offers", headers=headers, json=pair)
    into = next(
        offer for offer in offers.json()["offers"] if offer["kind"] == "rows_into_relation"
    )
    added = await client.post(
        f"{BASE}/{redis_id}/paste",
        headers=headers,
        json={
            **pair,
            "kind": "rows_into_relation",
            "columns": [
                {"source": "id", "target": "key"},
                {"source": "name", "target": "name"},
            ],
        },
    )
    rows = await client.post(f"{BASE}/{redis_id}/fetch", headers=headers, json={"node_id": TABLE})

    assert into["available"], into
    assert [column["name"] for column in into["target_columns"]] == ["key", "name"]
    assert added.status_code == 200, added.text
    assert added.json()["message"] == "2 rows added"
    assert rows.json()["rows"] == [["7", "Eve"], ["8", "Bob"]]


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
