"""Where something that must outlive a request is kept.

An adapter is built for one request and cannot hold a connection pool: it is
gone before the next one arrives. A module-level dictionary inside a driver
would survive, but then the application reaches for it instead of being handed
it, and closing it at shutdown would make application assembly name one driver
by hand.

So the container is here, knows nothing about connections, and is created and
closed by the application. What it holds — a pool, with all its settings and
semantics — belongs to the driver that has one. That split is what sub-project
6 settled: a file source has no connection at all, so pooling cannot be a layer
above every adapter.
"""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated, Protocol, runtime_checkable

from fastapi import Depends, Request


@runtime_checkable
class Closeable(Protocol):
    async def close(self) -> None: ...


@dataclass
class _Entry:
    value: Closeable
    used_at: float = field(default_factory=time.monotonic)


class ResourceStore:
    """Long-lived objects, addressed by a key their owner composes."""

    def __init__(self, *, max_entries: int, max_idle_seconds: float) -> None:
        self._max_entries = max_entries
        self._max_idle_seconds = max_idle_seconds
        self._entries: dict[str, _Entry] = {}
        # One lock for the whole store rather than one per key: creating an
        # entry does not talk to anything remote — a pool with min_size 0
        # connects on first use — so the section is short.
        self._lock = asyncio.Lock()

    async def get_or_create[T: Closeable](
        self, key: str, kind: type[T], create: Callable[[], Awaitable[T]]
    ) -> T:
        """The object under this key, made by `create` if it is not there.

        `kind` narrows the stored value back to what the caller expects
        without a cast, and turns "keys of different drivers never collide"
        from an assumption into a check.
        """
        async with self._lock:
            await self._drop_idle()
            entry = self._entries.get(key)
            if entry is not None:
                if not isinstance(entry.value, kind):
                    raise TypeError(
                        f"Resource {key} is a {type(entry.value).__name__}, "
                        f"not a {kind.__name__}"
                    )
                entry.used_at = time.monotonic()
                return entry.value

            value = await create()
            self._entries[key] = _Entry(value)
            await self._drop_overflow()
            return value

    async def aclose(self) -> None:
        async with self._lock:
            entries, self._entries = self._entries, {}
        for entry in entries.values():
            await entry.value.close()

    async def size(self) -> int:
        async with self._lock:
            return len(self._entries)

    async def _drop_idle(self) -> None:
        deadline = time.monotonic() - self._max_idle_seconds
        for key in [
            key for key, entry in self._entries.items() if entry.used_at < deadline
        ]:
            await self._entries.pop(key).value.close()

    async def _drop_overflow(self) -> None:
        while len(self._entries) > self._max_entries:
            oldest = min(self._entries, key=lambda key: self._entries[key].used_at)
            await self._entries.pop(oldest).value.close()


@dataclass(frozen=True)
class Pooling:
    """Where a stored connector may keep what outlives its request.

    One field rather than two on AdapterContext: a store without the identity
    of a connector cannot compose a key, and an identity without a store has
    nowhere to put anything, so the two cannot be allowed to disagree. Absent
    for a draft — it has no identity to key anything by.
    """

    store: ResourceStore
    connector_id: uuid.UUID


def get_resources(request: Request) -> ResourceStore:
    """The store the application created at startup.

    Reached through the application rather than through a module global, so
    there is exactly one of it and a test can run against its own.
    """
    store = request.app.state.resources
    if not isinstance(store, ResourceStore):
        raise RuntimeError("The application was started without a resource store")
    return store


ResourcesDep = Annotated[ResourceStore, Depends(get_resources)]
