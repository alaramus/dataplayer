"""Paste between connections through the API (D164, D165)."""

import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud, storage
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def home(db: AsyncSession) -> Path:
    """The personal directory of the user the route tests sign in as."""
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    home = storage.create_home(user.id)
    (home / "reports").mkdir(exist_ok=True)
    return home


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        await run(f"INSERT INTO {name}.regions VALUES (1, 'EU'), (2, 'US')")  # noqa: S608 -- a fixture's own schema name
        yield name


async def _files(client: AsyncClient, headers: dict[str, str], path: str = "/") -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": path},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _postgres(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"database {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def test_a_file_is_copied_between_two_connections(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
) -> None:
    filename = f"copy-{uuid.uuid4().hex}.txt"
    (home / filename).write_bytes(b"copy across roots")
    source = await _files(client, normal_user_token_headers)
    destination = await _files(client, normal_user_token_headers, path="/reports")
    pair = {
        "source_connector_id": source,
        "source_node_ids": [filename],
        "destination_node_id": None,
        "mode": "copy",
    }

    offered = await client.post(
        f"{BASE}/{destination}/paste/offers",
        headers=normal_user_token_headers,
        json=pair,
    )
    assert offered.status_code == 200, offered.text
    assert [(offer["kind"], offer["available"]) for offer in offered.json()["offers"]] == [
        ("file_copy", True)
    ]

    copied = await client.post(
        f"{BASE}/{destination}/paste",
        headers=normal_user_token_headers,
        json={**pair, "kind": "file_copy"},
    )
    assert copied.status_code == 200, copied.text
    assert copied.json()["message"] == "1 file copied"
    assert copied.json()["reload_node_ids"] == [None]
    assert (home / "reports" / filename).read_bytes() == (home / filename).read_bytes()


async def test_a_file_is_moved_between_two_connections(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
) -> None:
    filename = f"move-{uuid.uuid4().hex}.txt"
    (home / filename).write_bytes(b"move across roots")
    source = await _files(client, normal_user_token_headers)
    destination = await _files(client, normal_user_token_headers, path="/reports")
    pair = {
        "source_connector_id": source,
        "source_node_ids": [filename],
        "destination_node_id": None,
        "mode": "move",
    }

    offered = await client.post(
        f"{BASE}/{destination}/paste/offers",
        headers=normal_user_token_headers,
        json=pair,
    )
    [offer] = offered.json()["offers"]
    assert offer["kind"] == "file_move"
    assert offer["changes_source"] and not offer["can_replace"]

    moved = await client.post(
        f"{BASE}/{destination}/paste",
        headers=normal_user_token_headers,
        json={**pair, "kind": "file_move"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["message"] == "1 file moved"
    assert not (home / filename).exists()
    assert (home / "reports" / filename).read_bytes() == b"move across roots"


async def test_a_table_is_saved_as_csv_in_a_folder(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
    schema: str,
) -> None:
    database = await _postgres(client, normal_user_token_headers)
    files = await _files(client, normal_user_token_headers)
    name = f"regions-{uuid.uuid4().hex}.csv"
    pair = {
        "source_connector_id": database,
        "source_node_ids": [f"{schema}.regions"],
        "destination_node_id": "reports",
        "mode": "copy",
    }

    offered = await client.post(
        f"{BASE}/{files}/paste/offers", headers=normal_user_token_headers, json=pair
    )
    assert offered.status_code == 200, offered.text
    [offer] = offered.json()["offers"]
    assert offer["kind"] == "relation_csv"
    assert offer["available"] and offer["converts"]
    assert offer["suggested_name"] == "regions.csv"

    saved = await client.post(
        f"{BASE}/{files}/paste",
        headers=normal_user_token_headers,
        json={**pair, "kind": "relation_csv", "name": name},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["rows"] == 2
    assert saved.json()["reload_node_ids"] == ["reports"]
    assert (home / "reports" / name).read_bytes() == (
        b'\xef\xbb\xbf"id","code"\r\n"1","EU"\r\n"2","US"\r\n'
    )

    again = await client.post(
        f"{BASE}/{files}/paste",
        headers=normal_user_token_headers,
        json={**pair, "kind": "relation_csv", "name": name},
    )
    assert again.status_code == 409
    assert again.json()["detail"]["reason"] == "conflict"


async def test_nothing_is_offered_where_nothing_can_take_the_clipboard(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
    schema: str,
) -> None:
    filename = f"stays-{uuid.uuid4().hex}.txt"
    (home / filename).write_bytes(b"stays")
    database = await _postgres(client, normal_user_token_headers)
    files = await _files(client, normal_user_token_headers)

    file_into_database = await client.post(
        f"{BASE}/{database}/paste/offers",
        headers=normal_user_token_headers,
        json={
            "source_connector_id": files,
            "source_node_ids": [filename],
            "destination_node_id": schema,
            "mode": "copy",
        },
    )
    cut_table = await client.post(
        f"{BASE}/{files}/paste/offers",
        headers=normal_user_token_headers,
        json={
            "source_connector_id": database,
            "source_node_ids": [f"{schema}.regions"],
            "destination_node_id": None,
            "mode": "move",
        },
    )
    run_anyway = await client.post(
        f"{BASE}/{database}/paste",
        headers=normal_user_token_headers,
        json={
            "source_connector_id": files,
            "source_node_ids": [filename],
            "destination_node_id": schema,
            "mode": "copy",
            "kind": "file_copy",
        },
    )

    assert file_into_database.json() == {"offers": []}
    assert cut_table.json() == {"offers": []}
    assert run_anyway.status_code == 501


async def test_the_clipboard_offer_says_what_a_selection_can_be_held_as(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
    schema: str,
) -> None:
    filename = f"held-{uuid.uuid4().hex}.txt"
    (home / filename).write_bytes(b"held")
    database = await _postgres(client, normal_user_token_headers)
    files = await _files(client, normal_user_token_headers)

    async def offer(connector_id: str, node_ids: list[str]) -> dict[str, object]:
        response = await client.post(
            f"{BASE}/{connector_id}/clipboard/offer",
            headers=normal_user_token_headers,
            json={"node_ids": node_ids},
        )
        assert response.status_code == 200, response.text
        body: dict[str, object] = response.json()
        return body

    assert await offer(database, [f"{schema}.regions"]) == {
        "can_copy": {"available": True, "reason": None},
        "can_cut": None,
    }
    assert await offer(database, [schema]) == {
        "can_copy": {"available": False, "reason": "Copy a table or a view"},
        "can_cut": None,
    }
    assert await offer(database, []) == {
        "can_copy": {"available": False, "reason": "Tick a row to use this"},
        "can_cut": None,
    }
    assert await offer(files, [filename]) == {
        "can_copy": {"available": True, "reason": None},
        "can_cut": {"available": True, "reason": None},
    }
