"""The agent changing data through real connections, end to end (D136, D46).

Every test scripts the model and lets the tools run against a PostgreSQL
connection of the test's own, so the acceptance of AI5 is read from what the
person was asked, from what the database holds afterwards, and from the steps
the server wrote.
"""

import uuid
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai import conversations, preferences, tools as ai_tools
from app.ai.models import AgentPreferences, Conversation
from app.ai.tools import (
    ALLOW_ALL,
    ALLOW_CHAT,
    ALLOW_ONCE,
    CHANGE_CHOICES,
    READ_ONLY_CHAT,
    JEV_DENIED,
    JEV_UNAVAILABLE,
)
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
    user_id_of,
)
from tests.ai.test_reading import call, paused, postgres_connector, rename, tool_results
from tests.utils.relation_fixture import conninfo
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


async def probe_execute(statement: str) -> None:
    """Change the working database directly, around the agent entirely."""
    async with await psycopg.AsyncConnection.connect(
        conninfo(), autocommit=True
    ) as conn:
        await conn.execute(statement)


async def probe_scalar(statement: str) -> Any:
    """One value from the working database, as the server itself would read it."""
    async with await psycopg.AsyncConnection.connect(
        conninfo(), autocommit=True
    ) as conn:
        cursor = await conn.execute(statement)
        row = await cursor.fetchone()
        return None if row is None else row[0]


