"""Every kind of object at once: each found, each named again for its owner
only, and the words in no log line (S5, S6, D199, D200)."""

import logging
import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlmodel import col, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai import conversations
from app.ai.content import sealed
from app.ai.quick_chat import QuickConversation
from app.core.config import settings
from app.core.db import async_session_maker
from app.metrics.dashboards import Dashboard
from app.pipelines.models import Pipeline
from app.queries import crud as queries
from app.queries.models import EditorLayout
from app.services.models import ManagedService
from app.users.models import User
from tests.utils.search import Person, connection, hits, person, search

API = settings.API_V1_STR


@pytest.fixture
async def made() -> AsyncGenerator[list[uuid.UUID]]:
    """The owners whose pipelines, dashboards and services go with the test."""
    owners: list[uuid.UUID] = []
    yield owners
    async with async_session_maker() as session:
        for table in (Pipeline, Dashboard, ManagedService):
            await session.exec(delete(table).where(col(table.owner_id).in_(owners)))
        await session.commit()


async def _one_of_each(
    client: AsyncClient, owner: Person, marker: str
) -> list[tuple[str, str]]:
    """One object of every kind the person owns, each holding the marker: the
    object type and id of each, newest first."""
    made: list[tuple[str, str]] = []
    connector_id = await connection(client, owner.headers, f"Zoo {marker}")
    for object_type, path, body in (
        ("pipeline", f"{API}/pipelines", {"name": f"Pipeline {marker}"}),
        ("dashboard", f"{API}/metrics/dashboards", {"name": f"Dashboard {marker}"}),
        ("ssh_key", f"{API}/ssh-keys/generate", {"name": f"Key {marker}"}),
    ):
        response = await client.post(path, headers=owner.headers, json=body)
        assert response.status_code == 200, response.text
        made.append((object_type, str(response.json()["id"])))
    async with async_session_maker() as session:
        user = await session.get(User, owner.id)
        assert user is not None
        for title, text in ((f"Query {marker}", "select 1"), (None, f"select '{marker}'")):
            document = await queries.create(
                session,
                owner=user,
                connector_id=uuid.UUID(connector_id),
                title=title,
                body=text,
                search_path=[],
                layout=EditorLayout(),
            )
            made.append(("saved_query", str(document.id)))
        chat = await conversations.create(session, owner.id, f"Chat {marker}")
        await conversations.add_message(session, chat.id, "user", f"say {marker}", None)
        made.append(("conversation", str(chat.id)))
        project = await conversations.create_project(session, owner.id, f"Project {marker}")
        made.append(("project", str(project.id)))
        quick = QuickConversation(owner_id=owner.id, title=sealed(f"Quick {marker}"))
        service = ManagedService(
            owner_id=owner.id,
            template_key="postgres",
            connector_name=f"Service {marker}",
            container_name=f"dataplayer-search-test-{marker}",
            volume_name=f"dataplayer-search-test-{marker}",
        )
        session.add(quick)
        session.add(service)
        await session.commit()
        made.append(("quick_chat", str(quick.id)))
        made.append(("service", str(service.id)))
    return made[::-1]


async def test_every_kind_is_found_and_the_words_reach_no_log_line(
    client: AsyncClient,
    db: AsyncSession,
    made: list[uuid.UUID],
    caplog: pytest.LogCaptureFixture,
    superuser_token_headers: dict[str, str],
) -> None:
    owner = await person(client, db)
    stranger = await person(client, db)
    made.append(owner.id)
    marker = f"wombat{uuid.uuid4().hex[:8]}"
    await _one_of_each(client, owner, marker)
    caplog.set_level(logging.DEBUG)

    lines = await search(
        client,
        owner.headers,
        marker,
        browser=[{"object_type": "tab", "object_id": "panel-1", "title": f"Tab {marker}"}],
    )

    found = {hit["target"].get("object_type", hit["target"]["kind"]) for hit in hits(lines)}
    assert found >= {
        "connection",
        "tab",
        "saved_query",
        "pipeline",
        "dashboard",
        "conversation",
        "quick_chat",
        "project",
        "service",
        "ssh_key",
    }
    # Two saved queries: one by its title, one by a word in its body.
    assert len(hits(lines, "objects:saved_queries")) == 2
    # Nothing of it is anybody else's to find, a superuser's included (D34).
    for headers in (stranger.headers, superuser_token_headers):
        assert hits(await search(client, headers, marker)) == []
    assert not [one for one in caplog.records if marker in one.getMessage()]


async def test_what_was_opened_is_named_again_for_its_owner_and_nobody_else(
    client: AsyncClient,
    db: AsyncSession,
    made: list[uuid.UUID],
    superuser_token_headers: dict[str, str],
) -> None:
    owner = await person(client, db)
    stranger = await person(client, db)
    made.append(owner.id)
    opened = await _one_of_each(client, owner, f"wombat{uuid.uuid4().hex[:8]}")
    recent = [
        {"kind": "object", "object_type": object_type, "object_id": object_id}
        for object_type, object_id in opened
    ]

    mine = await search(client, owner.headers, "", recent=recent)

    assert [hit["key"] for hit in hits(mine)] == [
        f"object:{object_type}:{object_id}" for object_type, object_id in opened
    ]
    for hit in hits(mine):
        assert hit["open"] == hit["target"]["object_type"]
        assert hit["title"]
    for headers in (stranger.headers, superuser_token_headers):
        assert hits(await search(client, headers, "", recent=recent)) == []
