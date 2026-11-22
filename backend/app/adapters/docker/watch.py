"""What changed on a daemon, told while somebody looks (D414, on D303).

Two kinds of stream, opened only for what a screen shows. An open Logs tab is
a `follow=true` log stream from now; any line on it tells that tab to read
again, at most once every `LOG_EVERY` seconds, so a container printing a
thousand lines a second costs one refresh every two. A level shown — the top,
a group, a project, a node — is the daemon's `/events` stream, one per watch,
telling the group an event is about.

A stream that drops is opened again after `RETRY_SECONDS`; one that cannot be
opened says nothing, and the screen refreshes by hand as before.
"""

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Callable, Sequence

from app.adapters.changes import Changed, ChangeSink
from app.adapters.docker.catalog import parse, project_id, view_id
from app.adapters.docker.inventory import COMPOSE_PROJECT
from app.adapters.docker.session import DockerSession, segment
from app.adapters.docker_api.client import EngineRefused, EngineUnreachable
from app.adapters.protocol import AdapterError

logger = logging.getLogger(__name__)

LOG_EVERY = 2.0
RETRY_SECONDS = 5.0

# The events that change what a level lists. A health check's own exec is an
# event every few seconds and changes nothing a level shows.
_CHANGES: dict[str, frozenset[str]] = {
    "container": frozenset(
        {
            "create",
            "start",
            "stop",
            "die",
            "destroy",
            "pause",
            "unpause",
            "rename",
            "restart",
            "update",
        }
    ),
    "image": frozenset({"pull", "tag", "untag", "delete", "import", "load", "save"}),
    "volume": frozenset({"create", "destroy"}),
    "network": frozenset({"create", "destroy", "connect", "disconnect"}),
}
_GROUP_OF = {
    "container": "containers",
    "image": "images",
    "volume": "volumes",
    "network": "networks",
}


def changed_by(event: dict[str, object], shown: frozenset[str | None]) -> Changed | None:
    """The levels one event asks to read again, of those shown, or none."""
    kind = str(event.get("Type") or "")
    action = str(event.get("Action") or "")
    # A health check's result changes a container's one word (D407).
    if action.startswith("health_status"):
        action = "update"
    if action not in _CHANGES.get(kind, frozenset()):
        return None
    group = _GROUP_OF[kind]
    levels: set[str | None] = {group}
    if kind == "container":
        actor = event.get("Actor")
        attributes = actor.get("Attributes") if isinstance(actor, dict) else None
        project = (
            str(attributes.get(COMPOSE_PROJECT, ""))
            if isinstance(attributes, dict)
            else ""
        )
        levels.add(project_id(project))
    told = frozenset(levels) & shown
    return Changed(levels=told) if told else None


# A container's view shows its networks, so connecting one tells it too; an
# image's and a volume's list their containers' states, so any change to a
# container tells every one of them shown.
_VOLUME_USES = frozenset({"mount", "unmount"})

type Viewed = dict[str, tuple[str, str]]


def views_told(event: dict[str, object], viewed: Viewed) -> frozenset[str]:
    """The open views (D422) one event asks to read again."""
    kind = str(event.get("Type") or "")
    action = str(event.get("Action") or "")
    if action.startswith("health_status"):
        action = "update"
    actor = event.get("Actor")
    actor_id = str(actor.get("ID") or "") if isinstance(actor, dict) else ""
    attributes = actor.get("Attributes") if isinstance(actor, dict) else None
    # Which views: a leaf and its key, or a leaf and None for every one of it.
    wanted: set[tuple[str, str | None]] = set()
    if kind == "container" and action in _CHANGES["container"]:
        wanted |= {("container", actor_id), ("image", None), ("volume", None)}
    elif kind == "image" and action in _CHANGES["image"]:
        # A pull names the reference, not the id it lands on.
        wanted.add(("image", actor_id if actor_id.startswith("sha256:") else None))
    elif kind == "volume" and action in _CHANGES["volume"] | _VOLUME_USES:
        wanted.add(("volume", actor_id))
    elif kind == "network" and action in _CHANGES["network"]:
        wanted.add(("network", actor_id))
        container = attributes.get("container") if isinstance(attributes, dict) else None
        if container:
            wanted.add(("container", str(container)))
    return frozenset(
        node
        for node, (leaf, key) in viewed.items()
        if (leaf, key) in wanted or (leaf, None) in wanted
    )


