"""Chats found by the search: by title, never by what was said (S5, D141, D204)."""

import uuid

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai import conversations
from app.ai.content import sealed
from app.ai.quick_chat import QuickConversation
from app.core.db import async_session_maker
from tests.utils.search import Person, hits, object_ids, person, search

GROUP = "objects:conversations"


async def _conversation(owner: Person, title: str, said: str = "", *, archived: bool = False) -> str:
    async with async_session_maker() as session:
        made = await conversations.create(session, owner.id, title)
        if said:
            await conversations.add_message(session, made.id, "user", said, None)
        if archived:
            made.archived = True
            session.add(made)
            await session.commit()
        return str(made.id)


async def _quick_chat(owner: Person, title: str) -> str:
    async with async_session_maker() as session:
        chat = QuickConversation(owner_id=owner.id, title=sealed(title))
        session.add(chat)
        await session.commit()
        return str(chat.id)


async def _project(owner: Person, name: str) -> str:
    async with async_session_maker() as session:
        return str((await conversations.create_project(session, owner.id, name)).id)


async def test_each_kind_of_chat_is_found_by_its_title(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    conversation_id = await _conversation(owner, f"Revenue {marker} questions")
    quick_id = await _quick_chat(owner, f"Quick {marker} idea")
    project_id = await _project(owner, f"Planning {marker}")

    lines = await search(client, owner.headers, marker, mode="typing")

    found = {hit["target"]["object_type"]: hit for hit in hits(lines, GROUP)}
    assert found["conversation"]["target"]["object_id"] == conversation_id
    assert found["conversation"]["title"] == f"Revenue {marker} questions"
    assert found["conversation"]["open"] == "conversation"
    assert found["quick_chat"]["target"]["object_id"] == quick_id
    assert found["quick_chat"]["open"] == "quick_chat"
    assert found["project"]["target"]["object_id"] == project_id
    assert found["project"]["open"] == "project"


async def test_a_conversation_is_never_found_by_what_was_said_in_it(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    await _conversation(owner, "Plain title", said=f"the secret word is {marker}")

    lines = await search(client, owner.headers, marker)

    assert hits(lines, GROUP) == []


async def test_an_archived_chat_is_out_of_the_search(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    await _conversation(owner, f"Old {marker}", archived=True)

    assert object_ids(await search(client, owner.headers, marker), "conversation") == []


async def test_somebody_else_s_conversation_is_found_by_nobody(
    client: AsyncClient, db: AsyncSession, superuser_token_headers: dict[str, str]
) -> None:
    owner = await person(client, db)
    stranger = await person(client, db)
    marker = uuid.uuid4().hex[:8]
    conversation_id = await _conversation(owner, f"Private {marker}")

    assert conversation_id in object_ids(await search(client, owner.headers, marker), "conversation")
    assert hits(await search(client, stranger.headers, marker), GROUP) == []
    assert hits(await search(client, superuser_token_headers, marker), GROUP) == []


async def test_a_quick_chat_is_found_by_the_title_its_history_shows(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    # Untitled quick chats were once stored under this name.
    quick_id = await _quick_chat(owner, "New quick chat")
    recent = [{"kind": "object", "object_type": "quick_chat", "object_id": quick_id}]

    by_shown = await search(client, owner.headers, "new chat", mode="typing")
    by_stored = await search(client, owner.headers, "new quick", mode="typing")
    named_again = await search(client, owner.headers, "", recent=recent)

    [found] = hits(by_shown, GROUP)
    assert found["target"]["object_id"] == quick_id
    assert found["title"] == "New chat"
    assert found["match"]["match_class"] == "exact"
    assert hits(by_stored, GROUP) == []
    [again] = hits(named_again)
    assert again["title"] == "New chat"
