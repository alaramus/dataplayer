"""Telling the two people in an access request what just happened.

The topic lives here rather than in ``app/realtime`` for the reason the health
one lives with connectors: the transport carries it without knowing what it is
(D18). Registration at the bottom of this file is all the socket learns.

Nothing is remembered between deliveries. A request is a durable row and the
screens read it; this only saves somebody from having to look. What is missed
while offline is not lost — it is still in the table.
"""

import asyncio
import uuid
from typing import Literal

from pydantic import BaseModel

from app.core.access import Grant
from app.realtime.topics import Subscriber, TopicSet, UnknownTopic, register

NAME = "shares.requests"


class RequestEvent(BaseModel):
    """One thing that happened to a request, addressed to one of the two sides.

    `asked` goes to the owner of the connection, `answered` to the person who
    asked. The connection is named in both, because a notification that cannot
    say what it is about is not worth showing.
    """

    kind: Literal["asked", "answered"]
    request_id: uuid.UUID
    connector_id: uuid.UUID
    connector_label: str
    # Who asked, for the owner; who answered, for the requester.
    person: str
    outcome: Literal["approved", "declined"] | None = None
    access: Grant | None = None


class RequestsTopic:
    """Fan-out to the sockets of one user.

    Per user rather than per socket, like every topic here: somebody with two
    tabs open is one person and hears once in each of them.
    """

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

    async def publish(self, user_id: uuid.UUID, event: RequestEvent) -> None:
        async with self._lock:
            watching = list(self._subscribers.get(user_id, ()))
        for subscriber in watching:
            await subscriber.deliver(NAME, event)


async def announce(topics: TopicSet, user_id: uuid.UUID, event: RequestEvent) -> None:
    """Tell one person, if they are listening.

    Nothing happens if they are not, and nothing is queued: the row in the
    database is the record, and this is only the tap on the shoulder.
    """
    try:
        topic = topics.get(NAME)
    except UnknownTopic:
        return
    if not isinstance(topic, RequestsTopic):
        return
    await topic.publish(user_id, event)


register(NAME, RequestsTopic)
