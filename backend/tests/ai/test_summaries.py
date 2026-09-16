"""A conversation that nears the model's window is summarised, not truncated (D139, AI6).

The scripted model plays both roles — answering and summarising — so the
acceptance is read from what each call was given: the summary call receives the
older turns, the answering call receives the summary in their place, and the
transcript a person reads is never rewritten.
"""

import uuid

import pytest
from httpx import AsyncClient
from langchain_core.messages import HumanMessage
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from tests.ai.conftest import (
    AI,
    Script,
    Turn,
    new_conversation,
    ready_agent,
    send,
    settled,
    text,
)
from tests.ai.test_reading import rename
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

SUMMARY_MARKER = "Here is a summary of the conversation to date"


@pytest.fixture
async def headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    person = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    await ready_agent(client, person)
    return person


def summaries(messages: list[object]) -> list[str]:
    """The summary messages one model call was given, as their text."""
    return [
        str(message.content)
        for message in messages
        if isinstance(message, HumanMessage)
        and str(message.content).startswith(SUMMARY_MARKER)
    ]


async def test_a_conversation_past_the_window_is_summarised_and_keeps_its_facts(
    client: AsyncClient,
    headers: dict[str, str],
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A window of one token, so the second message is already past it.
    monkeypatch.setattr(settings, "AI_SUMMARY_TRIGGER_FRACTION", 0.000001)
    monkeypatch.setattr(settings, "AI_SUMMARY_KEEP_MESSAGES", 2)
    fact = f"the code word is {uuid.uuid4()}"
    first = f"remember this: {fact}"
    script.turns += [
        Turn(pieces=[text("Noted.")]),
        Turn(pieces=[text(f"The person asked to remember: {fact}.")]),
        Turn(pieces=[text(f"As noted, {fact}.")]),
        Turn(pieces=[text(f"Still remembered: {fact}.")]),
        Turn(pieces=[text(f"Still {fact}.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, first)
    finished = await settled(client, headers, run["id"])
    assert finished["status"] == "succeeded"

    second = await send(client, headers, conversation_id, "what was the code word?")
    finished = await settled(client, headers, second["id"])
    assert finished["status"] == "succeeded"

    # The summary call was given the older turns, the fact among them.
    assert any(fact in str(message.content) for message in script.calls[1])
    # The answering call was given the summary in their place.
    [summary] = summaries(script.calls[2])
    assert fact in summary
    assert all(str(message.content) != first for message in script.calls[2])

    third = await send(client, headers, conversation_id, "and what is it now?")
    finished = await settled(client, headers, third["id"])
    assert finished["status"] == "succeeded"

    # The working state kept the summary: the next answer starts from it.
    [summary] = summaries(script.calls[4])
    assert fact in summary

    # The transcript a person reads is untouched: every turn as it was written.
    conversation = await client.get(f"{AI}/conversations/{conversation_id}", headers=headers)
    messages = conversation.json()["messages"]
    assert [message["role"] for message in messages] == [
        "user", "assistant", "user", "assistant", "user", "assistant",
    ]
    assert messages[0]["content"] == first


async def test_a_short_conversation_is_not_summarised(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    first = f"remember this: {uuid.uuid4()}"
    script.turns += [
        Turn(pieces=[text("Noted.")]),
        Turn(pieces=[text("As noted.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, first)
    await settled(client, headers, run["id"])
    second = await send(client, headers, conversation_id, "repeat it")
    finished = await settled(client, headers, second["id"])

    assert finished["status"] == "succeeded"
    # Two answers, two model calls: nothing was spent on a summary.
    assert len(script.calls) == 2
    assert summaries(script.calls[1]) == []
    assert any(str(message.content) == first for message in script.calls[1])
