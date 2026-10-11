"""Paste between connections through the API (D164, D165, D168)."""

import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlmodel import col, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.main import app
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


async def _finished(
    client: AsyncClient, headers: dict[str, str], answer: Response
) -> dict[str, Any]:
    """A transfer answers with its job at once; this waits for how it ended."""
    assert answer.status_code == 200, answer.text
    started = answer.json()
    assert started["outcome"] == "started"
    await app.state.job_runner.wait_for(uuid.UUID(started["job"]["id"]))
    job = await client.get(
        f"{settings.API_V1_STR}/jobs/{started['job']['id']}", headers=headers
    )
    assert job.status_code == 200, job.text
    result: dict[str, Any] = job.json()
    return result


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
    job = await _finished(client, normal_user_token_headers, copied)
    assert (job["kind"], job["state"], job["subject_id"]) == (
        "paste.transfer",
        "succeeded",
        destination,
    )
    # The top of a connection is called by the connection's name.
    assert job["message"].startswith("Copied 1 file to files ")
    [item] = job["parameters"]["items"]
    assert (item["name"], item["outcome"]) == (filename, "done")
    assert job["parameters"]["bytes_done"] == job["parameters"]["bytes_total"] == 17
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
    job = await _finished(client, normal_user_token_headers, moved)
    assert job["state"] == "succeeded"
    assert job["message"].startswith("Moved 1 file to files ")
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
    job = await _finished(client, normal_user_token_headers, saved)
    assert (job["state"], job["message"]) == (
        "succeeded",
        f"{name} saved in reports with 2 rows",
    )
    assert job["parameters"]["items"][0]["rows"] == 2
    assert (home / "reports" / name).read_bytes() == (
        b'\xef\xbb\xbf"id","code"\r\n"1","EU"\r\n"2","US"\r\n'
    )

    again = await client.post(
        f"{BASE}/{files}/paste",
        headers=normal_user_token_headers,
        json={**pair, "kind": "relation_csv", "name": name},
    )
    # A taken name answers at once, before any job, so Paste can ask.
    assert again.status_code == 409
    assert again.json()["detail"]["reason"] == "conflict"


async def test_a_fourth_transfer_is_refused_while_three_run(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
    db: AsyncSession,
) -> None:
    filename = f"fourth-{uuid.uuid4().hex}.txt"
    (home / filename).write_bytes(b"wait")
    source = await _files(client, normal_user_token_headers)
    destination = await _files(client, normal_user_token_headers, path="/reports")
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    running = [
        Job(owner_id=user.id, kind="paste.transfer", state="running") for _ in range(3)
    ]
    async with async_session_maker() as session:
        session.add_all(running)
        await session.commit()
    try:
        refused = await client.post(
            f"{BASE}/{destination}/paste",
            headers=normal_user_token_headers,
            json={
                "source_connector_id": source,
                "source_node_ids": [filename],
                "destination_node_id": None,
                "mode": "copy",
                "kind": "file_copy",
            },
        )
    finally:
        async with async_session_maker() as session:
            await session.exec(
                delete(Job).where(col(Job.id).in_([job.id for job in running]))
            )
            await session.commit()

    assert refused.status_code == 429
    assert refused.json()["detail"]["message"] == (
        "Three transfers are running — wait for one to finish"
    )
    assert not (home / "reports" / filename).exists()


