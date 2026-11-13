"""An outside agent at /mcp: the token, the tools, the checks (D357, D358).

Spoken to as a client speaks MCP's Streamable HTTP transport, against a
PostgreSQL connection of the test's own.
"""

import json
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai import mcp_server
from app.ai.tools import TRANSFER_MARKER
from app.core.config import settings
from tests.utils.database import working_postgres_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

TOKENS = f"{settings.API_V1_STR}/ai/mcp-tokens/"
CONNECTORS = f"{settings.API_V1_STR}/connectors/"
SHARED = {
    "list_connections",
    "search",
    "browse_catalog",
    "describe_node",
    "read_rows",
    "run_query",
    "list_actions",
    "run_action",
    "read_guide",
}


async def person(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(client=client, email=random_email(), db=db)


async def token_of(client: AsyncClient, headers: dict[str, str], policy: str) -> str:
    response = await client.post(
        TOKENS, headers=headers, json={"name": f"mcp {policy}", "policy": policy}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["token"])


async def connection(
    client: AsyncClient, headers: dict[str, str], *, transfer: bool
) -> str:
    response = await client.post(
        CONNECTORS,
        headers=headers,
        json={
            "name": f"mcp reads {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
            "allow_third_party_transfer": transfer,
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def rpc(
    client: AsyncClient, token: str | None, method: str, params: dict[str, Any] | None = None
) -> Any:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return await client.post(
        mcp_server.PATH,
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )


async def call(client: AsyncClient, token: str, tool: str, **arguments: Any) -> Any:
    response = await rpc(client, token, "tools/call", {"name": tool, "arguments": arguments})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


async def test_without_a_valid_token_nothing_is_answered(
    client: AsyncClient, db: AsyncSession
) -> None:
    missing = await rpc(client, None, "tools/list")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"

    wrong = await rpc(client, "dp_mcp_not-a-token", "tools/list")
    assert wrong.status_code == 401
    assert "invalid_token" in wrong.headers["www-authenticate"]

    headers = await person(client, db)
    token = await token_of(client, headers, "full")
    listed = (await client.get(TOKENS, headers=headers)).json()
    await client.delete(f"{TOKENS}{listed[0]['id']}", headers=headers)
    revoked = await rpc(client, token, "tools/list")
    assert revoked.status_code == 401


async def test_the_shared_tools_are_offered_and_the_chat_only_ones_are_not(
    client: AsyncClient, db: AsyncSession
) -> None:
    token = await token_of(client, await person(client, db), "read_only")

    initialized = await rpc(
        client,
        token,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    )
    assert initialized.status_code == 200, initialized.text
    assert initialized.json()["result"]["serverInfo"]["name"] == "DataPlayer"

    listed = await rpc(client, token, "tools/list")
    assert listed.status_code == 200, listed.text
    tools = {tool["name"]: tool for tool in listed.json()["result"]["tools"]}
    assert set(tools) == SHARED
    assert tools["read_rows"]["annotations"]["readOnlyHint"] is True
    assert tools["run_query"]["annotations"]["readOnlyHint"] is False
    assert "connector_id" in tools["run_query"]["inputSchema"]["properties"]
    assert tools["read_guide"]["annotations"]["readOnlyHint"] is True

    guide = await call(client, token, "read_guide", key="connections")
    assert guide["title"] == "Connections"


async def test_reads_go_through_the_owner_and_the_transfer_flag(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await person(client, db)
    allowed = await connection(client, headers, transfer=True)
    closed = await connection(client, headers, transfer=False)
    token = await token_of(client, headers, "read_only")

    listed = await call(client, token, "list_connections")
    by_id = {one["id"]: one for one in listed["connections"]}
    assert by_id[allowed]["third_party_transfer"] == "allowed"
    assert by_id[closed]["third_party_transfer"] == TRANSFER_MARKER

    catalog = await call(client, token, "browse_catalog", connector_id=allowed)
    assert catalog["connector_id"] == allowed
    assert catalog["nodes"]

    refused = await call(client, token, "browse_catalog", connector_id=closed)
    assert refused["error"] == TRANSFER_MARKER
    assert "nodes" not in refused

    answer = await call(client, token, "run_query", connector_id=allowed, sql="SELECT 41 + 1 AS n")
    assert answer["mode"] == "read"
    assert answer["statements"][0]["status"] == "succeeded"

    # Another person's connection is not this token's to read.
    stranger = await token_of(client, await person(client, db), "full")
    foreign = await call(client, stranger, "browse_catalog", connector_id=allowed)
    assert "error" in foreign
    assert "nodes" not in foreign


@pytest.mark.parametrize("policy", ["read_only", "full"])
async def test_a_change_is_refused_or_run_by_the_token_s_policy(
    client: AsyncClient, db: AsyncSession, policy: str
) -> None:
    headers = await person(client, db)
    connector_id = await connection(client, headers, transfer=True)
    token = await token_of(client, headers, policy)
    table = f"mcp_probe_{uuid.uuid4().hex[:12]}"

    answer = await call(
        client,
        token,
        "run_query",
        connector_id=connector_id,
        sql=f"CREATE TEMP TABLE {table} (a int)",
    )
    if policy == "read_only":
        assert answer == {"error": mcp_server.READ_ONLY_TOKEN}
    else:
        assert answer["mode"] == "auto_commit"
        assert [one["status"] for one in answer["statements"]] == ["succeeded"]


async def test_a_failure_says_nothing_of_the_driver(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await person(client, db)
    connector_id = await connection(client, headers, transfer=True)
    token = await token_of(client, headers, "read_only")

    answer = await call(client, token, "browse_catalog", connector_id="not-a-uuid")
    assert "error" in answer
    answer = await call(
        client, token, "read_rows", connector_id=connector_id, node_id="no such node"
    )
    assert "error" in answer
    assert working_postgres_options()["password"] not in json.dumps(answer)
