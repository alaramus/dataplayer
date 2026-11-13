"""A person's MCP access tokens (D358): listing, making, revoking."""

import uuid
from typing import Any

from fastapi import APIRouter

from app.ai import mcp_tokens
from app.ai.mcp_tokens import McpTokenCreate, McpTokenCreated, McpTokenPublic
from app.core.db import SessionDep
from app.core.problems import Problem
from app.core.schemas import Message
from app.core.translation import say
from app.users.deps import CurrentUser

router = APIRouter(prefix="/ai/mcp-tokens", tags=["ai"])


@router.get("/", response_model=list[McpTokenPublic])
async def read_mcp_tokens(session: SessionDep, current_user: CurrentUser) -> Any:
    """Every token of this person, never the token itself."""
    rows = await mcp_tokens.list_own(session, current_user.id)
    return [mcp_tokens.public_of(row) for row in rows]


@router.post("/", response_model=McpTokenCreated)
async def create_mcp_token(
    session: SessionDep, current_user: CurrentUser, body: McpTokenCreate
) -> Any:
    """Make a token. This answer is the only one that carries it."""
    return await mcp_tokens.create(session, current_user.id, body)


@router.delete("/{token_id}", response_model=Message)
async def delete_mcp_token(
    session: SessionDep, current_user: CurrentUser, token_id: uuid.UUID
) -> Any:
    """Revoke a token: the next call made with it is refused."""
    if not await mcp_tokens.delete_own(session, current_user.id, token_id):
        raise Problem(404, "ai.mcp_token_not_found")
    return Message(message=say("Token revoked"))
