"""A quick chat answered by the browser's own model (D223)."""

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai import quick_chat
from tests.ai.conftest import AI
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email


async def test_the_browser_is_given_the_history_and_its_answer_is_kept(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    chat_id = (await client.post(f"{AI}/quick-chats", headers=headers)).json()["id"]
    before = (await client.get(f"{AI}/settings", headers=headers)).json()["model_key"]

    # No provider key is needed: the server calls no model.
    turn = await client.post(
        f"{AI}/quick-chats/{chat_id}/browser-turns", headers=headers,
        json={"text": "First question"},
    )
    assert turn.status_code == 200, turn.text
    assert turn.json()["prompt"] == quick_chat.PROMPT
    assert turn.json()["history"] == []
    assert turn.json()["chat"]["title"] == "First question"
    assert turn.json()["chat"]["model_key"] == quick_chat.BROWSER_MODEL_KEY
    assert [one["role"] for one in turn.json()["chat"]["messages"]] == ["user"]

    kept = await client.post(
        f"{AI}/quick-chats/{chat_id}/browser-answers", headers=headers,
        json={"text": "First answer"},
    )
    assert kept.status_code == 200, kept.text
    assert [(one["role"], one["content"]) for one in kept.json()["messages"]] == [
        ("user", "First question"), ("assistant", "First answer"),
    ]

    second = await client.post(
        f"{AI}/quick-chats/{chat_id}/browser-turns", headers=headers,
        json={"text": "Second question"},
    )
    assert second.json()["history"] == [
        {"role": "user", "content": "First question"},
        {"role": "assistant", "content": "First answer"},
    ]
    assert second.json()["chat"]["title"] == "First question"
    # The settings name a model the server can call; this one is not remembered.
    assert (await client.get(f"{AI}/settings", headers=headers)).json()["model_key"] == before


async def test_an_answer_needs_a_question_waiting_for_it(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers
    chat_id = (await client.post(f"{AI}/quick-chats", headers=headers)).json()["id"]
    answers = f"{AI}/quick-chats/{chat_id}/browser-answers"

    assert (await client.post(answers, headers=headers, json={"text": "Unasked"})).status_code == 409

    await client.post(
        f"{AI}/quick-chats/{chat_id}/browser-turns", headers=headers, json={"text": "Asked"}
    )
    assert (await client.post(answers, headers=headers, json={"text": "Once"})).status_code == 200
    assert (await client.post(answers, headers=headers, json={"text": "Twice"})).status_code == 409


async def test_a_browser_turn_is_one_persons_own(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    chat_id = (
        await client.post(f"{AI}/quick-chats", headers=normal_user_token_headers)
    ).json()["id"]
    other = await authentication_token_from_email(client=client, email=random_email(), db=db)

    asked = await client.post(
        f"{AI}/quick-chats/{chat_id}/browser-turns", headers=other, json={"text": "Mine?"}
    )
    answered = await client.post(
        f"{AI}/quick-chats/{chat_id}/browser-answers", headers=other, json={"text": "No"}
    )

    assert asked.status_code == 404
    assert answered.status_code == 404
