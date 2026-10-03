"""A dashboard found by the search: its owner's, and one shared with them (S5, D129)."""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.metrics.dashboards import Dashboard
from tests.utils.search import Person, hits, object_ids, person, search

DASHBOARDS = f"{settings.API_V1_STR}/metrics/dashboards"


@pytest.fixture(autouse=True)
async def clean() -> AsyncIterator[None]:
    yield
    async with async_session_maker() as session:
        await session.exec(delete(Dashboard))
        await session.commit()


async def _dashboard(client: AsyncClient, owner: Person, name: str) -> str:
    created = await client.post(DASHBOARDS, headers=owner.headers, json={"name": name})
    assert created.status_code == 200, created.text
    return str(created.json()["id"])


async def _share(client: AsyncClient, owner: Person, dashboard_id: str, reader: Person) -> None:
    granted = await client.put(
        f"{DASHBOARDS}/{dashboard_id}/grants",
        headers=owner.headers,
        json={"user_id": str(reader.id), "access": "read"},
    )
    assert granted.status_code == 200, granted.text


async def test_a_dashboard_is_found_by_its_owner(client: AsyncClient, db: AsyncSession) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    dashboard_id = await _dashboard(client, owner, f"Hosts {marker}")

    lines = await search(client, owner.headers, f"hosts {marker}", mode="typing")

    [found] = [
        hit for hit in hits(lines, "objects:dashboards") if hit["target"]["object_id"] == dashboard_id
    ]
    assert found["match"]["match_class"] == "exact"
    assert found["access"] == "own"
    assert found["open"] == "dashboard"
    assert found["detail"] == "Dashboard"
    assert found["facts"]["owner"] is None


async def test_a_dashboard_shared_with_the_person_is_found_and_names_its_owner(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db, full_name="Ada Owner")
    reader = await person(client, db)
    stranger = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    dashboard_id = await _dashboard(client, owner, f"Fleet {marker}")
    await _share(client, owner, dashboard_id, reader)

    [found] = [
        hit
        for hit in hits(await search(client, reader.headers, marker), "objects:dashboards")
        if hit["target"]["object_id"] == dashboard_id
    ]

    assert found["access"] == "read"
    assert found["facts"]["owner"] == "Ada Owner"
    assert "Ada Owner" in found["detail"]
    assert object_ids(await search(client, stranger.headers, marker), "dashboard") == []


async def test_a_revoked_dashboard_is_no_longer_found(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    reader = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    dashboard_id = await _dashboard(client, owner, f"Racks {marker}")
    await _share(client, owner, dashboard_id, reader)
    assert dashboard_id in object_ids(await search(client, reader.headers, marker), "dashboard")

    revoked = await client.delete(
        f"{DASHBOARDS}/{dashboard_id}/grants/{reader.id}", headers=owner.headers
    )
    assert revoked.status_code == 200, revoked.text

    assert object_ids(await search(client, reader.headers, marker), "dashboard") == []
