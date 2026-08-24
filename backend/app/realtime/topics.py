"""What a topic is, and where the ones that exist are found.

The transport knows this file and nothing beyond it. A topic is registered by
the module that owns it — health lives with connectors, because it is about
connectors — so adding one is a new module plus a line of registration, not an
edit to the socket.

Topics are built by the application lifespan and closed by it. A topic that
keeps a background task alive is exactly the thing that outlives a request
(D10), so it cannot belong to a module global any more than a pool can.
"""

import uuid
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class Subscriber(Protocol):
    """One socket, from a topic's point of view.

    A topic never sees the socket itself: it is handed something it can name a
    user by and deliver to, which is all it needs and all a test has to fake.
    """

    @property
    def user_id(self) -> uuid.UUID: ...

    async def deliver(self, topic: str, payload: BaseModel) -> None: ...


@runtime_checkable
class Topic(Protocol):
    """Something a socket can watch.

    Both hands are told about the same subscriber object, so a topic can key
    whatever it keeps by user rather than by socket — which is how two tabs of
    the same person avoid doing the work twice.
    """

    async def subscribe(self, subscriber: Subscriber) -> None: ...

    async def unsubscribe(self, subscriber: Subscriber) -> None: ...

    async def aclose(self) -> None: ...


TopicFactory = Callable[[], Topic]

_registry: dict[str, TopicFactory] = {}


class UnknownTopic(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown topic: {name}")
        self.name = name


def register(name: str, factory: TopicFactory) -> None:
    _registry[name] = factory


class TopicSet:
    """The topics of one running application.

    Built once at startup and closed at shutdown. A socket asks it by name and
    gets ``UnknownTopic`` for anything else — a topic is reachable only through
    the registry that holds it, so a client cannot name something else and be
    served.
    """

    def __init__(self, topics: dict[str, Topic]) -> None:
        self._topics = topics

    def get(self, name: str) -> Topic:
        topic = self._topics.get(name)
        if topic is None:
            raise UnknownTopic(name)
        return topic

    async def aclose(self) -> None:
        for topic in self._topics.values():
            await topic.aclose()
        self._topics.clear()


def build_all() -> TopicSet:
    return TopicSet({name: factory() for name, factory in _registry.items()})
