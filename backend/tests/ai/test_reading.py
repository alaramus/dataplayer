"""The agent reading through real connections, end to end (D133, D134, D135).

Every test scripts the model and lets the tools run against a PostgreSQL
connection of the test's own, so the acceptance of AI4 is read from what the
model was actually given and from the steps the server wrote.
"""

import asyncio
import json
import time
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from langchain_core.messages import ToolMessage
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.prompts import SYSTEM_PROMPT
from app.ai.tools import LIMIT_MESSAGE, WITHHELD_RESULT
from app.ai.topic import NAME, AgentTopic, WorkspaceOpened
from app.core.config import settings
from app.main import app
from tests.ai.conftest import (
    AI,
    Script,
    Turn,
    new_conversation,
    ready_agent,
    send,
    settled,
    text,
    user_id_of,
)
from tests.utils.database import working_postgres_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

CONNECTORS = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    person = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    await ready_agent(client, person)
    return person


async def postgres_connector(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    transfer: bool,
    name: str | None = None,
) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": name or f"agent reads {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
            "allow_third_party_transfer": transfer,
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def rename(client: AsyncClient, headers: dict[str, str], conversation_id: str) -> None:
    """A custom title, so the run does not spend a scripted turn on writing one."""
    response = await client.patch(
        f"{AI}/conversations/{conversation_id}", headers=headers, json={"title": "AI4 chat"}
    )
    assert response.status_code == 200, response.text


def call(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def tool_results(script: Script, call_index: int) -> list[dict[str, Any]]:
    """What the model was given by tools before one of its calls, decoded."""
    return [
        json.loads(message.content)
        for message in script.calls[call_index]
        if isinstance(message, ToolMessage) and isinstance(message.content, str)
    ]


async def paused(
    client: AsyncClient, headers: dict[str, str], run_id: str, *, seconds: float = 10.0
) -> dict[str, Any]:
    deadline = time.monotonic() + seconds
    while True:
        body = (await client.get(f"{AI}/runs/{run_id}", headers=headers)).json()
        if body["status"] == "awaiting_answer":
            return dict(body)
        if time.monotonic() > deadline:
            raise AssertionError(f"run {run_id} did not pause: {body}")
        await asyncio.sleep(0.02)


async def test_the_agent_lists_the_tables_of_a_named_connection(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True, name="shop")
    script.turns += [
        Turn(tool_calls=[call("list_connections", {}, "c1")]),
        Turn(tool_calls=[call("browse_catalog", {"connector_id": connector_id}, "c2")]),
        Turn(tool_calls=[call("browse_catalog", {"connector_id": connector_id, "node_id": "public"}, "c3")]),
        Turn(pieces=[text("shop holds these tables.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "show the tables in shop")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    assert [(step["title"], step["status"]) for step in finished["steps"]] == [
        ("Thinking", "done"),
        ("Listing connections", "done"),
        ('Browsing catalog in "shop"', "done"),
        ('Browsing catalog in "shop"', "done"),
    ]
    listed = tool_results(script, 1)[-1]
    assert listed["connections"][0]["id"] == connector_id
    assert listed["connections"][0]["third_party_transfer"] == "allowed"
    root = tool_results(script, 2)[-1]
    assert any(node["id"] == "public" for node in root["nodes"])
    relations = tool_results(script, 3)[-1]
    assert any(node["id"].startswith("public.") for node in relations["nodes"])


async def test_two_connections_with_one_name_become_a_question_not_a_guess(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    name = f"warehouse {uuid.uuid4()}"
    first_id = await postgres_connector(client, headers, transfer=True, name=name)
    await postgres_connector(client, headers, transfer=True, name=name)
    script.turns += [
        Turn(tool_calls=[call("list_connections", {}, "c1")]),
        Turn(
            tool_calls=[
                call(
                    "ask_user",
                    {
                        "question": f'Which "{name}"?',
                        "choices": [f"The first ({first_id})", "The second one"],
                    },
                    "c2",
                )
            ]
        ),
        Turn(tool_calls=[call("browse_catalog", {"connector_id": first_id}, "c3")]),
        Turn(pieces=[text("I read the first one.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, f"show the schemas in {name}")
    waiting = await paused(client, headers, run["id"])

    assert waiting["question"]["kind"] == "ask_user"
    assert waiting["question"]["choices"] == [f"The first ({first_id})", "The second one"]
    continued = await client.post(
        f"{AI}/runs/{run['id']}/answer",
        headers=headers,
        json={"answer": f"The first ({first_id})"},
    )
    assert continued.status_code == 200, continued.text
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    catalog = tool_results(script, 3)[-1]
    assert catalog["connector_id"] == first_id


def test_the_prompt_orders_a_question_over_a_guess() -> None:
    assert "ask which one rather than guessing" in SYSTEM_PROMPT


async def test_open_in_workspace_opens_the_panel(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    owner = await user_id_of(client, headers)
    heard: list[BaseModel] = []

    class _Listener:
        user_id = owner

        async def deliver(self, topic: str, payload: BaseModel) -> None:
            heard.append(payload)

    topic = app.state.topics.get(NAME)
    assert isinstance(topic, AgentTopic)
    listener = _Listener()
    await topic.subscribe(listener)  # type: ignore[arg-type]  # a subscriber is a protocol
    try:
        script.turns += [
            Turn(
                tool_calls=[
                    call(
                        "open_in_workspace",
                        {
                            "connector_id": connector_id,
                            "node_id": "pg_catalog.pg_class",
                            "view": "rows",
                        },
                        "c1",
                    )
                ]
            ),
            Turn(pieces=[text("Opened it.")]),
        ]
        conversation_id = await new_conversation(client, headers)
        await rename(client, headers, conversation_id)
        run = await send(client, headers, conversation_id, "open pg_class")
        finished = await settled(client, headers, run["id"])
    finally:
        await topic.unsubscribe(listener)  # type: ignore[arg-type]  # as above

    assert finished["status"] == "succeeded"
    opened = [event for event in heard if isinstance(event, WorkspaceOpened)]
    assert len(opened) == 1
    intent = opened[0].intent
    assert intent.connector_id == uuid.UUID(connector_id)
    assert intent.node_id == "pg_catalog.pg_class"
    assert intent.view == "rows"
    assert intent.representations
    assert 'Opening "pg_catalog.pg_class"' in [step["title"] for step in finished["steps"]]
    [result] = tool_results(script, 1)
    assert result["opened"] is True


async def test_a_grantee_cannot_read_a_connection_whose_flag_is_off(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    owner_headers = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    connector_id = await postgres_connector(client, owner_headers, transfer=False)
    grantee_id = await user_id_of(client, headers)
    granted = await client.put(
        f"{CONNECTORS}/{connector_id}/grants",
        headers=owner_headers,
        json={"user_id": str(grantee_id), "access": "read"},
    )
    assert granted.status_code == 200, granted.text
    script.turns += [
        Turn(tool_calls=[call("browse_catalog", {"connector_id": connector_id}, "c1")]),
        Turn(pieces=[text("The owner has not allowed this.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "show the schemas")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    [refusal] = tool_results(script, 1)
    assert refusal["error"] == "transfer_not_allowed"
    assert refusal["message"] == "Ask the connection owner to allow third-party transfer."
    assert "nodes" not in refusal


async def test_the_owner_allows_transfer_from_the_refused_step(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    name = f"ledger {uuid.uuid4()}"
    connector_id = await postgres_connector(client, headers, transfer=False, name=name)
    script.turns += [
        Turn(tool_calls=[call("browse_catalog", {"connector_id": connector_id}, "c1")]),
        Turn(pieces=[text("Thank you, I read it now.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "show the schemas")
    waiting = await paused(client, headers, run["id"])

    assert waiting["question"] == {
        "kind": "allow_transfer",
        "question": f'Allow third-party transfer for "{name}" so the agent can read it?',
        "choices": ["Allow", "Not now"],
        "connector_id": connector_id,
    }
    continued = await client.post(
        f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": "Allow"}
    )
    assert continued.status_code == 200, continued.text
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    connector = (await client.get(f"{CONNECTORS}/{connector_id}", headers=headers)).json()
    assert connector["allow_third_party_transfer"] is True
    [catalog] = tool_results(script, 1)
    assert any(node["id"] == "public" for node in catalog["nodes"])


async def test_the_owner_may_refuse_and_the_agent_says_why(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=False)
    script.turns += [
        Turn(tool_calls=[call("browse_catalog", {"connector_id": connector_id}, "c1")]),
        Turn(pieces=[text("You did not allow it, so nothing was read.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "show the schemas")
    await paused(client, headers, run["id"])
    continued = await client.post(
        f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": "Not now"}
    )
    assert continued.status_code == 200, continued.text
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    connector = (await client.get(f"{CONNECTORS}/{connector_id}", headers=headers)).json()
    assert connector["allow_third_party_transfer"] is False
    [refusal] = tool_results(script, 1)
    assert refusal["error"] == "transfer_not_allowed"
    assert "Allow third-party transfer on this connection" in refusal["message"]


async def test_switching_the_flag_off_withholds_earlier_results(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    script.turns += [
        Turn(tool_calls=[call("browse_catalog", {"connector_id": connector_id}, "c1")]),
        Turn(pieces=[text("Here are the schemas.")]),
        Turn(pieces=[text("I no longer have them.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)
    run = await send(client, headers, conversation_id, "show the schemas")
    await settled(client, headers, run["id"])

    withdrawn = await client.patch(
        f"{CONNECTORS}/{connector_id}",
        headers=headers,
        json={"allow_third_party_transfer": False},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    second = await send(client, headers, conversation_id, "list them again")
    finished = await settled(client, headers, second["id"])

    assert finished["status"] == "succeeded"
    [intact] = tool_results(script, 1)
    assert "nodes" in intact
    withheld = [
        message.content
        for message in script.calls[2]
        if isinstance(message, ToolMessage)
    ]
    assert withheld == [WITHHELD_RESULT]


async def test_the_tool_call_limit_stops_the_run_with_its_sentence(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    script.turns += [
        Turn(tool_calls=[call("list_connections", {}, f"c{number}")])
        for number in range(51)
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "list, then list again, forever")
    finished = await settled(client, headers, run["id"], seconds=30.0)

    assert finished["status"] == "failed"
    assert finished["error"] == LIMIT_MESSAGE
    tool_steps = [step for step in finished["steps"] if step["kind"] == "tool"]
    assert len(tool_steps) == 50


async def test_a_connection_the_person_has_no_grant_for_is_not_read(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    owner_headers = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    connector_id = await postgres_connector(client, owner_headers, transfer=True)
    script.turns += [
        Turn(tool_calls=[call("browse_catalog", {"connector_id": connector_id}, "c1")]),
        Turn(pieces=[text("I cannot see that connection.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "show the schemas")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    [refusal] = tool_results(script, 1)
    assert refusal == {"error": "Connector not found"}
    failed = [step for step in finished["steps"] if step["kind"] == "tool"]
    assert [step["status"] for step in failed] == ["failed"]


async def test_read_rows_returns_at_most_twenty_rows_and_says_there_is_more(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    script.turns += [
        Turn(
            tool_calls=[
                call(
                    "read_rows",
                    {"connector_id": connector_id, "node_id": "pg_catalog.pg_class"},
                    "c1",
                )
            ]
        ),
        Turn(pieces=[text("The first twenty rows.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "read pg_class")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    [page] = tool_results(script, 1)
    assert page["returned_rows"] == 20
    assert len(page["rows"]) == 20
    assert page["has_more"] is True
    assert 'Reading rows from "pg_catalog.pg_class"' in [
        step["title"] for step in finished["steps"]
    ]


async def test_a_query_reads_and_each_statement_is_a_substep(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    script.turns += [
        Turn(
            tool_calls=[
                call("run_query", {"connector_id": connector_id, "sql": "SELECT 1 AS one"}, "c1")
            ]
        ),
        Turn(pieces=[text("One row.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "run SELECT 1")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    [result] = tool_results(script, 1)
    assert result["statements"][0]["status"] == "succeeded"
    query_step = next(step for step in finished["steps"] if step["kind"] == "tool")
    assert query_step["status"] == "done"
    assert query_step["substeps"] == ["Statement 1 · succeeded · 1 rows"]


async def test_a_changing_query_is_refused_with_the_read_sentence(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    script.turns += [
        Turn(
            tool_calls=[
                call(
                    "run_query",
                    {"connector_id": connector_id, "sql": "DELETE FROM pg_catalog.pg_class"},
                    "c1",
                )
            ]
        ),
        Turn(pieces=[text("I cannot change data yet.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "delete everything")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    [refusal] = tool_results(script, 1)
    assert refusal["error"] == "Statement 1 is a dml statement, and this run is a read"
    query_step = next(step for step in finished["steps"] if step["kind"] == "tool")
    assert query_step["status"] == "failed"


async def test_describing_a_node_gives_its_model(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    script.turns += [
        Turn(
            tool_calls=[
                call(
                    "describe_node",
                    {"connector_id": connector_id, "node_id": "pg_catalog.pg_class"},
                    "c1",
                )
            ]
        ),
        Turn(pieces=[text("It has these columns.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "describe pg_class")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    [description] = tool_results(script, 1)
    assert "relation" in description
    assert any(column["name"] == "relname" for column in description["relation"]["columns"])
    assert 'Describing "pg_catalog.pg_class"' in [
        step["title"] for step in finished["steps"]
    ]
