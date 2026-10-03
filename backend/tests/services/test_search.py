"""A service found by the search: by its connection's name as it is now (S5, D199)."""

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlmodel import col, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import async_session_maker
from app.services.models import ManagedService
from tests.utils.search import (
    Person,
    connection,
    grant,
    hits,
    object_ids,
    person,
    search,
)

CONNECTORS = f"{settings.API_V1_STR}/connectors"
GROUP = "objects:services"

_made: list[uuid.UUID] = []


@pytest.fixture(autouse=True)
async def forget_services() -> AsyncGenerator[None]:
    """Rows written here are nobody's containers; other tests count the rows."""
    yield
    async with async_session_maker() as session:
        await session.exec(delete(ManagedService).where(col(ManagedService.id).in_(_made)))
        await session.commit()
    _made.clear()


async def _service(owner: Person, kept_name: str, connector_id: str | None = None) -> str:
    service_id = uuid.uuid4()
    async with async_session_maker() as session:
        session.add(
            ManagedService(
                id=service_id,
                owner_id=owner.id,
                template_key="postgres",
                connector_name=kept_name,
                connector_id=None if connector_id is None else uuid.UUID(connector_id),
                container_name=f"dataplayer-search-test-{service_id.hex[:12]}",
                volume_name=f"dataplayer-search-test-{service_id.hex[:12]}",
                state="running",
            )
        )
        await session.commit()
    _made.append(service_id)
    return str(service_id)


async def test_a_service_is_found_by_its_connection_s_new_name_after_a_rename(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Before {marker}")
    service_id = await _service(owner, f"Before {marker}", connector_id)
    renamed = await client.patch(
        f"{CONNECTORS}/{connector_id}", headers=owner.headers, json={"name": f"After {marker}"}
    )
    assert renamed.status_code == 200, renamed.text

    by_new = await search(client, owner.headers, f"after {marker}", mode="typing")
    by_kept = await search(client, owner.headers, f"before {marker}", mode="typing")

    [found] = [hit for hit in hits(by_new, GROUP) if hit["target"]["object_id"] == service_id]
    assert found["title"] == f"After {marker}"
    assert found["open"] == "service"
    assert found["facts"]["kind"] == "postgres"
    assert service_id not in object_ids(by_kept, "service")


async def test_a_service_without_a_connection_is_found_by_the_name_it_kept(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    service_id = await _service(owner, f"Starting {marker}")

    assert service_id in object_ids(await search(client, owner.headers, marker), "service")


async def test_somebody_else_s_service_is_found_by_nobody(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    stranger = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    service_id = await _service(owner, f"Theirs {marker}")

    assert service_id in object_ids(await search(client, owner.headers, marker), "service")
    assert object_ids(await search(client, stranger.headers, marker), "service") == []


async def test_a_grant_on_its_connection_finds_nobody_else_the_service(
    client: AsyncClient, db: AsyncSession, superuser_token_headers: dict[str, str]
) -> None:
    owner = await person(client, db)
    grantee = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    connector_id = await connection(client, owner.headers, f"Managed {marker}")
    service_id = await _service(owner, f"Managed {marker}", connector_id)
    await grant(client, owner.headers, connector_id, grantee)

    assert service_id in object_ids(await search(client, owner.headers, marker), "service")
    # The grantee reads the connection; the service that runs it stays its owner's.
    for headers in (grantee.headers, superuser_token_headers):
        assert hits(await search(client, headers, marker), GROUP) == []
    assert [
        hit["target"]["connector_id"] for hit in hits(await search(client, grantee.headers, marker), "connections")
    ] == [connector_id]
