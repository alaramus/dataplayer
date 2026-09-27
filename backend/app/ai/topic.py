"""What a chat window hears while an answer is being written (D137, D158).

The rows are the authority: a missed event costs nothing, because reading the
conversation reaches the same state, and a page opened mid-answer reads the
text so far from the run. Nothing is queued here.
"""

import asyncio
import uuid
from typing import Literal

from pydantic import BaseModel

from app.ai.models import AgentStepPublic, OpenIntent, RunStatus
from app.realtime.topics import Subscriber, TopicSet, UnknownTopic, register

NAME = "ai.runs"
# Apart from the agent's: a window listening to `ai.runs` re-reads its list of
# conversations on every event, and a quick answer is not one of them (D158).
QUICK_NAME = "ai.quick"


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


class WorkspaceOpened(BaseModel):
    kind: Literal["open"] = "open"
    conversation_id: uuid.UUID
    intent: OpenIntent


AgentEvent = (
    RunChanged | StepChanged | AnswerDelta | ReasoningDelta | TitleChanged | WorkspaceOpened
)


class QuickAnswerDelta(BaseModel):
    """What a quick chat's answer added since the last one (D158)."""

    kind: Literal["answer"] = "answer"
    chat_id: uuid.UUID
    text: str


class _PerUser:
    """Fan-out to the sockets of one user, like every topic here."""

    def __init__(self, name: str) -> None:
        self._name = name
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

    async def _deliver(self, user_id: uuid.UUID, event: BaseModel) -> None:
        async with self._lock:
            watching = list(self._subscribers.get(user_id, ()))
        for subscriber in watching:
            await subscriber.deliver(self._name, event)


class AgentTopic(_PerUser):
    def __init__(self) -> None:
        super().__init__(NAME)

    async def publish(self, user_id: uuid.UUID, event: AgentEvent) -> None:
        await self._deliver(user_id, event)


class QuickChatTopic(_PerUser):
    def __init__(self) -> None:
        super().__init__(QUICK_NAME)

    async def publish(self, user_id: uuid.UUID, event: QuickAnswerDelta) -> None:
        await self._deliver(user_id, event)


async def announce(topics: TopicSet, user_id: uuid.UUID, event: AgentEvent) -> None:
    try:
        topic = topics.get(NAME)
    except UnknownTopic:
        return
    if isinstance(topic, AgentTopic):
        await topic.publish(user_id, event)


async def announce_quick(
    topics: TopicSet, user_id: uuid.UUID, event: QuickAnswerDelta
) -> None:
    try:
        topic = topics.get(QUICK_NAME)
    except UnknownTopic:
        return
    if isinstance(topic, QuickChatTopic):
        await topic.publish(user_id, event)


register(NAME, AgentTopic)
register(QUICK_NAME, QuickChatTopic)
