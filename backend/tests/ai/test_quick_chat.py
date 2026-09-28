"""Plain chat has its own history and never binds agent tools (D158)."""

import asyncio

import pytest
from httpx import AsyncClient
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai import quick_chat
from app.ai.topic import NAME, QUICK_NAME, QuickAnswerDelta
from app.main import app
from tests.ai.conftest import (
    AI,
    KEY,
    MODEL_KEY,
    Script,
    Turn,
    ready_agent,
    text,
    user_id_of,
)
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email


async def test_quick_chat_stores_a_separate_conversation_without_tools(
    client: AsyncClient, normal_user_token_headers: dict[str, str], script: Script
) -> None:
    headers = normal_user_token_headers
    await ready_agent(client, headers)
    made = await client.post(f"{AI}/quick-chats", headers=headers)
    assert made.status_code == 201
    chat_id = made.json()["id"]
    script.turns.append(Turn(pieces=[text("A plain answer")]))

    sent = await client.post(
        f"{AI}/quick-chats/{chat_id}/messages", headers=headers,
        json={"text": "Explain this", "model_key": MODEL_KEY},
    )

    assert sent.status_code == 200, sent.text
    assert [(one["role"], one["content"]) for one in sent.json()["messages"]] == [
        ("user", "Explain this"), ("assistant", "A plain answer"),
    ]
    assert sent.json()["title"] == "Explain this"
    assert script.built[-1][:2] == (MODEL_KEY, KEY)
    assert isinstance(script.calls[-1][0], SystemMessage)
    assert isinstance(script.calls[-1][-1], HumanMessage)
    script.turns.append(Turn(pieces=[text("A follow-up")]))
    follow_up = await client.post(
        f"{AI}/quick-chats/{chat_id}/messages", headers=headers,
        json={"text": "And another question"},
    )
    assert follow_up.status_code == 200
    assert [message.content for message in script.calls[-1][1:]] == [
        "Explain this", "A plain answer", "And another question",
    ]
    assert chat_id not in {
        item["id"] for item in (await client.get(f"{AI}/conversations", headers=headers)).json()["data"]
    }
    assert (await client.get(f"{AI}/quick-chats", headers=headers)).json()[0]["id"] == chat_id


async def test_the_socket_hears_a_quick_answer_as_it_is_written(
    client: AsyncClient, normal_user_token_headers: dict[str, str], script: Script
) -> None:
    headers = normal_user_token_headers
    await ready_agent(client, headers)
    chat_id = (await client.post(f"{AI}/quick-chats", headers=headers)).json()["id"]
    owner = await user_id_of(client, headers)
    heard: list[tuple[str, BaseModel]] = []

    class _Listener:
        user_id = owner

        async def deliver(self, topic: str, payload: BaseModel) -> None:
            heard.append((topic, payload))

    listener = _Listener()
    quick = app.state.topics.get(QUICK_NAME)
    agent = app.state.topics.get(NAME)
    await quick.subscribe(listener)
    await agent.subscribe(listener)
    try:
        script.turns.append(Turn(pieces=[text("a"), text("b"), text("c")]))
        sent = await client.post(
            f"{AI}/quick-chats/{chat_id}/messages", headers=headers,
            json={"text": "Spell it", "model_key": MODEL_KEY},
        )
    finally:
        await quick.unsubscribe(listener)
        await agent.unsubscribe(listener)

    assert sent.status_code == 200, sent.text
    # Its own topic: a window listening for agent runs re-reads its list of
    # conversations on every event it hears.
    assert {topic for topic, _ in heard} == {QUICK_NAME}
    deltas = [payload for _, payload in heard if isinstance(payload, QuickAnswerDelta)]
    assert {str(delta.chat_id) for delta in deltas} == {chat_id}
    assert "".join(delta.text for delta in deltas) == "abc"


async def test_quick_chat_keeps_the_question_when_the_model_fails(
    client: AsyncClient, normal_user_token_headers: dict[str, str], script: Script
) -> None:
    headers = normal_user_token_headers
    await ready_agent(client, headers)
    chat_id = (await client.post(f"{AI}/quick-chats", headers=headers)).json()["id"]
    script.turns.append(Turn(error=RuntimeError("provider unavailable")))

    sent = await client.post(
        f"{AI}/quick-chats/{chat_id}/messages", headers=headers,
        json={"text": "Keep this question", "model_key": MODEL_KEY},
    )

    assert sent.status_code >= 400
    saved = await client.get(f"{AI}/quick-chats/{chat_id}", headers=headers)
    assert saved.status_code == 200
    assert [(message["role"], message["content"]) for message in saved.json()["messages"]] == [
        ("user", "Keep this question"),
    ]


