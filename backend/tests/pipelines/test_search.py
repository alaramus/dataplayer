"""A pipeline found by the search: by its name, by its owner only (S5)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from tests.utils.search import hits, object_ids, person, search

PIPELINES = f"{settings.API_V1_STR}/pipelines"

pytestmark = pytest.mark.usefixtures("clean")


async def _pipeline(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    response = await client.post(PIPELINES, headers=headers, json={"name": name})
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def test_a_pipeline_is_found_by_its_name_and_opens_as_a_pipeline(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    pipeline_id = await _pipeline(client, owner.headers, f"Nightly {marker} load")

    lines = await search(client, owner.headers, f"{marker} nightly", mode="typing")

    [found] = [
        hit for hit in hits(lines, "objects:pipelines") if hit["target"]["object_id"] == pipeline_id
    ]
    assert found["title"] == f"Nightly {marker} load"
    assert found["open"] == "pipeline"
    assert found["facts"]["kind"] == "pipeline"
    assert found["facts"]["changed_at"] is not None
    assert found["match"]["match_class"] == "word"


async def test_somebody_else_s_pipeline_is_found_by_nobody(
    client: AsyncClient, db: AsyncSession, superuser_token_headers: dict[str, str]
) -> None:
    owner = await person(client, db)
    stranger = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    pipeline_id = await _pipeline(client, owner.headers, f"Ledger {marker}")

    assert pipeline_id in object_ids(await search(client, owner.headers, marker), "pipeline")
    assert object_ids(await search(client, stranger.headers, marker), "pipeline") == []
    assert object_ids(await search(client, superuser_token_headers, marker), "pipeline") == []
