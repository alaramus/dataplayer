"""The model is told the account's language (D227)."""

from httpx import AsyncClient
from langchain_core.messages import BaseMessage, SystemMessage

from app.ai.prompts import LANGUAGE_NAMES, SYSTEM_PROMPT, language_line, system_prompt
from app.ai.quick_chat import PROMPT
from app.core.translation import LANGUAGES
from tests.ai.conftest import (
    AI,
    MODEL_KEY,
    Script,
    Turn,
    new_conversation,
    ready_agent,
    send,
    settled,
    text,
)

RUSSIAN_LINE = "The person's interface is in Russian. Answer in Russian unless they write in another language."


def _system(call: list[BaseMessage]) -> str:
    first = call[0]
    assert isinstance(first, SystemMessage)
    assert isinstance(first.content, str)
    return first.content


def test_every_language_has_a_name_the_model_reads() -> None:
    assert set(LANGUAGE_NAMES) == set(LANGUAGES)
    assert language_line("en") == ""
    assert system_prompt("en") == SYSTEM_PROMPT
    assert language_line("ru") == RUSSIAN_LINE


async def test_an_agent_run_started_in_russian_tells_the_model(
    client: AsyncClient, normal_user_token_headers: dict[str, str], script: Script
) -> None:
    headers = normal_user_token_headers
    await ready_agent(client, headers)
    conversation_id = await new_conversation(client, headers)
    script.turns.append(Turn(pieces=[text("Ответ")]))

    run = await send(
        client, {**headers, "Accept-Language": "ru"}, conversation_id, "Привет"
    )
    assert (await settled(client, headers, run["id"]))["status"] == "succeeded"

    prompt = _system(script.calls[0])
    assert prompt.startswith(SYSTEM_PROMPT)
    assert RUSSIAN_LINE in prompt


async def test_an_agent_run_started_in_english_has_the_prompt_as_written(
    client: AsyncClient, normal_user_token_headers: dict[str, str], script: Script
) -> None:
    headers = normal_user_token_headers
    await ready_agent(client, headers)
    conversation_id = await new_conversation(client, headers)
    script.turns.append(Turn(pieces=[text("An answer")]))

    run = await send(client, headers, conversation_id, "Hello")
    assert (await settled(client, headers, run["id"]))["status"] == "succeeded"

    assert _system(script.calls[0]) == SYSTEM_PROMPT


async def test_a_quick_chat_in_russian_tells_the_model(
    client: AsyncClient, normal_user_token_headers: dict[str, str], script: Script
) -> None:
    headers = {**normal_user_token_headers, "Accept-Language": "ru"}
    await ready_agent(client, headers)
    chat_id = (await client.post(f"{AI}/quick-chats", headers=headers)).json()["id"]
    script.turns.append(Turn(pieces=[text("Ответ")]))

    sent = await client.post(
        f"{AI}/quick-chats/{chat_id}/messages",
        headers=headers,
        json={"text": "Привет", "model_key": MODEL_KEY},
    )

    assert sent.status_code == 200, sent.text
    assert _system(script.calls[-1]) == f"{PROMPT} {RUSSIAN_LINE}"


async def test_the_browser_is_told_the_language_too(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = {**normal_user_token_headers, "Accept-Language": "ru"}
    chat_id = (await client.post(f"{AI}/quick-chats", headers=headers)).json()["id"]

    turn = await client.post(
        f"{AI}/quick-chats/{chat_id}/browser-turns",
        headers=headers,
        json={"text": "Привет"},
    )

    assert turn.status_code == 200, turn.text
    assert turn.json()["prompt"] == f"{PROMPT} {RUSSIAN_LINE}"