class DockerWatch:
    """The streams one screen asked for on one connection."""

    def __init__(self, session: DockerSession, sink: ChangeSink) -> None:
        self._session = session
        self._sink = sink
        self._logs: dict[str, asyncio.Task[None]] = {}
        self._events: asyncio.Task[None] | None = None
        self._shown: frozenset[str | None] = frozenset()
        self._viewed: Viewed = {}

    async def follow(self, node_ids: Sequence[str | None]) -> None:
        logs: set[str] = set()
        levels: set[str | None] = set()
        viewed: Viewed = {}
        for node_id in node_ids:
            if node_id is None:
                levels.add(None)
                continue
            try:
                named = parse(node_id)
            except ValueError:
                # The System section and its reports: nothing streams them.
                continue
            if named.leaf == "container" and named.view == "logs":
                logs.add(named.key)
            elif named.view is None:
                levels.add(node_id)
            if named.leaf is not None and named.view in (None, "inspect"):
                # A node opened on its view, or its Inspect: the same view.
                viewed[node_id] = (named.leaf, named.key)
        for key in set(self._logs) - logs:
            self._logs.pop(key).cancel()
        for key in logs - set(self._logs):
            self._logs[key] = asyncio.create_task(self._log(key))
        self._shown = frozenset(levels)
        self._viewed = viewed
        watched = bool(levels) or bool(viewed)
        if watched and self._events is None:
            self._events = asyncio.create_task(self._watch_events())
        elif not watched and self._events is not None:
            self._events.cancel()
            self._events = None

    async def close(self) -> None:
        tasks = list(self._logs.values())
        if self._events is not None:
            tasks.append(self._events)
        self._logs.clear()
        self._events = None
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _streamed(
        self, path: str, params: dict[str, str], on_chunk: Callable[[bytes], None]
    ) -> None:
        """One stream read to its end, again and again, until cancelled."""
        while True:
            try:
                engine = await self._session.engine()
                async with engine.stream("GET", path, params=params, seconds=None) as response:
                    async for chunk in response.aiter_bytes():
                        on_chunk(chunk)
            except EngineRefused as refused:
                if refused.status == 404:
                    return
            except (EngineUnreachable, AdapterError, OSError) as failure:
                logger.info("A Docker stream dropped: %r", failure)
            await asyncio.sleep(RETRY_SECONDS)

    async def _log(self, key: str) -> None:
        node = view_id("container", key, "logs")
        told_at = 0.0
        pending: asyncio.TimerHandle | None = None
        loop = asyncio.get_running_loop()

        def tell() -> None:
            nonlocal told_at, pending
            pending = None
            told_at = time.monotonic()
            self._sink(Changed(nodes=frozenset({node})))

        def on_chunk(chunk: bytes) -> None:
            nonlocal pending
            if not chunk or pending is not None:
                return
            wait = told_at + LOG_EVERY - time.monotonic()
            if wait <= 0:
                tell()
            else:
                pending = loop.call_later(wait, tell)

        try:
            await self._streamed(
                f"/containers/{segment(key)}/logs",
                # From now: what was there is on screen already.
                {"follow": "true", "stdout": "true", "stderr": "true", "tail": "0"},
                on_chunk,
            )
        finally:
            if pending is not None:
                pending.cancel()

    async def _watch_events(self) -> None:
        buffered = b""

        def on_chunk(chunk: bytes) -> None:
            nonlocal buffered
            buffered += chunk
            *lines, buffered = buffered.split(b"\n")
            for line in lines:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    told = changed_by(event, self._shown)
                    views = views_told(event, self._viewed)
                    if told is not None or views:
                        self._sink(
                            Changed(
                                levels=told.levels if told is not None else frozenset(),
                                nodes=views,
                            )
                        )

        await self._streamed("/events", {}, on_chunk)