async def test_quick_chat_keeps_what_was_written_when_the_model_fails_on_the_way(
    client: AsyncClient, normal_user_token_headers: dict[str, str], script: Script
) -> None:
    headers = normal_user_token_headers
    await ready_agent(client, headers)
    chat_id = (await client.post(f"{AI}/quick-chats", headers=headers)).json()["id"]
    script.turns.append(Turn(pieces=[text("Most of "), text("an answer")], error=RuntimeError("provider unavailable")))

    sent = await client.post(
        f"{AI}/quick-chats/{chat_id}/messages", headers=headers,
        json={"text": "A long question", "model_key": MODEL_KEY},
    )

    assert sent.status_code == 502
    assert sent.json()["detail"]["message"] == "The model could not answer. The answer so far is kept."
    saved = await client.get(f"{AI}/quick-chats/{chat_id}", headers=headers)
    assert [(message["role"], message["content"]) for message in saved.json()["messages"]] == [
        ("user", "A long question"), ("assistant", "Most of an answer"),
    ]


async def test_quick_chat_gives_up_on_a_model_that_stops_writing(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = normal_user_token_headers
    await ready_agent(client, headers)
    chat_id = (await client.post(f"{AI}/quick-chats", headers=headers)).json()["id"]
    monkeypatch.setattr(quick_chat, "QUIET_SECONDS", 0.2)
    # Held after its first piece and never let go.
    script.turns.append(Turn(pieces=[text("Begun"), text(" never finished")], gate=asyncio.Event()))

    sent = await client.post(
        f"{AI}/quick-chats/{chat_id}/messages", headers=headers,
        json={"text": "A question", "model_key": MODEL_KEY},
    )

    assert sent.status_code == 502
    assert sent.json()["detail"]["message"] == "The model stopped answering. The answer so far is kept."
    saved = await client.get(f"{AI}/quick-chats/{chat_id}", headers=headers)
    assert saved.json()["messages"][-1]["content"] == "Begun"


async def test_quick_chat_is_private_and_requires_a_model_key(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    headers = normal_user_token_headers
    stranger = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    chat_id = (await client.post(f"{AI}/quick-chats", headers=headers)).json()["id"]
    assert (await client.get(f"{AI}/quick-chats/{chat_id}", headers=stranger)).status_code == 404
    assert (await client.delete(f"{AI}/quick-chats/{chat_id}", headers=stranger)).status_code == 404
    assert (await client.post(
        f"{AI}/quick-chats/{chat_id}/messages", headers=stranger, json={"text": "Hello"}
    )).status_code == 404
    assert (await client.post(
        f"{AI}/quick-chats/{chat_id}/messages", headers=headers,
        json={"text": "Hello", "model_key": "openai:missing"},
    )).status_code == 422


async def test_quick_chat_history_uses_the_same_pin_project_and_archive_actions(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    headers = normal_user_token_headers
    stranger = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    chat_id = (await client.post(f"{AI}/quick-chats", headers=headers)).json()["id"]
    project = await client.post(f"{AI}/projects", headers=headers, json={"name": "Research"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    changed = await client.patch(
        f"{AI}/quick-chats/{chat_id}", headers=headers,
        json={"pinned": True, "project_id": project_id, "title": "Notes"},
    )
    assert changed.status_code == 200, changed.text
    assert (changed.json()["title"], changed.json()["pinned"], changed.json()["project_id"]) == (
        "Notes", True, project_id,
    )
    assert (await client.patch(
        f"{AI}/quick-chats/{chat_id}", headers=stranger, json={"archived": True}
    )).status_code == 404
    assert (await client.patch(
        f"{AI}/quick-chats/{chat_id}", headers=headers,
        json={"project_id": "00000000-0000-0000-0000-000000000000"},
    )).status_code == 404

    assert (await client.patch(
        f"{AI}/quick-chats/{chat_id}", headers=headers, json={"archived": True}
    )).status_code == 200
    assert chat_id not in {
        row["id"] for row in (await client.get(f"{AI}/quick-chats", headers=headers)).json()
    }
    assert chat_id in {
        row["id"] for row in (await client.get(
            f"{AI}/quick-chats", headers=headers, params={"archived": "true"}
        )).json()
    }
    assert (await client.delete(f"{AI}/quick-chats/archived", headers=stranger)).status_code == 200
    assert (await client.get(f"{AI}/quick-chats/{chat_id}", headers=headers)).status_code == 200
    assert (await client.delete(f"{AI}/projects/{project_id}", headers=headers)).status_code == 200
    assert (await client.get(f"{AI}/quick-chats/{chat_id}", headers=headers)).json()["project_id"] is None
    assert (await client.delete(f"{AI}/quick-chats/archived", headers=headers)).status_code == 200
    assert (await client.get(f"{AI}/quick-chats/{chat_id}", headers=headers)).status_code == 404
