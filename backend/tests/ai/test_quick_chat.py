"""Plain chat has its own history and never binds agent tools (D158)."""

from httpx import AsyncClient
from langchain_core.messages import HumanMessage, SystemMessage
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.ai.conftest import AI, KEY, MODEL_KEY, Script, Turn, ready_agent, text
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
