"""Telling the owner of a job what it is doing, without them having to ask.

The read route stays the authority, exactly as it does for a query run (D64):
a message that never arrives costs nothing, because the client asks the job
and reaches the same terminal state. That is why nothing is queued here.
"""

import asyncio
import uuid

from pydantic import BaseModel

from app.jobs.models import JobKind, JobState
from app.realtime.topics import Subscriber, TopicSet, UnknownTopic, register

NAME = "jobs"


class JobEvent(BaseModel):
    """That a job moved, and enough to draw it without re-reading it."""

    job_id: uuid.UUID
    kind: JobKind
    subject_id: uuid.UUID | None = None
    state: JobState
    step: str | None = None
    step_index: int = 0
    step_count: int = 0
    message: str | None = None


class JobsTopic:
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

    async def publish(self, user_id: uuid.UUID, event: JobEvent) -> None:
        async with self._lock:
            watching = list(self._subscribers.get(user_id, ()))
        for subscriber in watching:
            await subscriber.deliver(NAME, event)


async def announce(topics: TopicSet, user_id: uuid.UUID, event: JobEvent) -> None:
    """Tap the owner on the shoulder, if they happen to be listening."""
    try:
        topic = topics.get(NAME)
    except UnknownTopic:
        return
    if not isinstance(topic, JobsTopic):
        return
    await topic.publish(user_id, event)


register(NAME, JobsTopic)