async def test_jev_cannot_be_selected_without_a_key(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    conversation_id = await new_conversation(client, headers)
    response = await client.patch(
        f"{AI}/conversations/{conversation_id}",
        headers=headers,
        json={"change_policy": "jev"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("probability", "expected_error", "expected_rows"),
    [(0.2, JEV_DENIED, 0), (0.9, None, 1), (None, JEV_UNAVAILABLE, 0)],
)
async def test_jev_decides_even_when_global_allow_is_on(
    client: AsyncClient,
    headers: dict[str, str],
    script: Script,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    probability: float | None,
    expected_error: str | None,
    expected_rows: int,
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    table = f"ai_probe_{uuid.uuid4().hex[:12]}"
    await probe_execute(f"CREATE TABLE {table} (id integer)")
    sql = f"INSERT INTO {table} (id) VALUES (1)"
    script.turns += [
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": sql}, "c1")]),
        Turn(pieces=[text("Done.")]),
    ]

    class FakeClassifier:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "jev-test-key"

        async def ainvoke(self, request: dict[str, Any]) -> Any:
            assert sql in request["state"]["preview"]
            if probability is None:
                raise RuntimeError("provider failed")
            return SimpleNamespace(nouls={"allow": SimpleNamespace(noul=probability)})

    monkeypatch.setattr(ai_tools, "TypeSafeClassifier", FakeClassifier)
    await preferences.set_key(db, await user_id_of(client, headers), "typesafe", "jev-test-key")
    await client.patch(f"{AI}/settings", headers=headers, json={"allow_all_changes": True})
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)
    selected = await client.patch(
        f"{AI}/conversations/{conversation_id}",
        headers=headers,
        json={"change_policy": "jev"},
    )
    assert selected.status_code == 200, selected.text
    try:
        run = await send(client, headers, conversation_id, "add a row")
        finished = await settled(client, headers, run["id"])
        assert finished["status"] == "succeeded"
        assert finished["question"] is None
        [result] = tool_results(script, 1)
        if expected_error is not None:
            assert result == {"error": expected_error}
        assert await probe_scalar(f"SELECT count(*) FROM {table}") == expected_rows
        step = next(one for one in finished["steps"] if one["kind"] == "tool")
        assert any("Jev ·" in line for line in step["substeps"])
    finally:
        await probe_execute(f"DROP TABLE IF EXISTS {table}")


async def test_a_change_asks_and_allow_once_runs_it(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    name = f"probe shop {uuid.uuid4()}"
    connector_id = await postgres_connector(client, headers, transfer=True, name=name)
    table = f"ai_probe_{uuid.uuid4().hex[:12]}"
    await probe_execute(f"CREATE TABLE {table} (id integer)")
    sql = f"INSERT INTO {table} (id) VALUES (1)"
    script.turns += [
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": sql}, "c1")]),
        Turn(pieces=[text("One row added.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)
    try:
        run = await send(client, headers, conversation_id, "add a row")
        waiting = await paused(client, headers, run["id"])

        assert waiting["question"] == {
            "kind": "confirm_change",
            "question": f'Run 1 statement that changes data on "{name}"?',
            "choices": CHANGE_CHOICES,
            "connector_id": connector_id,
            "preview": {"summary": "1 statement would run", "lines": [sql]},
        }
        continued = await client.post(
            f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": ALLOW_ONCE}
        )
        assert continued.status_code == 200, continued.text
        finished = await settled(client, headers, run["id"])

        assert finished["status"] == "succeeded"
        assert await probe_scalar(f"SELECT count(*) FROM {table}") == 1
        # Once keeps nothing: the conversation still asks next time (D136).
        conversation = await db.get(Conversation, uuid.UUID(conversation_id))
        assert conversation is not None and conversation.change_policy == "ask"
        [result] = tool_results(script, 1)
        assert result["mode"] == "auto_commit"
        query_step = next(step for step in finished["steps"] if step["kind"] == "tool")
        assert query_step["substeps"] == ["Statement 1 · succeeded · 1 affected"]
    finally:
        await probe_execute(f"DROP TABLE IF EXISTS {table}")


async def test_a_read_only_chat_refuses_a_change_without_asking(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    """The narrow end of the three: not even the person is asked (D136)."""
    connector_id = await postgres_connector(client, headers, transfer=True)
    table = f"ai_probe_{uuid.uuid4().hex[:12]}"
    await probe_execute(f"CREATE TABLE {table} (id integer)")
    insert = f"INSERT INTO {table} (id) VALUES (1)"
    script.turns += [
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": insert}, "c1")]),
        Turn(pieces=[text("I may not change anything here.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)
    # Allowed everywhere, and refused here anyway: the chat is the narrower rule.
    await client.patch(f"{AI}/settings", headers=headers, json={"allow_all_changes": True})
    await client.patch(
        f"{AI}/conversations/{conversation_id}",
        headers=headers,
        json={"change_policy": "read_only"},
    )
    try:
        run = await send(client, headers, conversation_id, "add a row")
        finished = await settled(client, headers, run["id"])

        assert finished["status"] == "succeeded"
        assert finished["question"] is None
        [result] = tool_results(script, 1)
        assert result == {"error": READ_ONLY_CHAT}
        assert await probe_scalar(f"SELECT count(*) FROM {table}") == 0
        conversation = await db.get(Conversation, uuid.UUID(conversation_id))
        assert conversation is not None and conversation.change_policy == "read_only"
    finally:
        await probe_execute(f"DROP TABLE IF EXISTS {table}")


async def test_a_failing_statement_commits_nothing(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    table = f"ai_probe_{uuid.uuid4().hex[:12]}"
    await probe_execute(f"CREATE TABLE {table} (id integer)")
    sql = (
        f"INSERT INTO {table} (id) VALUES (1); "
        f"INSERT INTO {table} (id) VALUES ('not a number')"
    )
    script.turns += [
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": sql}, "c1")]),
        Turn(pieces=[text("Nothing was written.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)
    try:
        run = await send(client, headers, conversation_id, "add two rows")
        waiting = await paused(client, headers, run["id"])
        assert waiting["question"]["preview"]["summary"] == "2 statements would run"
        await client.post(
            f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": ALLOW_ONCE}
        )
        finished = await settled(client, headers, run["id"])

        assert finished["status"] == "succeeded"
        [result] = tool_results(script, 1)
        assert result["statements"][0]["status"] == "succeeded"
        assert result["statements"][1]["status"] == "failed"
        # One transaction: the first insert went back with the second (D136).
        assert await probe_scalar(f"SELECT count(*) FROM {table}") == 0
    finally:
        await probe_execute(f"DROP TABLE IF EXISTS {table}")


async def test_a_drop_is_rehearsed_for_the_confirmation_card(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    table = f"ai_probe_{uuid.uuid4().hex[:12]}"
    await probe_execute(f"CREATE TABLE {table} (id integer)")
    sql = f"DROP TABLE {table}"
    script.turns += [
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": sql}, "c1")]),
        Turn(pieces=[text("Dropped.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "drop the probe table")
    waiting = await paused(client, headers, run["id"])

    # A drop is rehearsed in a transaction that is rolled back (D46, D136).
    preview = waiting["question"]["preview"]
    assert preview is not None
    assert any("would succeed" in line for line in preview["lines"])
    assert await probe_scalar(f"SELECT to_regclass('public.{table}')") is not None
    await client.post(
        f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": ALLOW_ONCE}
    )
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    assert await probe_scalar(f"SELECT to_regclass('public.{table}')") is None


async def test_allow_all_in_this_chat_covers_only_this_chat(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    table = f"ai_probe_{uuid.uuid4().hex[:12]}"
    await probe_execute(f"CREATE TABLE {table} (id integer)")
    insert = f"INSERT INTO {table} (id) VALUES (1)"
    script.turns += [
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": insert}, "c1")]),
        Turn(pieces=[text("Added.")]),
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": insert}, "c2")]),
        Turn(pieces=[text("Added again.")]),
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": insert}, "c3")]),
        Turn(pieces=[text("Added in the other chat.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)
    try:
        run = await send(client, headers, conversation_id, "add a row")
        await paused(client, headers, run["id"])
        await client.post(
            f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": ALLOW_CHAT}
        )
        await settled(client, headers, run["id"])

        conversation = await db.get(Conversation, uuid.UUID(conversation_id))
        assert conversation is not None and conversation.change_policy == "allow"

        second = await send(client, headers, conversation_id, "add another")
        finished = await settled(client, headers, second["id"])
        assert finished["status"] == "succeeded"
        assert finished["question"] is None

        other = await new_conversation(client, headers)
        await rename(client, headers, other)
        elsewhere = await send(client, headers, other, "add a row here too")
        waiting = await paused(client, headers, elsewhere["id"])
        assert waiting["question"]["kind"] == "confirm_change"
        await client.post(
            f"{AI}/runs/{elsewhere['id']}/answer",
            headers=headers,
            json={"answer": ALLOW_ONCE},
        )
        await settled(client, headers, elsewhere["id"])

        assert await probe_scalar(f"SELECT count(*) FROM {table}") == 3
    finally:
        await probe_execute(f"DROP TABLE IF EXISTS {table}")


async def test_allow_all_in_every_chat_is_global_and_revocable(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    table = f"ai_probe_{uuid.uuid4().hex[:12]}"
    await probe_execute(f"CREATE TABLE {table} (id integer)")
    insert = f"INSERT INTO {table} (id) VALUES (1)"
    script.turns += [
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": insert}, "c1")]),
        Turn(pieces=[text("Added.")]),
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": insert}, "c2")]),
        Turn(pieces=[text("Added without asking.")]),
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": insert}, "c3")]),
        Turn(pieces=[text("Added after asking again.")]),
    ]
    first = await new_conversation(client, headers)
    await rename(client, headers, first)
    try:
        run = await send(client, headers, first, "add a row")
        await paused(client, headers, run["id"])
        await client.post(
            f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": ALLOW_ALL}
        )
        await settled(client, headers, run["id"])

        owner = await user_id_of(client, headers)
        stored = await db.get(AgentPreferences, owner)
        assert stored is not None and stored.allow_all_changes is True

        second = await new_conversation(client, headers)
        await rename(client, headers, second)
        run = await send(client, headers, second, "add a row")
        finished = await settled(client, headers, run["id"])
        assert finished["status"] == "succeeded"
        assert finished["question"] is None

        revoked = await client.patch(
            f"{AI}/settings", headers=headers, json={"allow_all_changes": False}
        )
        assert revoked.status_code == 200, revoked.text

        third = await new_conversation(client, headers)
        await rename(client, headers, third)
        run = await send(client, headers, third, "add a row")
        waiting = await paused(client, headers, run["id"])
        assert waiting["question"]["kind"] == "confirm_change"
        await client.post(
            f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": ALLOW_ONCE}
        )
        await settled(client, headers, run["id"])

        assert await probe_scalar(f"SELECT count(*) FROM {table}") == 3
    finally:
        await probe_execute(f"DROP TABLE IF EXISTS {table}")


async def test_a_pending_confirmation_survives_a_restart(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    connector_id = await postgres_connector(client, headers, transfer=True)
    table = f"ai_probe_{uuid.uuid4().hex[:12]}"
    await probe_execute(f"CREATE TABLE {table} (id integer)")
    insert = f"INSERT INTO {table} (id) VALUES (1)"
    script.turns += [
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": insert}, "c1")]),
        Turn(pieces=[text("Added.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)
    try:
        run = await send(client, headers, conversation_id, "add a row")
        await paused(client, headers, run["id"])

        # Startup sweeps stranded work but a pause for a person is kept (D137).
        await conversations.recover_interrupted(db)
        still = await client.get(f"{AI}/runs/{run['id']}", headers=headers)
        assert still.json()["status"] == "awaiting_answer"

        await client.post(
            f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": ALLOW_ONCE}
        )
        finished = await settled(client, headers, run["id"])

        assert finished["status"] == "succeeded"
        assert await probe_scalar(f"SELECT count(*) FROM {table}") == 1
    finally:
        await probe_execute(f"DROP TABLE IF EXISTS {table}")


async def test_a_destructive_action_shows_its_preview_and_drops(
    client: AsyncClient, headers: dict[str, str], script: Script
) -> None:
    name = f"probe shop {uuid.uuid4()}"
    connector_id = await postgres_connector(client, headers, transfer=True, name=name)
    table = f"ai_probe_{uuid.uuid4().hex[:12]}"
    await probe_execute(f"CREATE TABLE {table} (id integer)")
    node_id = f"public.{table}"
    script.turns += [
        Turn(
            tool_calls=[
                call(
                    "run_action",
                    {
                        "connector_id": connector_id,
                        "action_name": "drop_relation",
                        "node_id": node_id,
                        "params": {},
                    },
                    "c1",
                )
            ]
        ),
        Turn(pieces=[text("Dropped.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "drop the probe table")
    waiting = await paused(client, headers, run["id"])

    question = waiting["question"]
    assert question["kind"] == "confirm_change"
    assert question["question"] == f'Run "Drop" on "{name}"?'
    assert question["preview"] is not None
    assert table in question["preview"]["summary"]
    await client.post(
        f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": ALLOW_ONCE}
    )
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    assert await probe_scalar(f"SELECT to_regclass('public.{table}')") is None
    [result] = tool_results(script, 1)
    assert result["action"] == "drop_relation"
    assert "dropped" in result["result"]["message"]
    assert f'Running action "drop_relation" on "{name}"' in [
        step["title"] for step in finished["steps"]
    ]


async def test_a_grantee_with_read_access_is_refused_a_change(
    client: AsyncClient, headers: dict[str, str], script: Script, db: AsyncSession
) -> None:
    owner_headers = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    connector_id = await postgres_connector(client, owner_headers, transfer=True)
    grantee_id = await user_id_of(client, headers)
    granted = await client.put(
        f"{CONNECTORS}/{connector_id}/grants",
        headers=owner_headers,
        json={"user_id": str(grantee_id), "access": "read"},
    )
    assert granted.status_code == 200, granted.text
    table = f"ai_probe_{uuid.uuid4().hex[:12]}"
    await probe_execute(f"CREATE TABLE {table} (id integer)")
    insert = f"INSERT INTO {table} (id) VALUES (1)"
    script.turns += [
        Turn(tool_calls=[call("run_query", {"connector_id": connector_id, "sql": insert}, "c1")]),
        Turn(pieces=[text("I may not change this connection.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)
    try:
        run = await send(client, headers, conversation_id, "add a row")
        finished = await settled(client, headers, run["id"])

        # The level answers before anybody is asked, in D66's own sentence.
        assert finished["status"] == "succeeded"
        assert finished["question"] is None
        [refusal] = tool_results(script, 1)
        assert refusal["error"] == "A dml statement needs write access to this connection"
        assert await probe_scalar(f"SELECT count(*) FROM {table}") == 0
    finally:
        await probe_execute(f"DROP TABLE IF EXISTS {table}")
