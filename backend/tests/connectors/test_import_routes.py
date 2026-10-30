import asyncio
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
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        await run(
            f"INSERT INTO {name}.regions VALUES (1, 'EU')"  # noqa: S608 -- fixture-owned schema.
        )
        yield name


@pytest.fixture
async def home(db: AsyncSession) -> Path:
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    return storage.create_home(user.id)


async def _postgres(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"import target {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _files(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"import source {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


def _csv(home: Path, body: str) -> str:
    """A file in the user's own storage, named the way the catalog names it."""
    name = f"import-{uuid.uuid4()}.csv"
    (home / name).write_text(body, encoding="utf-8")
    # A node id relative to the connector's root, which is how the catalog
    # names one; a leading slash would leave that root by the rule D8 sets.
    return name


def _move(
    schema: str, files: str, node: str, pairs: list[tuple[str, str]]
) -> dict[str, object]:
    return {
        "node_id": f"{schema}.regions",
        "source_connector_id": files,
        "source_node_id": node,
        "columns": [{"source": source, "target": target} for source, target in pairs],
    }


def _create(
    schema: str,
    files: str,
    node: str,
    name: str,
    columns: list[tuple[str, str, str]],
) -> dict[str, object]:
    return {
        "parent_node_id": schema,
        "name": name,
        "source_connector_id": files,
        "source_node_id": node,
        "columns": [
            {"source": source, "target": target, "type_code": type_code}
            for source, target, type_code in columns
        ],
    }


async def test_describes_how_a_schema_accepts_a_new_relation(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    target = await _postgres(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{target}/relations/options",
        headers=normal_user_token_headers,
        json={"parent_node_id": schema},
    )

    assert response.status_code == 200, response.text
    assert response.json()["supported"] is True
    assert "text" in {
        option["code"] for option in response.json()["column_type_options"]
    }


async def test_creates_a_relation_from_another_source_with_chosen_columns(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    home: Path,
) -> None:
    target = await _postgres(client, normal_user_token_headers)
    files = await _files(client, normal_user_token_headers)
    node = _csv(home, "id,code,ignored\n7,US,x\n8,AP,y\n")

    response = await client.post(
        f"{BASE}/{target}/relations/from-source",
        headers=normal_user_token_headers,
        json=_create(
            schema,
            files,
            node,
            "imported_regions",
            [("code", "region_code", "text"), ("id", "source_id", "integer")],
        ),
    )

    assert response.status_code == 200, response.text
    assert response.json()["inserted"] == 2
    rows = await client.post(
        f"{BASE}/{target}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.imported_regions", "limit": 10},
    )
    assert [column["name"] for column in rows.json()["columns"]] == [
        "region_code",
        "source_id",
    ]
    assert sorted(rows.json()["rows"]) == [["AP", "8"], ["US", "7"]]


async def test_a_folder_accepts_a_new_relation_and_keeps_it_as_a_file(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
) -> None:
    """The same command, the same dialog, a source that has no CREATE TABLE."""
    files = await _files(client, normal_user_token_headers)
    node = _csv(home, "id,code\n7,US\n8,AP\n")
    folder = f"made-{uuid.uuid4()}"
    (home / folder).mkdir()

    options = await client.post(
        f"{BASE}/{files}/relations/options",
        headers=normal_user_token_headers,
        json={"parent_node_id": folder},
    )
    created = await client.post(
        f"{BASE}/{files}/relations/from-source",
        headers=normal_user_token_headers,
        json=_create(
            folder,
            files,
            node,
            "regions",
            [("code", "region_code", "text"), ("id", "source_id", "text")],
        ),
    )

    assert options.status_code == 200, options.text
    assert options.json()["supported"] is True
    assert [
        option["code"] for option in options.json()["column_type_options"]
    ] == ["text"]
    assert created.status_code == 200, created.text
    assert created.json()["inserted"] == 2
    # The node the catalog would have listed, so the row opens like any other.
    assert created.json()["node"]["name"] == "regions.csv"

    rows = await client.post(
        f"{BASE}/{files}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": f"{folder}/regions.csv", "limit": 10},
    )
    assert [column["name"] for column in rows.json()["columns"]] == [
        "region_code",
        "source_id",
    ]
    assert rows.json()["rows"] == [["US", "7"], ["AP", "8"]]


async def test_a_folder_takes_a_large_source_as_a_file_written_by_a_job(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
) -> None:
    """Past one request's ceiling the file is written as the rows arrive (D45)."""
    files = await _files(client, normal_user_token_headers)
    node = _csv(home, "id,code\n" + "".join(f"{n},C{n}\n" for n in range(6000)))
    folder = f"made-{uuid.uuid4()}"
    (home / folder).mkdir()

    started = await client.post(
        f"{BASE}/{files}/relations/from-source",
        headers=normal_user_token_headers,
        json=_create(folder, files, node, "codes", [("code", "region_code", "text")]),
    )

    assert started.status_code == 200, started.text
    job = started.json()["job"]
    assert job["parameters"]["kind"] == "rows_new_file"
    for _ in range(100):
        state = await client.get(
            f"{settings.API_V1_STR}/jobs/{job['id']}", headers=normal_user_token_headers
        )
        if state.json()["finished_at"] is not None:
            break
        await asyncio.sleep(0.1)
    assert state.json()["state"] == "succeeded", state.json()["message"]
    lines = (home / folder / "codes.csv").read_text(encoding="utf-8-sig").splitlines()
    # Quoted as every CSV a transfer writes is (D165).
    assert lines[0] == '"region_code"'
    assert lines[1:3] == ['"C0"', '"C1"']
    assert len(lines) == 6001


async def test_a_file_is_not_a_container_for_a_new_relation(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
) -> None:
    """Answered rather than raised: the screen says why and offers nothing."""
    files = await _files(client, normal_user_token_headers)
    node = _csv(home, "id,code\n7,US\n")

    response = await client.post(
        f"{BASE}/{files}/relations/options",
        headers=normal_user_token_headers,
        json={"parent_node_id": node},
    )

    assert response.status_code == 200, response.text
    assert response.json()["supported"] is False
    assert response.json()["reason"]


async def test_a_name_already_taken_in_the_folder_is_refused(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    home: Path,
) -> None:
    files = await _files(client, normal_user_token_headers)
    node = _csv(home, "id,code\n7,US\n")
    folder = f"made-{uuid.uuid4()}"
    (home / folder).mkdir()
    (home / folder / "regions.csv").write_text("kept\n", encoding="utf-8")

    response = await client.post(
        f"{BASE}/{files}/relations/from-source",
        headers=normal_user_token_headers,
        json=_create(folder, files, node, "regions", [("code", "code", "text")]),
    )

    assert response.status_code == 422, response.text
    assert (home / folder / "regions.csv").read_text(encoding="utf-8") == "kept\n"


async def test_moves_rows_from_a_file_into_a_relation(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    home: Path,
) -> None:
    target = await _postgres(client, normal_user_token_headers)
    files = await _files(client, normal_user_token_headers)
    node = _csv(home, "id,code\n7,US\n8,AP\n")

    response = await client.post(
        f"{BASE}/{target}/import",
        headers=normal_user_token_headers,
        json=_move(schema, files, node, [("id", "id"), ("code", "code")]),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"kind": "moved", "inserted": 2, "truncated": False}

    rows = await client.post(
        f"{BASE}/{target}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.regions", "limit": 10},
    )
    assert sorted(row[1] for row in rows.json()["rows"]) == ["AP", "EU", "US"]


