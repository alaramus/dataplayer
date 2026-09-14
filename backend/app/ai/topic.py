"""What a chat window hears while an answer is being written (D137).

The rows are the authority: a missed event costs nothing, because reading the
conversation reaches the same state, and a page opened mid-answer reads the
text so far from the run. Nothing is queued here.
"""

import asyncio
import uuid
from typing import Literal

from pydantic import BaseModel

from app.ai.models import AgentStepPublic, RunStatus
from app.realtime.topics import Subscriber, TopicSet, UnknownTopic, register

NAME = "ai.runs"


class RunChanged(BaseModel):
    kind: Literal["run"] = "run"
    conversation_id: uuid.UUID
    run_id: uuid.UUID
    status: RunStatus
    error: str | None = None


class StepChanged(BaseModel):
    """A step began or ended. Its reasoning travels as deltas, not here."""

    kind: Literal["step"] = "step"
    conversation_id: uuid.UUID
    run_id: uuid.UUID
    step: AgentStepPublic


class AnswerDelta(BaseModel):
    kind: Literal["answer"] = "answer"
    conversation_id: uuid.UUID
    run_id: uuid.UUID
    text: str


class ReasoningDelta(BaseModel):
    kind: Literal["reasoning"] = "reasoning"
    conversation_id: uuid.UUID
    run_id: uuid.UUID
    ordinal: int
    text: str


class TitleChanged(BaseModel):
    kind: Literal["title"] = "title"
    conversation_id: uuid.UUID
    title: str


AgentEvent = RunChanged | StepChanged | AnswerDelta | ReasoningDelta | TitleChanged


class AgentTopic:
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

    async def publish(self, user_id: uuid.UUID, event: AgentEvent) -> None:
        async with self._lock:
            watching = list(self._subscribers.get(user_id, ()))
        for subscriber in watching:
            await subscriber.deliver(NAME, event)


async def announce(topics: TopicSet, user_id: uuid.UUID, event: AgentEvent) -> None:
    try:
        topic = topics.get(NAME)
    except UnknownTopic:
        return
    if isinstance(topic, AgentTopic):
        await topic.publish(user_id, event)


register(NAME, AgentTopic)
