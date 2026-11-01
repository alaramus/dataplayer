"""Watches on the znodes a screen shows, over one session held open (D303).

The one place this source keeps a session past a request (D297): a watch lives
as long as its session does. kazoo's recipes set the watch again after every
event and after a reconnect; a recipe this screen no longer wants stops the
next time it fires, since a ZooKeeper watch cannot be taken back.

A level is watched for its children, a znode for its data and its deletion.
Each recipe's first call is the reading it starts from, not a change, and is
not told.
"""

import logging
from collections.abc import Sequence
from threading import Lock

from kazoo.client import KazooClient
from kazoo.exceptions import KazooException
from kazoo.recipe.watchers import ChildrenWatch, DataWatch
from starlette.concurrency import run_in_threadpool

from app.adapters.changes import Changed, ChangeSink
from app.adapters.zookeeper.session import ZookeeperSession
from app.adapters.zookeeper.znodes import checked_path

logger = logging.getLogger(__name__)

# How many znodes one screen may have watched on one connection: the levels
# open in a tree and the tabs open on its znodes, with room to spare.
WATCH_CEILING = 300


def parent_of(path: str) -> str | None:
    head = path.rsplit("/", 1)[0]
    return head or None


def level_of(path: str) -> str | None:
    return None if path == "/" else path


class ZookeeperWatch:
    def __init__(self, client: KazooClient, sink: ChangeSink) -> None:
        self._client = client
        self._sink = sink
        self._lock = Lock()
        # The registration each watched path holds now. A recipe compares its
        # own against this and stops when it is no longer the one.
        self._children: dict[str, object] = {}
        self._data: dict[str, object] = {}

    async def follow(self, node_ids: Sequence[str | None]) -> None:
        wanted: list[str] = []
        for node_id in node_ids:
            try:
                path = "/" if node_id is None else checked_path(node_id)
            except ValueError:
                # A report or anything else that is not a znode is not watched.
                continue
            if path not in wanted:
                wanted.append(path)
        await run_in_threadpool(self._follow, wanted[:WATCH_CEILING])

    def _follow(self, wanted: list[str]) -> None:
        with self._lock:
            for gone in set(self._children) - set(wanted):
                del self._children[gone]
            for gone in set(self._data) - set(wanted):
                del self._data[gone]
            fresh_children = [path for path in wanted if path not in self._children]
            fresh_data = [path for path in wanted if path != "/" and path not in self._data]
            for path in fresh_children:
                self._children[path] = object()
            for path in fresh_data:
                self._data[path] = object()
        for path in fresh_children:
            self._watch_children(path)
        for path in fresh_data:
            self._watch_data(path)

    def _watch_children(self, path: str) -> None:
        token = self._children.get(path)
        first = [True]

        def changed(children: list[str]) -> bool:
            del children
            if self._children.get(path) is not token:
                return False
            if first[0]:
                first[0] = False
                return True
            # The parent level too: the count of children a row there shows
            # is part of what changed.
            levels = {level_of(path)} if path == "/" else {path, parent_of(path)}
            self._sink(Changed(levels=frozenset(levels)))
            return True

        try:
            ChildrenWatch(self._client, path, changed)
        except KazooException:
            # Not readable, or gone: nothing to watch until a screen asks again.
            with self._lock:
                if self._children.get(path) is token:
                    del self._children[path]

    def _watch_data(self, path: str) -> None:
        token = self._data.get(path)
        first = [True]

        def changed(data: bytes | None, stat: object) -> bool:
            del data
            if self._data.get(path) is not token:
                return False
            if first[0]:
                first[0] = False
                return True
            if stat is None:
                # Deleted. Its children's watch has stopped with it, so the next
                # time a screen asks, both are set afresh.
                with self._lock:
                    self._children.pop(path, None)
            self._sink(
                Changed(levels=frozenset({parent_of(path)}), nodes=frozenset({path}))
            )
            return True

        try:
            DataWatch(self._client, path, changed)
        except KazooException:
            with self._lock:
                if self._data.get(path) is token:
                    del self._data[path]

    async def close(self) -> None:
        with self._lock:
            self._children.clear()
            self._data.clear()
        await run_in_threadpool(_stop, self._client)


def _stop(client: KazooClient) -> None:
    try:
        client.stop()
        client.close()
    except Exception:  # noqa: BLE001 - a session that already dropped
        logger.debug("ZooKeeper watch session did not close cleanly", exc_info=True)


async def open_watch(session: ZookeeperSession, sink: ChangeSink) -> ZookeeperWatch:
    client = await session.held()
    return ZookeeperWatch(client, sink)
