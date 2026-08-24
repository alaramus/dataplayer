"""The one socket.

It authenticates, it hands frames to topics by name, and it tells the topics
when its subscriber goes away. It does not know what any topic does.
"""

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.core.config import settings
from app.core.db import async_session_maker
from app.realtime.messages import (
    ClientFrame,
    ErrorCode,
    WsAuth,
    WsError,
    WsEvent,
    WsReady,
    WsSubscribe,
    WsUnsubscribe,
)
from app.realtime.topics import TopicSet, UnknownTopic
from app.users.deps import user_for_token

router = APIRouter(tags=["realtime"])

_frames: TypeAdapter[ClientFrame] = TypeAdapter(ClientFrame)

# Close codes. 1008 is "policy violation", which is what a socket that never
# said who it is amounts to.
_UNAUTHENTICATED = 1008


class SocketSession:
    """One connected socket, and the topics it is watching.

    Sending is serialised: a topic delivers from its own task, and the reply to
    a client frame comes from the reading loop, so two writers can otherwise
    meet inside one frame.
    """

    def __init__(self, websocket: WebSocket, user_id: uuid.UUID) -> None:
        self._websocket = websocket
        self._user_id = user_id
        self._lock = asyncio.Lock()
        self.watching: set[str] = set()

    @property
    def user_id(self) -> uuid.UUID:
        return self._user_id

    async def send(self, frame: BaseModel) -> None:
        async with self._lock:
            await self._websocket.send_text(frame.model_dump_json())

    async def deliver(self, topic: str, payload: BaseModel) -> None:
        await self.send(WsEvent(topic=topic, payload=payload))

    async def refuse(self, code: ErrorCode, message: str) -> None:
        await self.send(WsError(code=code, message=message))


async def _authenticated_user(websocket: WebSocket) -> uuid.UUID | None:
    """Wait for the opening `auth` frame and check it.

    A socket that says nothing holds a connection and a slot for as long as it
    likes, so the wait has a ceiling.
    """
    try:
        async with asyncio.timeout(settings.WS_AUTH_TIMEOUT_SECONDS):
            raw = await websocket.receive_text()
    except (TimeoutError, WebSocketDisconnect):
        return None

    try:
        frame = _frames.validate_json(raw)
    except ValidationError:
        return None
    if not isinstance(frame, WsAuth):
        return None

    async with async_session_maker() as session:
        user = await user_for_token(session, frame.token)
    return None if user is None else user.id


@router.websocket("/ws")
async def socket(websocket: WebSocket) -> None:
    await websocket.accept()

    user_id = await _authenticated_user(websocket)
    if user_id is None:
        await websocket.close(code=_UNAUTHENTICATED)
        return

    topics: TopicSet = websocket.app.state.topics
    session = SocketSession(websocket, user_id)
    await session.send(WsReady())

    try:
        await _serve(websocket, session, topics)
    except WebSocketDisconnect:
        pass
    finally:
        await _drop_everything(session, topics)


async def _serve(
    websocket: WebSocket, session: SocketSession, topics: TopicSet
) -> None:
    while True:
        raw = await websocket.receive_text()
        try:
            frame: Any = _frames.validate_json(raw)
        except ValidationError:
            await session.refuse("malformed", "Frame not understood")
            continue

        if isinstance(frame, WsAuth):
            # One socket, one identity: re-authenticating would move the
            # subscriber between users while topics hold it by the old one.
            await session.refuse(
                "already_authenticated", "This socket already has an identity"
            )
            continue

        try:
            topic = topics.get(frame.topic)
        except UnknownTopic:
            await session.refuse("unknown_topic", f"No topic named {frame.topic}")
            continue

        if isinstance(frame, WsSubscribe):
            session.watching.add(frame.topic)
            await topic.subscribe(session)
        elif isinstance(frame, WsUnsubscribe):
            session.watching.discard(frame.topic)
            await topic.unsubscribe(session)


async def _drop_everything(session: SocketSession, topics: TopicSet) -> None:
    """Tell every topic this subscriber is gone.

    Without this a topic keeps working for a socket that closed — which for the
    health monitor means opening connections to other people's servers with
    nobody watching.
    """
    for name in list(session.watching):
        try:
            await topics.get(name).unsubscribe(session)
        except UnknownTopic:
            continue
    session.watching.clear()
