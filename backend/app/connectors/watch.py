"""A node watched live: one socket, one node, for as long as the screen shows it (D323).

A socket of its own, as a terminal has (D148), rather than a topic of the
application's socket: a topic is named and takes no arguments (D18, D127),
and a watch is of one node at one interval. The socket opens unauthenticated
and its first frame says who is asking, for which connection, which node and
at what interval. After `ready` it carries the source's rows one way and
nothing the other; a new interval is a new socket.

Written out again in `frontend/src/features/market/frames.ts`, for the reason
`app/realtime/messages.py` gives: OpenAPI has no WebSocket channel.
"""

import asyncio
import logging
import uuid
from contextlib import aclosing, suppress
from typing import Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.adapters.live import LiveMode, SupportsLive
from app.adapters.protocol import AdapterError, ErrorKind, NodeNotFound
from app.connectors.access import adapter_for
from app.core.config import settings
from app.core.db import async_session_maker
from app.core.translation import N_, say
from app.users.deps import user_for_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["watch"])

# The codes the application's socket and a terminal's close with.
_POLICY = 1008
_NORMAL = 1000
_GONE = (WebSocketDisconnect, RuntimeError)

WatchRefusal = Literal[
    "unauthenticated",
    "malformed",
    "not_found",
    "forbidden",
    "disabled",
    # A source, or a node of it, that is not watched live.
    "unsupported",
    # The source itself said no: `error_kind` says in what way.
    "source",
]

_REFUSALS_BY_STATUS: dict[int, tuple[WatchRefusal, str]] = {
    404: ("not_found", N_("No such connection")),
    403: ("forbidden", N_("This connection is not shared with you")),
    409: ("disabled", N_("This connection is switched off")),
}


class WatchOpen(BaseModel):
    """Who is asking, for which node, at what interval. The first frame.

    The token travels here rather than in the address, for the reason the
    application's socket gives (D18).
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["open"]
    token: str
    connector_id: uuid.UUID
    node_id: str = Field(min_length=1, max_length=2048)
    interval: str | None = Field(default=None, max_length=16)


class WatchReady(BaseModel):
    type: Literal["ready"] = "ready"
    intervals: list[str]
    interval: str | None


class WatchRows(BaseModel):
    type: Literal["rows"] = "rows"
    part: str
    mode: LiveMode
    columns: list[str]
    rows: list[list[str | None]]
    key: list[str]


class WatchRefused(BaseModel):
    """Why nothing is watched. The socket closes straight after."""

    type: Literal["refused"] = "refused"
    code: WatchRefusal
    message: str
    error_kind: ErrorKind | None = None


class WatchEnded(BaseModel):
    """The source stopped answering. The socket closes straight after."""

    type: Literal["ended"] = "ended"
    message: str
    error_kind: ErrorKind | None = None


class _Refusal(Exception):
    def __init__(
        self, code: WatchRefusal, message: str, error_kind: ErrorKind | None = None
    ) -> None:
        super().__init__(message)
        self.frame = WatchRefused(code=code, message=message, error_kind=error_kind)


async def _send(websocket: WebSocket, frame: BaseModel) -> None:
    await websocket.send_text(frame.model_dump_json())


@router.websocket("/watch")
async def watch_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        opening = await _opening(websocket)
        adapter = await _adapter(opening)
        try:
            start = await adapter.live_start(opening.node_id, opening.interval)
        except NodeNotFound:
            raise _Refusal("not_found", say("No such node")) from None
        except ValueError as refusal:
            raise _Refusal("unsupported", str(refusal)) from None
        except AdapterError as failure:
            raise _Refusal("source", failure.message, failure.error_kind) from None
    except _Refusal as refusal:
        with suppress(*_GONE):
            await _send(websocket, refusal.frame)
            await websocket.close(code=_NORMAL)
        return
    except WebSocketDisconnect:
        return
    with suppress(*_GONE):
        await _send(
            websocket, WatchReady(intervals=start.intervals, interval=start.interval)
        )
        ended = await _relay(websocket, adapter, opening.node_id, start.interval)
        if ended is not None:
            await _send(websocket, ended)
        await websocket.close(code=_NORMAL)


async def _opening(websocket: WebSocket) -> WatchOpen:
    """The first frame, which must be an `open`, within the time a socket gets."""
    try:
        async with asyncio.timeout(settings.WS_AUTH_TIMEOUT_SECONDS):
            message = await websocket.receive()
    except TimeoutError:
        raise _Refusal("unauthenticated", say("Say who you are first")) from None
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(code=message.get("code", _NORMAL))
    text = message.get("text")
    try:
        return WatchOpen.model_validate_json(text if isinstance(text, str) else "")
    except ValidationError:
        raise _Refusal("malformed", say("The first frame opens a watch")) from None


async def _adapter(opening: WatchOpen) -> SupportsLive:
    async with async_session_maker() as session:
        user = await user_for_token(session, opening.token)
        if user is None:
            raise _Refusal("unauthenticated", say("Sign in again to watch this"))
        try:
            adapter = await adapter_for(
                session, opening.connector_id, user, requires="read"
            )
        except HTTPException as refusal:
            code, message = _REFUSALS_BY_STATUS.get(
                refusal.status_code,
                ("source", N_("The connection could not be opened")),
            )
            raise _Refusal(code, say(message)) from None
        except ValueError, ValidationError:
            raise _Refusal(
                "source", say("The settings of this connection are not valid")
            ) from None
    if not isinstance(adapter, SupportsLive):
        raise _Refusal(
            "unsupported", say("This kind of connection is not watched live")
        )
    return adapter


async def _relay(
    websocket: WebSocket, adapter: SupportsLive, node_id: str, interval: str | None
) -> WatchEnded | None:
    """Rows to the client until it leaves or the source stops; why it stopped."""
    rows = asyncio.create_task(_rows(websocket, adapter, node_id, interval))
    gone = asyncio.create_task(_left(websocket))
    try:
        done, _ = await asyncio.wait({rows, gone}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        # Also when this is cancelled itself, on shutdown: a stream left
        # behind would go on reading a market nobody watches.
        for task in (rows, gone):
            task.cancel()
        await asyncio.gather(rows, gone, return_exceptions=True)
    if rows not in done:
        return None
    failure = rows.exception()
    if isinstance(failure, AdapterError):
        return WatchEnded(message=failure.message, error_kind=failure.error_kind)
    if failure is not None and not isinstance(failure, _GONE):
        logger.warning("Watch stopped: %r", failure)
        return WatchEnded(message=say("Watching stopped"), error_kind="unknown")
    return WatchEnded(message=say("Watching stopped"), error_kind=None)


async def _rows(
    websocket: WebSocket, adapter: SupportsLive, node_id: str, interval: str | None
) -> None:
    # Closed with this task, so the source lets go of its stream at once
    # rather than whenever the generator is collected.
    async with aclosing(adapter.live(node_id, interval)) as batches:
        async for batch in batches:
            await _send(
                websocket,
                WatchRows(
                    part=batch.part,
                    mode=batch.mode,
                    columns=batch.columns,
                    rows=batch.rows,
                    key=batch.key,
                ),
            )


async def _left(websocket: WebSocket) -> None:
    """Returns when the client goes; nothing it sends after `open` is read."""
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