async def test_what_cannot_be_read_as_rows_is_named_and_not_run(
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
            "source_node_ids": ["reports"],
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

    # A folder is not rows: both row kinds say so, and a file copy is not
    # among them, because a database holds no files.
    assert [
        (offer["kind"], offer["available"], offer["reason"])
        for offer in file_into_database.json()["offers"]
    ] == [
        ("rows_new_relation", False, "This cannot be read as rows"),
        ("rows_into_relation", False, "Tick the table the rows go into"),
    ]
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


async def test_a_csv_file_becomes_a_table_in_a_schema(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
    schema: str,
) -> None:
    filename = f"people-{uuid.uuid4().hex}.csv"
    (home / filename).write_text("id,name\n1,Ada\n2,Grace\n")
    files = await _files(client, normal_user_token_headers)
    database = await _postgres(client, normal_user_token_headers)
    pair = {
        "source_connector_id": files,
        "source_node_ids": [filename],
        "destination_node_id": schema,
        "mode": "copy",
    }

    offered = await client.post(
        f"{BASE}/{database}/paste/offers", headers=normal_user_token_headers, json=pair
    )
    assert offered.status_code == 200, offered.text
    create, into = offered.json()["offers"]
    assert create["kind"] == "rows_new_relation" and create["available"]
    assert create["workflow"] == "new-relation"
    assert [column["name"] for column in create["source_columns"]] == ["id", "name"]
    assert not into["available"]

    made = await client.post(
        f"{BASE}/{database}/paste",
        headers=normal_user_token_headers,
        json={
            **pair,
            "kind": "rows_new_relation",
            "name": "pasted_people",
            "columns": [
                {"source": "id", "target": "id", "type_code": "text"},
                {"source": "name", "target": "who", "type_code": "text"},
            ],
        },
    )
    assert made.status_code == 200, made.text
    assert made.json()["message"] == "pasted_people created with 2 rows"
    assert made.json()["reload_node_ids"] == [schema]

    rows = await client.post(
        f"{BASE}/{database}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.pasted_people", "limit": 10},
    )
    assert rows.status_code == 200, rows.text
    assert [column["name"] for column in rows.json()["columns"]] == ["id", "who"]
    assert sorted(rows.json()["rows"]) == [["1", "Ada"], ["2", "Grace"]]


async def test_rows_are_added_to_a_ticked_table(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
    schema: str,
) -> None:
    filename = f"regions-{uuid.uuid4().hex}.csv"
    (home / filename).write_text("region,label\n7,AS\n8,AF\n")
    files = await _files(client, normal_user_token_headers)
    database = await _postgres(client, normal_user_token_headers)
    pair = {
        "source_connector_id": files,
        "source_node_ids": [filename],
        "destination_node_id": schema,
        "target_node_id": f"{schema}.regions",
        "mode": "copy",
    }

    offered = await client.post(
        f"{BASE}/{database}/paste/offers", headers=normal_user_token_headers, json=pair
    )
    create, into = offered.json()["offers"]
    # Both are usable: a table in the schema, or these rows in the ticked one.
    assert create["available"] and into["available"]
    assert into["workflow"] == "into-relation"
    assert [column["name"] for column in into["target_columns"]] == ["id", "code"]

    added = await client.post(
        f"{BASE}/{database}/paste",
        headers=normal_user_token_headers,
        json={
            **pair,
            "kind": "rows_into_relation",
            "columns": [
                {"source": "region", "target": "id"},
                {"source": "label", "target": "code"},
            ],
        },
    )
    assert added.status_code == 200, added.text
    assert added.json()["message"] == "2 rows added"

    rows = await client.post(
        f"{BASE}/{database}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.regions", "limit": 10},
    )
    assert sorted(rows.json()["rows"]) == [["1", "EU"], ["2", "US"], ["7", "AS"], ["8", "AF"]]


async def test_a_value_the_table_cannot_read_is_named_and_nothing_is_written(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
    schema: str,
) -> None:
    filename = f"broken-{uuid.uuid4().hex}.csv"
    (home / filename).write_text("id,code\n9,OK\nnine,NO\n")
    files = await _files(client, normal_user_token_headers)
    database = await _postgres(client, normal_user_token_headers)

    refused = await client.post(
        f"{BASE}/{database}/paste",
        headers=normal_user_token_headers,
        json={
            "source_connector_id": files,
            "source_node_ids": [filename],
            "destination_node_id": schema,
            "target_node_id": f"{schema}.regions",
            "mode": "copy",
            "kind": "rows_into_relation",
            "columns": [
                {"source": "id", "target": "id"},
                {"source": "code", "target": "code"},
            ],
        },
    )

    assert refused.status_code == 422
    assert refused.json()["detail"]["message"] == "'nine' cannot be read by id (row 2)"
    rows = await client.post(
        f"{BASE}/{database}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.regions", "limit": 10},
    )
    assert len(rows.json()["rows"]) == 2


