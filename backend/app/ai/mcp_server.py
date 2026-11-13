"""`/mcp`: the agent's tools offered to an agent outside DataPlayer (D357, D358).

A route of the backend, not a server of its own (D124). The token is checked
here, before MCP sees the request; the tools are the chat's, over a host that
records no step and asks nobody. The `mcp` SDK is imported by this module
alone.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException
from mcp.server.fastmcp import FastMCP
from mcp.server.lowlevel.server import request_ctx
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from app.adapters.cache import DataCache
from app.adapters.protocol import AdapterError
from app.adapters.resources import ResourceStore
from app.ai import mcp_tokens
from app.ai.mcp_tokens import Caller
from app.ai.tools import (
    Operation,
    PreviewMaker,
    ToolResult,
    bounded_json,
    safe_error,
    shared_tools,
    transfer_refusal,
)
from app.connectors import access
from app.connectors.models import Connector
from app.core.access import Access
from app.core.db import async_session_maker
from app.core.translation import current_language
from app.queries.execution import RunRefused as QueryRefused
from app.search.engine import SearchEngine
from app.users.models import User

logger = logging.getLogger(__name__)

PATH = "/mcp"
# Where the request's verified caller travels: the tool runs in a task of the
# session manager, started from the lifespan, so a context variable set while
# the request is checked never reaches it. The request itself does.
CALLER_KEY = "dataplayer.mcp_caller"

READ_ONLY_TOKEN = "This token may only read. Make a token that may change data to do this."
FAILED = "The operation failed. Nothing about why can be said here; try it in DataPlayer."
INSTRUCTIONS = (
    "DataPlayer connects databases, files, queues and other sources. Start with "
    "list_connections, then browse_catalog and describe_node; use ids exactly as "
    "returned. A connection marked transfer_not_allowed cannot be read until its "
    "owner allows third-party transfer in DataPlayer."
)
READ_TOOLS = frozenset(
    {"list_connections", "search", "browse_catalog", "describe_node", "read_rows", "list_actions"}
)


def current_caller() -> Caller:
    request = request_ctx.get().request
    caller = request.scope.get(CALLER_KEY) if request is not None else None
    if not isinstance(caller, Caller):
        # The endpoint refuses a request without one before MCP reads it.
        raise RuntimeError("An MCP tool ran without a verified caller")
    return caller


@dataclass
class McpHost:
    """The shared tools' host for a call from outside (D357)."""

    resources: ResourceStore
    data_cache: DataCache
    search_engine: SearchEngine | None
    attached: tuple[uuid.UUID, ...] = ()

    async def invoke(self, title: str, operation: Operation) -> str:
        del title  # Nobody watches a step of an outside call.
        caller = current_caller()
        english = current_language.set("en")
        try:
            async with async_session_maker() as session:
                user = await session.get(User, caller.user_id)
                if user is None or not user.is_active:
                    result: Any = {"error": "user_not_available"}
                else:
                    result = await operation(session, user)
        except (HTTPException, AdapterError, QueryRefused, ValueError) as failure:
            result = {"error": safe_error(failure)}
        except Exception:  # noqa: BLE001 - driver text never reaches the caller
            logger.exception("An MCP tool failed")
            result = {"error": FAILED}
        finally:
            current_language.reset(english)
        if isinstance(result, ToolResult):
            result = result.value
        return bounded_json(result)

    async def connector(
        self, session: AsyncSession, user: User, connector_id: uuid.UUID
    ) -> tuple[Connector, Any, Access] | dict[str, Any]:
        connector, held = await access.resolve(session, connector_id, user, requires="read")
        if not connector.allow_third_party_transfer:
            # No Allow from here: nobody is on the other end to ask (D135).
            return transfer_refusal(connector, held)
        source = await access.resolve_source(
            session, connector_id, user, self.resources, requires="read"
        )
        return connector, source.adapter, held

    async def confirm_change(
        self,
        session: AsyncSession,
        *,
        connector: Connector,
        question: str,
        preview: PreviewMaker | None = None,
    ) -> str | None:
        del session, connector, question, preview
        return READ_ONLY_TOKEN if current_caller().policy == "read_only" else None

    async def connection_label(self, connector_id: str) -> str:
        return connector_id


def build_server(host: McpHost) -> FastMCP:
    server = FastMCP(
        name="DataPlayer",
        instructions=INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        # A bearer token is what a rebinding page cannot send, and the
        # default protection admits only localhost as the Host.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    for fn, name, description in shared_tools(
        host, change_note="A change is refused when the token may only read."
    ):
        server.add_tool(
            fn,
            name=name,
            description=description,
            annotations=ToolAnnotations(
                readOnlyHint=name in READ_TOOLS, openWorldHint=False
            ),
            structured_output=False,
        )
    return server


@asynccontextmanager
async def serving(
    application: FastAPI,
    *,
    resources: ResourceStore,
    data_cache: DataCache,
    search_engine: SearchEngine | None,
) -> AsyncIterator[None]:
    """Run the MCP session manager for as long as the application.

    A session manager runs once, so every lifespan builds its own server. It
    runs in a task of its own: its task group must be left by the task that
    entered it, and a lifespan is not always entered and left by one task —
    the test suite's session fixture is not.
    """
    server = build_server(
        McpHost(resources=resources, data_cache=data_cache, search_engine=search_engine)
    )
    server.streamable_http_app()
    manager = server.session_manager
    started, stop = asyncio.Event(), asyncio.Event()

    async def run() -> None:
        async with manager.run():
            started.set()
            await stop.wait()

    task = asyncio.create_task(run(), name="mcp-sessions")
    waiter = asyncio.ensure_future(started.wait())
    await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
    if task.done():
        waiter.cancel()
        task.result()
    application.state.mcp_sessions = manager
    try:
        yield
    finally:
        stop.set()
        await task


def unauthorized(missing: bool) -> JSONResponse:
    return JSONResponse(
        {
            "error": "invalid_token",
            "error_description": (
                "Send a DataPlayer MCP token as Authorization: Bearer"
                if missing
                else "The token is unknown, expired or revoked"
            ),
        },
        status_code=401,
        headers={
            "WWW-Authenticate": "Bearer" if missing else 'Bearer error="invalid_token"'
        },
    )


class McpEndpoint:
    """The route: a verified token, then MCP's own transport."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope)
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        caller: Caller | None = None
        if scheme.lower() == "bearer" and token.strip():
            async with async_session_maker() as session:
                caller = await mcp_tokens.verify(session, token.strip())
        if caller is None:
            await unauthorized(missing=not token.strip())(scope, receive, send)
            return
        scope[CALLER_KEY] = caller
        manager: StreamableHTTPSessionManager = request.app.state.mcp_sessions
        await manager.handle_request(scope, receive, send)


def mount(application: FastAPI) -> None:
    # A Route given an ASGI app rather than a function passes every method.
    application.router.routes.append(
        Route(PATH, endpoint=McpEndpoint(), include_in_schema=False)
    )
