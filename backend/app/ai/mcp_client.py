"""The client side of MCP: listing an outside server's tools and calling one (D360, D361).

The `mcp` SDK is imported here and in `mcp_server.py` alone. Every call opens
its own session and closes it: a run may pause for days and resume in another
process, and a session held across that would be a session lost.
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

from app.ai.mcp_servers import AddressRefused, McpServer, check_address, request_headers
from app.core.problems import MESSAGES, ProblemCode

logger = logging.getLogger(__name__)

CONNECT_SECONDS = 10.0
LIST_SECONDS = 15.0
CALL_SECONDS = 60.0
MAX_TOOLS = 100

FailureKind = Literal["unreachable", "refused", "failed"]
# What a person and the model read of a failure: the transport's own text may
# carry the address with its token, so it never leaves this module (D2c).
CODES: dict[FailureKind, ProblemCode] = {
    "unreachable": "ai.mcp_server_unreachable",
    "refused": "ai.mcp_server_refused",
    "failed": "ai.mcp_server_failed",
}


class McpCallFailed(Exception):
    def __init__(self, kind: FailureKind, code: ProblemCode | None = None) -> None:
        self.kind = kind
        self.code: ProblemCode = code or CODES[kind]
        self.message = MESSAGES[self.code]
        super().__init__(self.message)


@dataclass(frozen=True)
class RemoteTool:
    name: str
    title: str | None
    description: str | None
    input_schema: dict[str, Any]
    read_only: bool


@dataclass(frozen=True)
class CallOutcome:
    text: str
    is_error: bool


def _kind_of(failure: BaseException) -> FailureKind:
    found: list[BaseException] = [failure]
    while found:
        one = found.pop()
        if isinstance(one, httpx.HTTPStatusError) and one.response.status_code in (401, 403):
            return "refused"
        if isinstance(one, (httpx.ConnectError, httpx.TimeoutException, TimeoutError)):
            return "unreachable"
        if isinstance(one, BaseExceptionGroup):
            found.extend(one.exceptions)
        if one.__cause__ is not None:
            found.append(one.__cause__)
    return "failed"


@asynccontextmanager
async def _session(server: McpServer, read_seconds: float) -> AsyncIterator[ClientSession]:
    await check_address(server.url)
    async with (
        httpx.AsyncClient(
            headers=request_headers(server),
            timeout=httpx.Timeout(read_seconds, connect=CONNECT_SECONDS),
            follow_redirects=False,
        ) as http,
        streamable_http_client(server.url, http_client=http) as (read, write, _id),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


async def list_tools(server: McpServer) -> list[RemoteTool]:
    try:
        async with _session(server, LIST_SECONDS) as session:
            tools: list[RemoteTool] = []
            cursor: str | None = None
            while len(tools) < MAX_TOOLS:
                page = await session.list_tools(cursor)
                for tool in page.tools:
                    annotations = tool.annotations
                    tools.append(
                        RemoteTool(
                            name=tool.name,
                            title=tool.title or (annotations.title if annotations else None),
                            description=tool.description,
                            input_schema=dict(tool.inputSchema or {}),
                            read_only=bool(annotations and annotations.readOnlyHint),
                        )
                    )
                cursor = page.nextCursor
                if cursor is None:
                    break
            return tools[:MAX_TOOLS]
    except AddressRefused as refused:
        raise McpCallFailed("unreachable", refused.code) from refused
    except Exception as failure:  # noqa: BLE001 - reduced to a kind
        kind = _kind_of(failure)
        logger.warning("Listing the tools of an MCP server failed: %s", kind)
        raise McpCallFailed(kind) from failure


def _text_of(parts: list[Any]) -> str:
    texts: list[str] = []
    for part in parts:
        if isinstance(part, TextContent):
            texts.append(part.text)
        else:
            texts.append(f"[{getattr(part, 'type', 'content')} left out]")
    return "\n".join(texts)


async def call_tool(server: McpServer, name: str, arguments: dict[str, Any]) -> CallOutcome:
    try:
        async with _session(server, CALL_SECONDS) as session:
            result = await session.call_tool(name, arguments)
    except AddressRefused as refused:
        raise McpCallFailed("unreachable", refused.code) from refused
    except Exception as failure:  # noqa: BLE001 - reduced to a kind
        kind = _kind_of(failure)
        logger.warning("A call to an MCP server failed: %s", kind)
        raise McpCallFailed(kind) from failure
    text = _text_of(list(result.content))
    if not text and result.structuredContent is not None:
        text = json.dumps(result.structuredContent, ensure_ascii=False, default=str)
    return CallOutcome(text=text, is_error=bool(result.isError))