def _answer(offers: list[dict[str, object]]) -> list[tuple[object, object, object]]:
    return [(offer["kind"], offer["available"], offer["reason"]) for offer in offers]


async def _pair(
    client: AsyncClient,
    headers: dict[str, str],
    source: dict[str, object],
    destination: dict[str, object],
) -> list[dict[str, object]]:
    answer = await client.post(
        f"{BASE}/pair/offers",
        headers=headers,
        json={"source": source, "destination": destination},
    )
    assert answer.status_code == 200, answer.text
    offers: list[dict[str, object]] = answer.json()["offers"]
    return offers


@pytest.mark.usefixtures("home")
async def test_a_pair_says_what_it_could_do_before_anything_is_ticked(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    files = {"connector_id": await _files(client, normal_user_token_headers), "ticked": []}
    database = {
        "connector_id": await _postgres(client, normal_user_token_headers),
        "place": schema,
        "ticked": [],
    }

    assert _answer(await _pair(client, normal_user_token_headers, files, database)) == [
        ("rows_new_relation", False, "Tick a file or a table readable as rows"),
        ("rows_into_relation", False, "Tick a file or a table readable as rows"),
    ]
    # The other way is the same question with the sides swapped.
    assert _answer(await _pair(client, normal_user_token_headers, database, files)) == [
        ("relation_csv", False, "Tick a table or a view"),
    ]


async def test_a_pair_answers_from_the_ticks_of_both_sides(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
    schema: str,
) -> None:
    filename = f"pair-{uuid.uuid4().hex}.csv"
    (home / "reports" / filename).write_text("id,code\n3,PA\n")
    files = {
        "connector_id": await _files(client, normal_user_token_headers),
        "place": "reports",
        "ticked": [f"reports/{filename}"],
    }
    database = {
        "connector_id": await _postgres(client, normal_user_token_headers),
        "place": schema,
        "ticked": [f"{schema}.regions"],
    }

    # The CSV into the schema, or into the ticked table; the ticked table back
    # into the folder the files side stands in.
    assert _answer(await _pair(client, normal_user_token_headers, files, database)) == [
        ("rows_new_relation", True, None),
        ("rows_into_relation", True, None),
    ]
    [back] = await _pair(client, normal_user_token_headers, database, files)
    assert (back["kind"], back["available"], back["mode"]) == ("relation_csv", True, "copy")
    assert back["suggested_name"] == "regions.csv"


async def test_two_folders_offer_copy_and_move(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
) -> None:
    filename = f"pair-{uuid.uuid4().hex}.txt"
    (home / filename).write_bytes(b"pair")
    left = {"connector_id": await _files(client, normal_user_token_headers), "ticked": [filename]}
    right = {
        "connector_id": await _files(client, normal_user_token_headers, path="/reports"),
        "ticked": [],
    }

    offers = await _pair(client, normal_user_token_headers, left, right)
    assert [(offer["kind"], offer["mode"], offer["available"]) for offer in offers] == [
        ("file_copy", "copy", True),
        ("file_move", "move", True),
    ]
    assert _answer(await _pair(client, normal_user_token_headers, right, left)) == [
        ("file_copy", False, "Tick files or folders to copy"),
        ("file_move", False, "Tick files or folders to move"),
    ]


@pytest.mark.usefixtures("home")
async def test_a_pair_is_two_connections(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    files = await _files(client, normal_user_token_headers)

    answer = await client.post(
        f"{BASE}/pair/offers",
        headers=normal_user_token_headers,
        json={
            "source": {"connector_id": files, "ticked": []},
            "destination": {"connector_id": files, "ticked": []},
        },
    )

    assert answer.status_code == 422
    assert answer.json()["detail"]["code"] == "paste.same_connection"
