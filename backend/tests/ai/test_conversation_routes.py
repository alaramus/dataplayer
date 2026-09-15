"""Conversations and their answers, end to end through the API (D137, D141)."""

import asyncio
import time
import uuid

import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel
from sqlalchemy import text as sql
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.models import Conversation
from app.ai.topic import NAME, AgentTopic, AnswerDelta, RunChanged
from app.core.config import settings
from app.main import app
from tests.ai.conftest import (
    AI,
    KEY,
    ProviderRefusedKey,
    Script,
    Turn,
    new_conversation,
    ready_agent,
    reasoning,
    running_with,
    send,
    settled,
    text,
    user_id_of,
)
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email


@pytest.fixture
async def headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    """A person of this test's own, with a key and a model: conversations pile up."""
    person = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    await ready_agent(client, person)
    return person


async def test_an_answer_streams_is_written_down_and_names_the_conversation(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    script.turns += [
        Turn(
            pieces=[reasoning("Which tables? "), reasoning("None yet."), text("There are "), text("**no tables**.")],
            usage=(40, 9),
        ),
        Turn(pieces=[text("Tables question")]),
    ]
    conversation_id = await new_conversation(client, headers)

    run = await send(client, headers, conversation_id, "Show me the tables\nin test")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    assert (finished["input_tokens"], finished["output_tokens"]) == (40, 9)
    [step] = finished["steps"]
    assert (step["kind"], step["title"], step["status"]) == ("thinking", "Thinking", "done")
    assert step["detail"] == "Which tables? None yet."
    conversation = (await client.get(f"{AI}/conversations/{conversation_id}", headers=headers)).json()
    assert [(m["role"], m["content"]) for m in conversation["messages"]] == [
        ("user", "Show me the tables\nin test"),
        ("assistant", "There are **no tables**."),
    ]
    # The model's title arrives after the answer; before it the first line stood.
    for _ in range(100):
        conversation = (await client.get(f"{AI}/conversations/{conversation_id}", headers=headers)).json()
        if conversation["title"] == "Tables question":
            break
        await asyncio.sleep(0.02)
    assert conversation["title"] == "Tables question"
    assert script.built[0][1] == KEY


async def test_the_first_line_is_the_title_until_the_model_writes_one(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    gate = asyncio.Event()
    script.turns.append(Turn(pieces=[text("Working"), text(" on it")], gate=gate))
    conversation_id = await new_conversation(client, headers)

    run = await send(client, headers, conversation_id, "\n  Count the orders  \nplease")
    listed = (await client.get(f"{AI}/conversations", headers=headers)).json()

    assert listed["data"][0]["title"] == "Count the orders"
    assert listed["data"][0]["active"] is True
    gate.set()
    await settled(client, headers, run["id"])


async def test_a_renamed_conversation_keeps_its_name(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    gate = asyncio.Event()
    script.turns += [
        Turn(pieces=[text("Answer"), text(".")], gate=gate),
        Turn(pieces=[text("A model title")]),
    ]
    conversation_id = await new_conversation(client, headers)
    run = await send(client, headers, conversation_id, "Question")

    renamed = await client.patch(
        f"{AI}/conversations/{conversation_id}", headers=headers, json={"title": "My name"}
    )
    gate.set()
    await settled(client, headers, run["id"])
    await asyncio.sleep(0.2)

    assert renamed.status_code == 200
    conversation = (await client.get(f"{AI}/conversations/{conversation_id}", headers=headers)).json()
    assert conversation["title"] == "My name"
    assert conversation["title_is_custom"] is True


async def test_the_conversation_goes_on_from_the_models_saved_state(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    """The second answer is given the first exchange by the checkpointer (D139)."""
    script.turns += [
        Turn(pieces=[text("orders, users")]),
        Turn(pieces=[text("Title")]),
        Turn(pieces=[text("orders has 3 rows")]),
    ]
    conversation_id = await new_conversation(client, headers)
    first = await send(client, headers, conversation_id, "Which tables?")
    await settled(client, headers, first["id"])

    second = await send(client, headers, conversation_id, "How many rows in the first?")
    await settled(client, headers, second["id"])

    seen = script.calls[-1]
    assert [type(m) for m in seen if not m.type == "system"] == [HumanMessage, AIMessage, HumanMessage]
    assert seen[-1].content == "How many rows in the first?"


async def test_a_conversation_keeps_one_state_however_long_it_grows(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    """Nothing goes back to an earlier state, so only the latest is kept (D139)."""
    script.turns += [Turn(pieces=[text("one")]), Turn(pieces=[text("T")]), Turn(pieces=[text("two")])]
    conversation_id = await new_conversation(client, headers)
    for message in ("first", "second"):
        run = await send(client, headers, conversation_id, message)
        await settled(client, headers, run["id"])

    count = (
        await db.exec(  # type: ignore[call-overload]  # a raw statement, as the migration tests run
            sql("SELECT count(*) FROM checkpoints WHERE thread_id = :thread").bindparams(
                thread=conversation_id
            )
        )
    ).scalar_one()

    assert count == 1


async def test_a_second_message_waits_for_the_first_answer(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    gate = asyncio.Event()
    script.turns.append(Turn(pieces=[text("slow"), text(" answer")], gate=gate))
    conversation_id = await new_conversation(client, headers)
    run = await send(client, headers, conversation_id, "first")

    refused = await client.post(
        f"{AI}/conversations/{conversation_id}/messages", headers=headers, json={"text": "second"}
    )

    assert refused.status_code == 409
    assert refused.json()["detail"]["message"] == "This conversation is already being answered"
    gate.set()
    await settled(client, headers, run["id"])


async def test_stop_keeps_what_was_written(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    gate = asyncio.Event()
    script.turns.append(Turn(pieces=[text("Half of"), text(" the rest")], gate=gate))
    conversation_id = await new_conversation(client, headers)
    run = await send(client, headers, conversation_id, "Go")
    await running_with(client, headers, run["id"], "Half of")

    stopped = await client.post(f"{AI}/runs/{run['id']}/cancel", headers=headers)

    assert stopped.status_code == 200
    assert stopped.json()["status"] == "cancelled"
    assert stopped.json()["steps"][0]["status"] == "cancelled"
    conversation = (await client.get(f"{AI}/conversations/{conversation_id}", headers=headers)).json()
    last = conversation["messages"][-1]
    assert (last["role"], last["content"]) == ("assistant", "Half of")


async def test_a_tool_question_pauses_and_the_answer_resumes_the_same_run(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    script.turns += [
        Turn(
            tool_calls=[
                {
                    "name": "ask_user",
                    "args": {"question": "Which orders?", "choices": ["Open", "Archived"]},
                    "id": "question-1",
                    "type": "tool_call",
                }
            ]
        ),
        Turn(pieces=[text("I used Open orders.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    run = await send(client, headers, conversation_id, "Open orders")

    deadline = time.monotonic() + 10
    while True:
        paused = (await client.get(f"{AI}/runs/{run['id']}", headers=headers)).json()
        if paused["status"] == "awaiting_answer":
            break
        if time.monotonic() > deadline:
            raise AssertionError(f"run did not pause: {paused}")
        await asyncio.sleep(0.02)

    assert paused["question"] == {
        "kind": "ask_user",
        "question": "Which orders?",
        "choices": ["Open", "Archived"],
        "connector_id": None,
    }
    refused = await client.post(
        f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": "Something else"}
    )
    assert refused.status_code == 422
    continued = await client.post(
        f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": "Open"}
    )
    assert continued.status_code == 200
    finished = await settled(client, headers, run["id"])
    assert finished["status"] == "succeeded"


async def test_a_read_tool_runs_inside_the_answer_and_has_a_server_named_step(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    script.turns += [
        Turn(
            tool_calls=[
                {
                    "name": "list_connections",
                    "args": {},
                    "id": "connections-1",
                    "type": "tool_call",
                }
            ]
        ),
        Turn(pieces=[text("I listed the available connections.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await client.patch(
        f"{AI}/conversations/{conversation_id}", headers=headers, json={"title": "Connections"}
    )

    run = await send(client, headers, conversation_id, "Show my connections")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    assert [(step["title"], step["status"]) for step in finished["steps"]] == [
        ("Thinking", "done"),
        ("Listing connections", "done"),
    ]


async def test_a_provider_failure_is_a_sentence_and_nothing_of_the_providers_text(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    script.turns.append(Turn(error=ProviderRefusedKey(f"401 invalid key {KEY}")))
    conversation_id = await new_conversation(client, headers)

    run = await send(client, headers, conversation_id, "Hello")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "failed"
    assert finished["error"] == "The provider refused the key"
    assert finished["steps"][0]["status"] == "failed"
    assert KEY not in str(finished)


async def test_an_answer_that_runs_too_long_is_stopped(
    client: AsyncClient,
    headers: dict[str, str],
    script: Script,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AI_RUN_TIMEOUT_SECONDS", 0.3)
    script.turns.append(Turn(pieces=[text("never"), text(" finishes")], gate=asyncio.Event()))
    conversation_id = await new_conversation(client, headers)

    run = await send(client, headers, conversation_id, "Hello")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "failed"
    assert finished["error"].startswith("The answer took longer than")


async def test_a_message_needs_a_model_and_its_key(
    client: AsyncClient, db: AsyncSession
) -> None:
    person = await authentication_token_from_email(client=client, email=random_email(), db=db)
    conversation_id = await new_conversation(client, person)

    no_model = await client.post(
        f"{AI}/conversations/{conversation_id}/messages", headers=person, json={"text": "hi"}
    )
    await client.patch(f"{AI}/settings", headers=person, json={"model_key": "openai:gpt-5.6-luna"})
    no_key = await client.post(
        f"{AI}/conversations/{conversation_id}/messages", headers=person, json={"text": "hi"}
    )

    assert no_model.status_code == 409
    assert no_model.json()["detail"]["message"] == "Choose a model in the agent settings first"
    assert no_key.status_code == 409
    assert no_key.json()["detail"]["message"] == "Add a key for OpenAI in the agent settings first"


async def test_the_socket_hears_the_answer_as_it_is_written(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    heard: list[BaseModel] = []
    owner = await user_id_of(client, headers)

    class _Listener:
        user_id = owner

        async def deliver(self, topic: str, payload: BaseModel) -> None:
            heard.append(payload)

    topic = app.state.topics.get(NAME)
    assert isinstance(topic, AgentTopic)
    listener = _Listener()
    await topic.subscribe(listener)  # type: ignore[arg-type]  # a subscriber is a protocol
    try:
        script.turns += [Turn(pieces=[text("a"), text("b"), text("c")]), Turn(pieces=[text("T")])]
        conversation_id = await new_conversation(client, headers)
        run = await send(client, headers, conversation_id, "Spell it")
        await settled(client, headers, run["id"])
    finally:
        await topic.unsubscribe(listener)  # type: ignore[arg-type]  # as above

    statuses = [event.status for event in heard if isinstance(event, RunChanged)]
    assert statuses[0] == "running"
    assert statuses[-1] == "succeeded"
    assert "".join(event.text for event in heard if isinstance(event, AnswerDelta)) == "abc"


async def test_somebody_elses_conversation_is_not_found(
    client: AsyncClient, headers: dict[str, str], db: AsyncSession
) -> None:
    conversation_id = await new_conversation(client, headers)
    stranger = await authentication_token_from_email(client=client, email=random_email(), db=db)

    responses = [
        await client.get(f"{AI}/conversations/{conversation_id}", headers=stranger),
        await client.patch(f"{AI}/conversations/{conversation_id}", headers=stranger, json={"title": "x"}),
        await client.delete(f"{AI}/conversations/{conversation_id}", headers=stranger),
        await client.post(f"{AI}/conversations/{conversation_id}/messages", headers=stranger, json={"text": "x"}),
        await client.post(f"{AI}/runs/{uuid.uuid4()}/answer", headers=stranger, json={"answer": "x"}),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404, 404, 404]


async def test_what_is_said_is_stored_encrypted(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    marker = f"marker-{uuid.uuid4()}"
    script.turns += [Turn(pieces=[text(f"echo {marker}")]), Turn(pieces=[text("T")])]
    conversation_id = await new_conversation(client, headers)
    run = await send(client, headers, conversation_id, f"say {marker}")
    await settled(client, headers, run["id"])

    stored = await db.get(Conversation, uuid.UUID(conversation_id))
    messages = (
        await db.exec(  # type: ignore[call-overload]  # a raw statement, as the migration tests run
            sql("SELECT content FROM conversationmessage WHERE conversation_id = :id").bindparams(
                id=uuid.UUID(conversation_id)
            )
        )
    ).scalars().all()

    assert stored is not None
    assert marker.encode() not in stored.title
    assert len(messages) == 2
    assert all(marker.encode() not in content for content in messages)


async def test_deleting_a_conversation_takes_its_answers_and_state_with_it(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    gate = asyncio.Event()
    script.turns.append(Turn(pieces=[text("still"), text(" writing")], gate=gate))
    conversation_id = await new_conversation(client, headers)
    run = await send(client, headers, conversation_id, "Go")
    await running_with(client, headers, run["id"], "still")

    deleted = await client.delete(f"{AI}/conversations/{conversation_id}", headers=headers)

    assert deleted.status_code == 200
    assert (await client.get(f"{AI}/conversations/{conversation_id}", headers=headers)).status_code == 404
    assert (await client.get(f"{AI}/runs/{run['id']}", headers=headers)).status_code == 404
    left = (
        await db.exec(  # type: ignore[call-overload]  # a raw statement, as the migration tests run
            sql("SELECT count(*) FROM checkpoints WHERE thread_id = :thread").bindparams(
                thread=conversation_id
            )
        )
    ).scalar_one()
    assert left == 0


async def test_deleting_all_conversations_leaves_none(
    client: AsyncClient, headers: dict[str, str], db: AsyncSession
) -> None:
    for _ in range(2):
        await new_conversation(client, headers)

    response = await client.delete(f"{AI}/conversations", headers=headers)
    listed = (await client.get(f"{AI}/conversations", headers=headers)).json()
    rows = (
        await db.exec(  # type: ignore[call-overload]  # a raw statement, as the migration tests run
            sql("SELECT count(*) FROM conversationmessage m JOIN conversation c ON c.id = m.conversation_id WHERE c.owner_id = :owner").bindparams(
                owner=await user_id_of(client, headers)
            )
        )
    ).scalar_one()

    assert response.status_code == 200
    assert listed == {"data": [], "count": 0}
    assert rows == 0
