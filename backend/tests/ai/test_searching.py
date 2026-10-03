"""The agent's `search` tool, through a scripted model and real connections (S10).

The model is scripted; the tool runs against PostgreSQL connections of the
test's own, so what is asserted is what the model was actually given.
"""

import json
from typing import Any

import pytest
from httpx import AsyncClient
from langchain_core.messages import ToolMessage
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.search_tool import NOTHING_INSIDE
from app.ai.tools import TRANSFER_MARKER, WITHHELD_RESULT
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
from tests.ai.test_reading import (
    CONNECTORS,
    call,
    postgres_connector,
    rename,
    tool_results,
)
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

TABLE = "pg_catalog.pg_class"


@pytest.fixture
async def headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    person = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    await ready_agent(client, person)
    return person


def tables_of(result: dict[str, Any]) -> set[str]:
    """The connections a table named pg_class was found in."""
    return {
        hit["connector_id"]
        for hit in result["hits"]
        if hit["kind"] == "node" and hit["node_id"] == TABLE
    }


async def test_the_agent_finds_a_table_across_the_connections_it_may_use(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    shop = await postgres_connector(client, headers, transfer=True, name="search shop")
    stock = await postgres_connector(client, headers, transfer=True, name="search stock")
    closed = await postgres_connector(client, headers, transfer=False, name="search closed")
    script.turns += [
        Turn(tool_calls=[call("search", {"words": "pg_class", "connector_ids": [shop, stock, closed]}, "c1")]),
        Turn(pieces=[text("pg_class is in both.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "where is pg_class?")
    finished = await settled(client, headers, run["id"], seconds=30.0)

    assert finished["status"] == "succeeded"
    [result] = tool_results(script, 1)
    assert tables_of(result) == {shop, stock}
    assert sorted(result["searched_inside"]) == ["search shop", "search stock"]
    # The closed connection is named in a refusal, and nothing else of it is there.
    [refused] = result["refused"]
    assert refused["error"] == TRANSFER_MARKER
    assert refused["connector_id"] == closed
    assert refused["connector"] == "search closed"
    assert closed not in result["connector_ids"]
    assert all(hit.get("connector_id") != closed for hit in result["hits"])
    assert "search closed" not in json.dumps(result["hits"])
    [step] = [step for step in finished["steps"] if step["kind"] == "tool"]
    assert step["title"] == 'Searching for "pg_class"'


async def test_the_connection_of_an_attached_tab_is_searched_unnamed(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    attached = await postgres_connector(client, headers, transfer=True)
    other = await postgres_connector(client, headers, transfer=True)
    script.turns += [
        Turn(tool_calls=[call("search", {"words": "pg_class"}, "c1")]),
        Turn(pieces=[text("Found it.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    response = await client.post(
        f"{AI}/conversations/{conversation_id}/messages",
        headers=headers,
        data={
            "text": "find pg_class here",
            "contexts": json.dumps([
                {
                    "panel_id": "catalog-1",
                    "label": "Catalog",
                    "kind": "catalog",
                    "connector_id": attached,
                }
            ]),
        },
    )
    assert response.status_code == 202, response.text
    await settled(client, headers, response.json()["id"], seconds=30.0)

    [result] = tool_results(script, 1)
    assert tables_of(result) == {attached}
    assert other not in tables_of(result)
    assert "note" not in result


async def test_nothing_inside_is_asked_unless_attached_or_named(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    name = f"search lone {random_email()}"
    connector_id = await postgres_connector(client, headers, transfer=True, name=name)
    script.turns += [
        Turn(tool_calls=[call("search", {"words": "search lone"}, "c1")]),
        Turn(pieces=[text("Only its name.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "find it")
    await settled(client, headers, run["id"], seconds=30.0)

    [result] = tool_results(script, 1)
    assert result["note"] == NOTHING_INSIDE
    assert result["searched_inside"] == []
    assert [hit["kind"] for hit in result["hits"] if hit.get("connector_id") == connector_id] == [
        "connection"
    ]


async def test_a_short_search_is_refused_with_a_sentence(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    script.turns += [
        Turn(tool_calls=[call("search", {"words": "x"}, "c1")]),
        Turn(pieces=[text("Too short.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "find x")
    await settled(client, headers, run["id"])

    [result] = tool_results(script, 1)
    assert result == {"error": "A search needs at least 2 characters"}


async def test_switching_transfer_off_withholds_an_earlier_search(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    script.turns += [
        Turn(tool_calls=[call("search", {"words": "pg_class", "connector_ids": [connector_id]}, "c1")]),
        Turn(pieces=[text("Found it.")]),
        Turn(pieces=[text("I no longer have it.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)
    run = await send(client, headers, conversation_id, "find pg_class")
    await settled(client, headers, run["id"], seconds=30.0)

    withdrawn = await client.patch(
        f"{CONNECTORS}/{connector_id}",
        headers=headers,
        json={"allow_third_party_transfer": False},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    second = await send(client, headers, conversation_id, "again")
    await settled(client, headers, second["id"])

    withheld = [
        message.content for message in script.calls[2] if isinstance(message, ToolMessage)
    ]
    assert withheld == [WITHHELD_RESULT]
