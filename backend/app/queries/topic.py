"""Telling a console what its run is doing, without it having to ask.

D64: the socket announces, and the read route stays the authority. A message
that never arrives therefore costs nothing — the client polls the run and
reaches the same terminal state. That is why nothing is queued here and why
this file is short.
"""

import asyncio
import uuid

from pydantic import BaseModel

from app.queries.runs import RunStatus
from app.realtime.topics import Subscriber, TopicSet, UnknownTopic, register

NAME = "queries.runs"


class RunEvent(BaseModel):
    """That a run changed state, and enough to decide whether to re-read it."""

    run_id: uuid.UUID
    document_id: uuid.UUID | None = None
    status: RunStatus
    # How many statements have reached a terminal state, so a console can show
    # progress without asking after every one.
    finished_statements: int = 0
    statement_count: int = 0


class RunsTopic:
    """Fan-out to the sockets of one user, like every topic here."""

    def __init__(self) -> None:
        self._subscribers: dict[uuid.UUID, set[Subscriber]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, subscriber: Subscriber) -> None:
        async with self._lock:
            self._subscribers.setdefault(subscriber.user_id, set()).add(subscriber)

    async def unsubscribe(self, subscriber: Subscriber) -> None:
        async with self._lock:
            watching = self._subscribers.get(subscriber.user_id)
            if watching is None:
                return
            watching.discard(subscriber)
            if not watching:
                del self._subscribers[subscriber.user_id]

    async def aclose(self) -> None:
        async with self._lock:
            self._subscribers.clear()

    async def publish(self, user_id: uuid.UUID, event: RunEvent) -> None:
        async with self._lock:
            watching = list(self._subscribers.get(user_id, ()))
        for subscriber in watching:
            await subscriber.deliver(NAME, event)


async def announce(topics: TopicSet, user_id: uuid.UUID, event: RunEvent) -> None:
    """Tap the owner on the shoulder, if they happen to be listening."""
    try:
        topic = topics.get(NAME)
    except UnknownTopic:
        return
    if not isinstance(topic, RunsTopic):
        return
    await topic.publish(user_id, event)


register(NAME, RunsTopic)
