"""A person's outside MCP servers (D360): the list, saving one, reading its tools."""

import uuid
from typing import Any

from fastapi import APIRouter

from app.ai import mcp_servers, mcp_tools
from app.ai.mcp_client import McpCallFailed
from app.ai.mcp_servers import (
    McpServerCreate,
    McpServerPublic,
    McpServerUpdate,
    McpToolPublic,
    McpToolsPublic,
    ServerRefused,
)
from app.core.db import SessionDep
from app.core.problems import Problem
from app.core.schemas import Message
from app.core.translation import say
from app.users.deps import CurrentUser

router = APIRouter(prefix="/ai/mcp-servers", tags=["ai"])


def _refused(refused: ServerRefused) -> Problem:
    if refused.code == "ai.mcp_server_name_taken":
        return Problem(409, refused.code)
    if refused.code == "ai.mcp_server_limit":
        return Problem(422, refused.code, limit=str(refused.params["limit"]))
    return Problem(422, refused.code, name=str(refused.params.get("name", "")))


@router.get("/", response_model=list[McpServerPublic])
async def read_mcp_servers(session: SessionDep, current_user: CurrentUser) -> Any:
    """Every outside MCP server of this person; never a token or a header's value."""
    return [mcp_servers.public_of(one) for one in await mcp_servers.list_own(session, current_user.id)]


@router.post("/", response_model=McpServerPublic)
async def create_mcp_server(
    session: SessionDep, current_user: CurrentUser, body: McpServerCreate
) -> Any:
    try:
        server = await mcp_servers.create(session, current_user.id, body)
    except ServerRefused as refused:
        raise _refused(refused) from refused
    return mcp_servers.public_of(server)


@router.patch("/{server_id}", response_model=McpServerPublic)
async def update_mcp_server(
    session: SessionDep, current_user: CurrentUser, server_id: uuid.UUID, body: McpServerUpdate
) -> Any:
    server = await mcp_servers.get_own(session, current_user.id, server_id)
    if server is None:
        raise Problem(404, "ai.mcp_server_not_found")
    try:
        changed = await mcp_servers.update(session, server, body)
    except ServerRefused as refused:
        raise _refused(refused) from refused
    return mcp_servers.public_of(changed)


@router.delete("/{server_id}", response_model=Message)
async def delete_mcp_server(
    session: SessionDep, current_user: CurrentUser, server_id: uuid.UUID
) -> Any:
    if not await mcp_servers.delete_own(session, current_user.id, server_id):
        raise Problem(404, "ai.mcp_server_not_found")
    mcp_tools.forget(server_id)
    return Message(message=say("MCP server removed"))


@router.post("/{server_id}/tools", response_model=McpToolsPublic)
async def read_mcp_server_tools(
    session: SessionDep, current_user: CurrentUser, server_id: uuid.UUID
) -> Any:
    """Ask the server what it offers now, which also says whether it answers."""
    server = await mcp_servers.get_own(session, current_user.id, server_id)
    if server is None:
        raise Problem(404, "ai.mcp_server_not_found")
    mcp_tools.forget(server_id)
    try:
        tools = await mcp_tools.tools_of(server)
    except McpCallFailed as failed:
        raise Problem(502, failed.code) from failed
    return McpToolsPublic(
        server_id=server.id,
        tools=[
            McpToolPublic(
                name=tool.name,
                title=tool.title,
                description=tool.description,
                read_only=tool.read_only,
                enabled=tool.name not in server.tools_off,
            )
            for tool in tools
        ],
    )