async def test_more_rows_than_one_request_carries_start_a_job(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    home: Path,
) -> None:
    """Past the ceiling the rows go as a job a block at a time (D43)."""
    target = await _postgres(client, normal_user_token_headers)
    files = await _files(client, normal_user_token_headers)
    lines = "".join(f"{n},C{n % 100}\n" for n in range(2, 6003))
    node = _csv(home, "id,code\n" + lines)

    response = await client.post(
        f"{BASE}/{target}/import",
        headers=normal_user_token_headers,
        json=_move(schema, files, node, [("id", "id"), ("code", "code")]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "started"
    assert body["job"]["kind"] == "paste.transfer"
    assert body["job"]["parameters"]["kind"] == "rows_into_relation"


@pytest.mark.usefixtures("home")
async def test_a_file_too_large_for_one_request_is_loaded_by_a_job(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    """The file is kept in its owner's storage while the job reads it (D45)."""
    target = await _postgres(client, normal_user_token_headers)
    body = "id,code" + chr(10) + "".join(f"{n},C{n}" + chr(10) for n in range(6000))

    response = await client.post(
        f"{BASE}/{target}/load-csv-job",
        headers=normal_user_token_headers,
        files={"file": ("big.csv", body.encode(), "text/csv")},
        data={"node_id": schema, "params": "{}"},
    )

    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["outcome"] == "started"
    assert answer["job"]["parameters"]["source_upload"].endswith(".csv")
    assert answer["job"]["parameters"]["name"] == "big"


@pytest.mark.usefixtures("home", "schema")
async def test_a_large_file_makes_the_new_schema_it_asks_for(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """The schema is made once the file is in hand, then the job fills it (D45)."""
    target = await _postgres(client, normal_user_token_headers)
    fresh = f"csv_job_{uuid.uuid4().hex[:8]}"
    body = "id,code\n" + "".join(f"{n},C{n}\n" for n in range(6000))
    params = f'{{"schema_name": "{fresh}", "create_schema": true}}'

    try:
        response = await client.post(
            f"{BASE}/{target}/load-csv-job",
            headers=normal_user_token_headers,
            files={"file": ("big.csv", body.encode(), "text/csv")},
            data={"node_id": "public", "params": params},
        )

        assert response.status_code == 200, response.text
        assert response.json()["job"]["parameters"]["destination_node_id"] == fresh
        schemas = await client.get(f"{BASE}/{target}/catalog", headers=normal_user_token_headers)
        assert fresh in {node["id"] for node in schemas.json()}
    finally:
        await run(f'DROP SCHEMA IF EXISTS "{fresh}" CASCADE')  # noqa: S608 -- generated test name.


async def test_a_value_the_target_cannot_read_is_named_and_nothing_is_written(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    home: Path,
) -> None:
    target = await _postgres(client, normal_user_token_headers)
    files = await _files(client, normal_user_token_headers)
    node = _csv(home, "id,code\n7,US\nnope,AP\n")

    response = await client.post(
        f"{BASE}/{target}/import",
        headers=normal_user_token_headers,
        json=_move(schema, files, node, [("id", "id"), ("code", "code")]),
    )

    assert response.status_code == 422
    assert "nope" in response.text

    rows = await client.post(
        f"{BASE}/{target}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.regions", "limit": 10},
    )
    assert [row[1] for row in rows.json()["rows"]] == ["EU"]


async def test_the_preview_shows_the_pairing_and_says_there_is_more(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    home: Path,
) -> None:
    target = await _postgres(client, normal_user_token_headers)
    files = await _files(client, normal_user_token_headers)
    lines = "\n".join(f"{n},c{n}" for n in range(1, 41))
    node = _csv(home, f"id,code\n{lines}\n")

    response = await client.post(
        f"{BASE}/{target}/import/preview",
        headers=normal_user_token_headers,
        json=_move(schema, files, node, [("code", "code"), ("id", "id")]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # The order of the pairing, not of the file.
    assert body["columns"] == ["code", "id"]
    assert body["rows"][0] == ["c1", "1"]
    assert len(body["rows"]) == 20
    assert body["more"] is True


async def test_the_preview_writes_nothing(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    home: Path,
) -> None:
    target = await _postgres(client, normal_user_token_headers)
    files = await _files(client, normal_user_token_headers)
    node = _csv(home, "id,code\n7,US\n")

    await client.post(
        f"{BASE}/{target}/import/preview",
        headers=normal_user_token_headers,
        json=_move(schema, files, node, [("id", "id"), ("code", "code")]),
    )

    rows = await client.post(
        f"{BASE}/{target}/fetch",
        headers=normal_user_token_headers,
        json={"node_id": f"{schema}.regions", "limit": 10},
    )
    assert [row[1] for row in rows.json()["rows"]] == ["EU"]


async def test_a_column_neither_side_has_is_refused(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
    home: Path,
) -> None:
    target = await _postgres(client, normal_user_token_headers)
    files = await _files(client, normal_user_token_headers)
    node = _csv(home, "id,code\n7,US\n")

    missing_source = await client.post(
        f"{BASE}/{target}/import",
        headers=normal_user_token_headers,
        json=_move(schema, files, node, [("nope", "code")]),
    )
    missing_target = await client.post(
        f"{BASE}/{target}/import",
        headers=normal_user_token_headers,
        json=_move(schema, files, node, [("code", "nope")]),
    )
    twice = await client.post(
        f"{BASE}/{target}/import",
        headers=normal_user_token_headers,
        json=_move(schema, files, node, [("id", "code"), ("code", "code")]),
    )

    assert missing_source.status_code == 422
    assert "no column" in missing_source.text
    assert missing_target.status_code == 422
    assert twice.status_code == 422


async def test_a_connector_the_caller_does_not_own_is_not_a_source(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    schema: str,
) -> None:
    target = await _postgres(client, normal_user_token_headers)

    response = await client.post(
        f"{BASE}/{target}/import",
        headers=normal_user_token_headers,
        json=_move(schema, str(uuid.uuid4()), "a.csv", [("code", "code")]),
    )

    assert response.status_code == 404


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        f"{BASE}/{uuid.uuid4()}/import",
        json={
            "node_id": "public.x",
            "source_connector_id": str(uuid.uuid4()),
            "source_node_id": "/a.csv",
            "columns": [{"source": "a", "target": "b"}],
        },
    )
    assert response.status_code == 401
