"""Where a captured result lives while somebody reads it.

D64: one bounded materialisation, then an opaque id. Keeping a cursor would
hold a transaction and a pooled connection for as long as a person looks at the
first page, and re-running for page two would answer from a different snapshot.

This store is deliberately process-local, and that is a stated boundary rather
than an oversight: phase 5 may put a shared one behind the same three methods.
Nothing here reaches a database, so a result that is gone is gone, and the run
that produced it — which is durable — says so.
"""

import asyncio
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request

from app.adapters.query import MaterialisedResult


@dataclass
class _Held:
    result: MaterialisedResult
    owner_id: uuid.UUID
    run_id: uuid.UUID
    bytes_used: int
    used_at: float
    # An active run's results are never evicted: they are the outputs of
    # something still happening, and losing one would be losing part of an
    # answer already given.
    active: bool = field(default=True)


class QueryResults:
    """Captured results, bounded by bytes and by how long ago each was read."""

    def __init__(
        self,
        *,
        max_bytes: int,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_bytes = max_bytes
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._held: dict[str, _Held] = {}
        self._lock = asyncio.Lock()

    async def put(
        self, *, owner_id: uuid.UUID, run_id: uuid.UUID, result: MaterialisedResult
    ) -> str | None:
        """Keep one result and answer with its id, or nothing.

        Nothing when it does not fit even after everything evictable has gone:
        the statement still succeeded, and its result could not be published.
        The two are different facts and the caller reports them separately.
        """
        size = max(result.bytes_used, 1)
        if size > self._max_bytes:
            return None
        result_id = secrets.token_urlsafe(24)
        async with self._lock:
            now = self._clock()
            self._expire(now)
            self._make_room(size, now)
            if self._used() + size > self._max_bytes:
                return None
            self._held[result_id] = _Held(
                result=result,
                owner_id=owner_id,
                run_id=run_id,
                bytes_used=size,
                used_at=now,
            )
        return result_id

    async def get(self, result_id: str, *, owner_id: uuid.UUID) -> MaterialisedResult | None:
        """One result, if it is still here and belongs to this caller.

        Ownership is checked here rather than by the route comparing ids: an
        opaque id is not an authorisation, and a result belonging to somebody
        else is indistinguishable from one that expired.
        """
        async with self._lock:
            held = self._held.get(result_id)
            if held is None or held.owner_id != owner_id:
                return None
            now = self._clock()
            if not held.active and now - held.used_at > self._ttl_seconds:
                del self._held[result_id]
                return None
            held.used_at = now
            return held.result

    async def release(self, run_id: uuid.UUID) -> None:
        """This run has finished; its results may now be evicted like any other."""
        async with self._lock:
            for held in self._held.values():
                if held.run_id == run_id:
                    held.active = False

    async def forget(self, run_id: uuid.UUID) -> None:
        async with self._lock:
            for result_id in [
                key for key, held in self._held.items() if held.run_id == run_id
            ]:
                del self._held[result_id]

    async def aclose(self) -> None:
        async with self._lock:
            self._held.clear()

    def _used(self) -> int:
        return sum(held.bytes_used for held in self._held.values())

    def _expire(self, now: float) -> None:
        for result_id in [
            key
            for key, held in self._held.items()
            if not held.active and now - held.used_at > self._ttl_seconds
        ]:
            del self._held[result_id]

    def _make_room(self, wanted: int, now: float) -> None:
        """Evict the least recently read terminal results, and only those."""
        evictable = sorted(
            (held for held in self._held.values() if not held.active),
            key=lambda held: held.used_at,
        )
        for held in evictable:
            if self._used() + wanted <= self._max_bytes:
                return
            for result_id, candidate in list(self._held.items()):
                if candidate is held:
                    del self._held[result_id]
                    break


def get_results(request: Request) -> QueryResults:
    """The store of the running application, for a route that reads one.

    Through the application rather than a module global, for the reason a pool
    is: what outlives a request belongs to the application (D10).
    """
    results = request.app.state.query_results
    if not isinstance(results, QueryResults):
        raise RuntimeError("The application has no result store; is the lifespan running?")
    return results


ResultsDep = Annotated[QueryResults, Depends(get_results)]
