"""An outside MCP server for the client's tests (D360, D361), run in this process.

A real server on a real port: the client is the SDK's HTTP transport, so a
server reached any other way would test a path the agent never takes. It asks
for a bearer token, offers one tool that only reads and one that writes, and
keeps what was written for the test to look at.
"""

import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.types import ASGIApp, Receive, Scope, Send

TOKEN = "fixture-token-5b1e"


@dataclass
class Fixture:
    url: str
    notes: list[str] = field(default_factory=list)
    seen_headers: list[dict[str, str]] = field(default_factory=list)


def _app(fixture: Fixture) -> ASGIApp:
    server = FastMCP(
        name="Fixture",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True), description="Say a word back.")
    def echo(word: str) -> str:
        return f"echo: {word}"

    @server.tool(description="Keep a note.")
    def write_note(text: str) -> str:
        fixture.notes.append(text)
        return "kept"

    inner = server.streamable_http_app()

    async def guarded(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {key.decode().lower(): value.decode() for key, value in scope["headers"]}
            fixture.seen_headers.append(headers)
            if headers.get("authorization") != f"Bearer {TOKEN}":
                await send({"type": "http.response.start", "status": 401, "headers": []})
                await send({"type": "http.response.body", "body": b""})
                return
        await inner(scope, receive, send)

    return guarded


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def serve() -> Iterator[Fixture]:
    port = _free_port()
    fixture = Fixture(url=f"http://127.0.0.1:{port}/mcp")
    server = uvicorn.Server(
        uvicorn.Config(_app(fixture), host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("The fixture MCP server did not start")
        time.sleep(0.05)
    try:
        yield fixture
    finally:
        server.should_exit = True
        thread.join(timeout=5)
