"""Watches on what a screen shows, and the topic that tells it (D303)."""

import asyncio
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from pydantic import BaseModel

from app.adapters.changes import Changed
from app.connectors.changes import SourceChanges, SourceChangesTopic
from tests.adapters.zookeeper_fixture import (
    adapter,
    build_tree,
    new_root,
    on_server,
    remove_tree,
)


@pytest.fixture
async def root() -> AsyncIterator[str]:
    path = new_root()
    await on_server(lambda client: build_tree(client, path))
    yield path
    await on_server(lambda client: remove_tree(client, path))


class _Heard:
    """What a source said, from whatever thread it said it on."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.changes: list[Changed] = []

    def __call__(self, changed: Changed) -> None:
        with self._lock:
            self.changes.append(changed)

    async def until(self, wanted: Callable[[Changed], bool], seconds: float = 8.0) -> Changed:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            with self._lock:
                found = next((one for one in self.changes if wanted(one)), None)
            if found is not None:
                return found
            await asyncio.sleep(0.05)
        raise AssertionError(f"Not told in time; told {self.changes}")


async def test_a_new_child_a_new_value_and_a_deletion_are_told(root: str) -> None:
    heard = _Heard()
    watch = await adapter().watch_changes(heard)
    try:
        await watch.follow([root, f"{root}/config"])
        # Nothing has changed yet: the readings a watch starts from are not news.
        await asyncio.sleep(0.5)
        assert heard.changes == []

        await on_server(lambda client: client.create(f"{root}/fresh", b""))
        await heard.until(lambda one: root in one.levels)

        await on_server(lambda client: client.set(f"{root}/config", b"{}"))
        told = await heard.until(lambda one: f"{root}/config" in one.nodes)
        assert told.levels == frozenset({root})

        await on_server(lambda client: client.delete(f"{root}/config"))
        await heard.until(lambda one: f"{root}/config" in one.nodes and one is not told)
    finally:
        await watch.close()


async def test_a_node_no_longer_followed_is_not_told(root: str) -> None:
    heard = _Heard()
    watch = await adapter().watch_changes(heard)
    try:
        await watch.follow([f"{root}/config"])
        await watch.follow([f"{root}/text"])
        await on_server(lambda client: client.set(f"{root}/config", b"[]"))
        await on_server(lambda client: client.set(f"{root}/text", b"words"))
        await heard.until(lambda one: f"{root}/text" in one.nodes)
        assert not any(f"{root}/config" in one.nodes for one in heard.changes)
    finally:
        await watch.close()


async def test_what_is_not_a_znode_is_not_watched(root: str) -> None:
    watch = await adapter().watch_changes(_Heard())
    try:
        # A report's id and a level that is gone are passed over, not refused.
        await watch.follow(["\\server/srvr", f"{root}/gone", None])
    finally:
        await watch.close()


class _Socket:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.got: list[BaseModel] = []

    async def deliver(self, topic: str, payload: BaseModel) -> None:
        del topic
        self.got.append(payload)


async def test_the_topic_tells_the_person_gathered(root: str) -> None:
    topic = SourceChangesTopic()
    socket = _Socket(uuid.uuid4())
    connector_id = uuid.uuid4()
    await topic.subscribe(socket)
    try:
        await topic.follow(socket.user_id, connector_id, adapter(), [root])
        # A burst of writes is one telling.
        def burst(client: Any) -> None:
            for index in range(5):
                client.create(f"{root}/burst-{index}", b"")

        await on_server(burst)
        deadline = time.monotonic() + 8
        while not socket.got and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.6)
        told = socket.got[0]
        assert isinstance(told, SourceChanges)
        assert told.connector_id == connector_id and root in told.levels
        assert len(socket.got) <= 2

        # Asking for nothing closes the watch: nothing more is told.
        await topic.follow(socket.user_id, connector_id, adapter(), [])
        count = len(socket.got)
        await on_server(lambda client: client.create(f"{root}/after", b""))
        await asyncio.sleep(1.0)
        assert len(socket.got) == count
    finally:
        await topic.aclose()
