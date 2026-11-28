"""A container's logs told while somebody looks (D473, on D303 and D414).

An open Logs page is one `follow=true&tailLines=0` stream of the container's
log from now; anything on it tells that page to read again, at most once
every `LOG_EVERY` seconds, so a container printing a thousand lines a second
costs one refresh every two. A stream that drops is opened again after
`RETRY_SECONDS`; a pod that is gone ends it.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import Sequence

import httpx

from app.adapters.changes import Changed, ChangeSink
from app.adapters.kubernetes.catalog import parse
from app.adapters.kubernetes.session import KubernetesSession, segment
from app.adapters.protocol import AdapterError

logger = logging.getLogger(__name__)

LOG_EVERY = 2.0
RETRY_SECONDS = 5.0


def logs_followed(node_ids: Sequence[str | None]) -> dict[str, tuple[str, str, str]]:
    """The Logs pages among `node_ids`: namespace, pod and container by node."""
    found: dict[str, tuple[str, str, str]] = {}
    for node_id in node_ids:
        if node_id is None:
            continue
        try:
            named = parse(node_id)
        except ValueError:
            continue
        if (
            named.view == "logs"
            and named.resource == "pods"
            and named.group == ""
            and named.namespace
            and named.name
            and named.container
        ):
            found[node_id] = (named.namespace, named.name, named.container)
    return found


class KubernetesWatch:
    """The log streams one screen asked for on one connection."""

    def __init__(self, session: KubernetesSession, sink: ChangeSink) -> None:
        self._session = session
        self._sink = sink
        self._logs: dict[str, asyncio.Task[None]] = {}

    async def follow(self, node_ids: Sequence[str | None]) -> None:
        wanted = logs_followed(node_ids)
        for node in set(self._logs) - set(wanted):
            self._logs.pop(node).cancel()
        for node in set(wanted) - set(self._logs):
            self._logs[node] = asyncio.create_task(self._log(node, *wanted[node]))

    async def close(self) -> None:
        tasks = list(self._logs.values())
        self._logs.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def _log(self, node: str, namespace: str, pod: str, container: str) -> None:
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

        path = f"/api/v1/namespaces/{segment(namespace)}/pods/{segment(pod)}/log"
        # From now: what was there is on screen already.
        params = {"container": container, "follow": "true", "tailLines": "0"}
        try:
            while True:
                try:
                    client = await self._session.client()
                    async with client.stream("GET", path, params=params, timeout=httpx.Timeout(20.0, read=None)) as answer:
                        if answer.status_code == 404:
                            return
                        if answer.status_code == 200:
                            async for chunk in answer.aiter_bytes():
                                on_chunk(chunk)
                        else:
                            logger.info("A Kubernetes log stream was refused: %s", answer.status_code)
                except (AdapterError, httpx.HTTPError, OSError) as failure:
                    logger.info("A Kubernetes log stream dropped: %r", type(failure).__name__)
                await asyncio.sleep(RETRY_SECONDS)
        finally:
            if pending is not None:
                pending.cancel()
