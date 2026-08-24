"""Opening a WebSocket against the application from a test.

httpx alone cannot: its transport speaks HTTP only. Starlette's ``TestClient``
can, but it is synchronous and brings its own event loop — the trap the pool
tests already ran into, since a pool belongs to the loop that created it. This
transport stays inside the one session loop.

Not a fixture: the transport holds an anyio cancel scope, and a session-scoped
fixture is finalised in a different task than the one that entered it, which
that scope refuses. Opened and closed inside the test, it stays in one task.

The application's lifespan is not entered here — the session-scoped ``client``
fixture holds it open, and every test using these helpers asks for something
that depends on it.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession, WebSocketDisconnect, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from app.core.config import settings
from app.main import app

WS_URL = f"http://test{settings.API_V1_STR}/ws"


def token_of(headers: dict[str, str]) -> str:
    """The bare token out of an Authorization header."""
    return headers["Authorization"].removeprefix("Bearer ")


@asynccontextmanager
async def open_socket() -> AsyncIterator[AsyncWebSocketSession]:
    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://test"
    ) as client:
        async with aconnect_ws(WS_URL, client) as ws:
            yield ws


def _holds(error: BaseException, kind: type[BaseException]) -> bool:
    if isinstance(error, kind):
        return True
    if isinstance(error, BaseExceptionGroup):
        return any(_holds(inner, kind) for inner in error.exceptions)
    return False


@asynccontextmanager
async def hung_up_on() -> AsyncIterator[AsyncWebSocketSession]:
    """Assert that the server closes this socket.

    Not ``pytest.raises``: the disconnect travels out through the transport's
    task group and arrives wrapped in an exception group, which that does not
    match. Anything else still propagates, so a failed assertion inside the
    block is still a failure.
    """
    try:
        async with open_socket() as ws:
            yield ws
    except BaseException as error:
        if not _holds(error, WebSocketDisconnect):
            raise
    else:
        raise AssertionError("the socket stayed open")


@asynccontextmanager
async def authenticated_socket(
    headers: dict[str, str],
) -> AsyncIterator[AsyncWebSocketSession]:
    """A socket that has said who it is and been told it is ready."""
    async with open_socket() as ws:
        await ws.send_json({"type": "auth", "token": token_of(headers)})
        ready: dict[str, Any] = await ws.receive_json(timeout=5)
        assert ready["type"] == "ready", ready
        yield ws
