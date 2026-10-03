"""An SSH key found by the search: by its name, by its owner only (S5, D146)."""

import uuid

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from tests.utils.search import Person, hits, object_ids, person, search

KEYS = f"{settings.API_V1_STR}/ssh-keys"


async def _key(client: AsyncClient, owner: Person, name: str) -> dict[str, str]:
    response = await client.post(f"{KEYS}/generate", headers=owner.headers, json={"name": name})
    assert response.status_code == 200, response.text
    made: dict[str, str] = response.json()
    return made


async def test_a_key_is_found_by_its_name_and_carries_no_key(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    key = await _key(client, owner, f"Deploy {marker}")

    lines = await search(client, owner.headers, f"deploy {marker}", mode="typing")

    [found] = [hit for hit in hits(lines, "objects:ssh_keys") if hit["target"]["object_id"] == key["id"]]
    assert found["open"] == "ssh_key"
    assert found["match"]["match_class"] == "exact"
    assert key["public_key"] not in str(lines)


async def test_a_key_is_found_by_its_fingerprint(client: AsyncClient, db: AsyncSession) -> None:
    owner = await person(client, db)
    key = await _key(client, owner, f"Build {uuid.uuid4().hex[:8]}")

    lines = await search(client, owner.headers, key["fingerprint"])

    [found] = [hit for hit in hits(lines, "objects:ssh_keys") if hit["target"]["object_id"] == key["id"]]
    assert found["match"]["field"] == "details"


async def test_somebody_else_s_key_is_found_by_nobody(
    client: AsyncClient, db: AsyncSession, superuser_token_headers: dict[str, str]
) -> None:
    owner = await person(client, db)
    stranger = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    key = await _key(client, owner, f"Bastion {marker}")

    assert key["id"] in object_ids(await search(client, owner.headers, marker), "ssh_key")
    assert object_ids(await search(client, stranger.headers, marker), "ssh_key") == []
    assert object_ids(await search(client, superuser_token_headers, marker), "ssh_key") == []
