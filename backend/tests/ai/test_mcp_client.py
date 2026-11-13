"""Outside MCP servers the agent calls (D360, D361), against a real one on a port."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai import mcp_servers, mcp_tools
from app.ai.mcp_servers import AddressRefused, McpServer, check_address
from app.ai.tools import CHANGE_CHOICES, READ_ONLY_CHAT
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
from tests.ai.test_reading import call, paused, rename, tool_results
from tests.utils import mcp_fixture
from tests.utils.mcp_fixture import TOKEN, Fixture
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

SERVERS = f"{AI}/mcp-servers/"


@pytest.fixture(scope="module")
def outside() -> Iterator[Fixture]:
    yield from mcp_fixture.serve()


@pytest.fixture
def private_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MCP_CLIENT_ALLOW_PRIVATE", True)


@pytest.fixture
async def headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    person = await authentication_token_from_email(client=client, email=random_email(), db=db)
    await ready_agent(client, person)
    return person


async def add_server(
    client: AsyncClient, who: dict[str, str], url: str, **extra: Any
) -> dict[str, Any]:
    response = await client.post(
        SERVERS,
        headers=who,
        json={"name": "fixture", "url": url, "token": TOKEN, **extra},
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:9/mcp", "http://localhost/mcp", "http://10.1.2.3/mcp", "http://[::1]/mcp"]
)
async def test_a_private_address_is_refused_unless_the_installation_allows_it(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "MCP_CLIENT_ALLOW_PRIVATE", False)
    with pytest.raises(AddressRefused) as refused:
        await check_address(url)
    assert refused.value.code == "ai.mcp_address_private"

    monkeypatch.setattr(settings, "MCP_CLIENT_ALLOW_PRIVATE", True)
    await check_address(url)


async def test_a_public_address_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MCP_CLIENT_ALLOW_PRIVATE", False)
    await check_address("https://93.184.215.14/mcp")


async def test_an_address_with_credentials_or_another_scheme_is_refused(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    for url in ["ftp://example.com/mcp", "https://ann:pw@example.com/mcp", "example.com"]:
        response = await client.post(SERVERS, headers=headers, json={"name": "x", "url": url})
        assert response.status_code == 422, url


async def test_secrets_are_sealed_and_never_come_back(
    client: AsyncClient, headers: dict[str, str], db: AsyncSession
) -> None:
    made = await add_server(
        client, headers, "https://example.com/mcp", headers={"X-Team": "team-secret-91"}
    )
    assert made["has_token"] is True
    assert made["header_names"] == ["X-Team"]
    assert TOKEN not in str(made) and "team-secret-91" not in str(made)
    stored = await db.get(McpServer, uuid.UUID(made["id"]))
    assert stored is not None and stored.secret is not None
    assert TOKEN.encode() not in stored.secret and b"team-secret-91" not in stored.secret
    assert mcp_servers.request_headers(stored) == {
        "X-Team": "team-secret-91",
        "Authorization": f"Bearer {TOKEN}",
    }

    # A header sent without a value keeps the one it had; a new one needs one.
    kept = await client.patch(
        f"{SERVERS}{made['id']}", headers=headers, json={"headers": {"X-Team": None}}
    )
    assert kept.status_code == 200, kept.text
    await db.refresh(stored)
    assert mcp_servers.request_headers(stored)["X-Team"] == "team-secret-91"
    missing = await client.patch(
        f"{SERVERS}{made['id']}", headers=headers, json={"headers": {"X-Other": None}}
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "ai.mcp_header_value_required"

    cleared = await client.patch(
        f"{SERVERS}{made['id']}", headers=headers, json={"clear_token": True}
    )
    assert cleared.json()["has_token"] is False


async def test_a_reserved_header_and_a_taken_name_are_refused(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    reserved = await client.post(
        SERVERS,
        headers=headers,
        json={"name": "x", "url": "https://example.com/mcp", "headers": {"Authorization": "a"}},
    )
    assert reserved.status_code == 422
    await add_server(client, headers, "https://example.com/mcp")
    again = await client.post(
        SERVERS, headers=headers, json={"name": "fixture", "url": "https://example.com/mcp"}
    )
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "ai.mcp_server_name_taken"


async def test_somebody_else_s_server_is_not_found(
    client: AsyncClient, headers: dict[str, str], db: AsyncSession
) -> None:
    made = await add_server(client, headers, "https://example.com/mcp")
    other = await authentication_token_from_email(client=client, email=random_email(), db=db)
    assert (await client.get(SERVERS, headers=other)).json() == []
    for response in [
        await client.patch(f"{SERVERS}{made['id']}", headers=other, json={"enabled": False}),
        await client.post(f"{SERVERS}{made['id']}/tools", headers=other),
        await client.delete(f"{SERVERS}{made['id']}", headers=other),
    ]:
        assert response.status_code == 404


@pytest.mark.usefixtures("private_allowed")
async def test_the_tools_are_read_with_what_they_only_read(
    client: AsyncClient, headers: dict[str, str], outside: Fixture
) -> None:
    made = await add_server(client, headers, outside.url)
    response = await client.post(f"{SERVERS}{made['id']}/tools", headers=headers)
    assert response.status_code == 200, response.text
    tools = {tool["name"]: tool for tool in response.json()["tools"]}
    assert set(tools) == {"echo", "write_note"}
    assert tools["echo"]["read_only"] is True
    assert tools["write_note"]["read_only"] is False


@pytest.mark.usefixtures("private_allowed")
async def test_a_wrong_token_is_said_without_the_transport_s_words(
    client: AsyncClient, headers: dict[str, str], outside: Fixture
) -> None:
    response = await client.post(
        SERVERS, headers=headers, json={"name": "wrong", "url": outside.url, "token": "nope"}
    )
    made = response.json()
    tools = await client.post(f"{SERVERS}{made['id']}/tools", headers=headers)
    assert tools.status_code == 502
    assert tools.json()["detail"]["code"] == "ai.mcp_server_refused"
    assert "127.0.0.1" not in tools.text


async def test_an_unreachable_server_says_so(
    client: AsyncClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "MCP_CLIENT_ALLOW_PRIVATE", True)
    made = await add_server(client, headers, "http://127.0.0.1:9/mcp")
    tools = await client.post(f"{SERVERS}{made['id']}/tools", headers=headers)
    assert tools.status_code == 502
    assert tools.json()["detail"]["code"] == "ai.mcp_server_unreachable"


def test_a_tool_name_fits_providers_and_stays_unique() -> None:
    taken: set[str] = set()
    first = mcp_tools.tool_name("My Tracker!", "create issue", taken)
    second = mcp_tools.tool_name("My Tracker!", "create issue", taken)
    long = mcp_tools.tool_name("x" * 80, "y" * 80, taken)
    assert first == "My_Tracker__create_issue"
    assert second != first
    assert len(long) <= 64
    assert all(ch.isalnum() or ch in "_-" for ch in first + second + long)


@pytest.mark.usefixtures("private_allowed")
async def test_the_agent_reads_through_an_outside_tool_without_asking(
    client: AsyncClient, headers: dict[str, str], script: Script, outside: Fixture
) -> None:
    await add_server(client, headers, outside.url)
    script.turns += [
        Turn(tool_calls=[call("fixture__echo", {"word": "hello"}, "c1")]),
        Turn(pieces=[text("It said hello back.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "echo hello")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    assert "fixture__echo" in script.bound[0]
    [result] = tool_results(script, 1)
    assert result == {"mcp_server": "fixture", "tool": "echo", "content": "echo: hello"}
    assert [step["title"] for step in finished["steps"]][1] == 'Calling "echo" on "fixture"'


@pytest.mark.usefixtures("private_allowed")
async def test_a_tool_that_does_not_only_read_asks_with_its_arguments(
    client: AsyncClient, headers: dict[str, str], script: Script, outside: Fixture
) -> None:
    await add_server(client, headers, outside.url)
    script.turns += [
        Turn(tool_calls=[call("fixture__write_note", {"text": "buy milk"}, "c1")]),
        Turn(pieces=[text("Noted.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    run = await send(client, headers, conversation_id, "note: buy milk")
    waiting = await paused(client, headers, run["id"])

    assert waiting["question"] == {
        "kind": "confirm_change",
        "question": 'Run "write_note" on the MCP server "fixture"?',
        "choices": CHANGE_CHOICES,
        "connector_id": None,
        "preview": {
            "summary": "With these arguments:",
            "lines": ["{", '  "text": "buy milk"', "}"],
        },
    }
    assert outside.notes.count("buy milk") == 0
    continued = await client.post(
        f"{AI}/runs/{run['id']}/answer", headers=headers, json={"answer": CHANGE_CHOICES[0]}
    )
    assert continued.status_code == 200, continued.text
    finished = await settled(client, headers, run["id"])
    assert finished["status"] == "succeeded"
    assert outside.notes.count("buy milk") == 1


@pytest.mark.usefixtures("private_allowed")
async def test_a_read_only_chat_refuses_an_outside_change(
    client: AsyncClient, headers: dict[str, str], script: Script, outside: Fixture
) -> None:
    await add_server(client, headers, outside.url)
    script.turns += [
        Turn(tool_calls=[call("fixture__write_note", {"text": "never"}, "c1")]),
        Turn(pieces=[text("I may not.")]),
    ]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)
    await client.patch(
        f"{AI}/conversations/{conversation_id}",
        headers=headers,
        json={"change_policy": "read_only"},
    )

    run = await send(client, headers, conversation_id, "note: never")
    finished = await settled(client, headers, run["id"])

    assert finished["status"] == "succeeded"
    [result] = tool_results(script, 1)
    assert result == {"error": READ_ONLY_CHAT}
    assert "never" not in outside.notes


@pytest.mark.usefixtures("private_allowed")
async def test_a_server_or_a_tool_switched_off_is_not_offered(
    client: AsyncClient, headers: dict[str, str], script: Script, outside: Fixture
) -> None:
    made = await add_server(client, headers, outside.url)
    await client.patch(
        f"{SERVERS}{made['id']}", headers=headers, json={"tools_off": ["write_note"]}
    )
    script.turns += [Turn(pieces=[text("One.")]), Turn(pieces=[text("Two.")])]
    conversation_id = await new_conversation(client, headers)
    await rename(client, headers, conversation_id)

    first = await send(client, headers, conversation_id, "what can you call?")
    await settled(client, headers, first["id"])
    assert "fixture__echo" in script.bound[-1]
    assert "fixture__write_note" not in script.bound[-1]

    switched = await client.patch(
        f"{AI}/conversations/{conversation_id}",
        headers=headers,
        json={"mcp_servers_off": [made["id"]]},
    )
    assert switched.json()["mcp_servers_off"] == [made["id"]]
    second = await send(client, headers, conversation_id, "and now?")
    await settled(client, headers, second["id"])
    assert not any(name.startswith("fixture__") for name in script.bound[-1])
