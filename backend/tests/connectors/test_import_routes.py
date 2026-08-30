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
