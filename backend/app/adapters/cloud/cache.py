"""Issued secrets kept in this process until shortly before they expire (D449).

Never in the database or the shared cache: a token is a password for fifteen
minutes, and the only copy is here, in memory, keyed by the account, its
version and what was asked. Concurrent asks for the same key share one issue,
so a pool opening ten connections at once asks the cloud once.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable

from app.adapters.cloud import IssuedSecret

# Reissued this long before the cloud stops accepting it: a connection takes a
# moment to open, and a token checked at the last second is refused.
MARGIN_SECONDS = 60.0
# How long a secret that never expires by itself is reused, so a password
# rotated in its store is read again within minutes.
MAX_KEEP_SECONDS = 300.0


class IssueCache:
    """What was issued, by key, while it is still worth handing out."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._kept: dict[Hashable, tuple[IssuedSecret, float]] = {}
        # Only while an issue is running; a task belongs to the loop that made
        # it, and nothing is left here once it is done.
        self._running: dict[Hashable, asyncio.Task[IssuedSecret]] = {}

    async def get(
        self, key: Hashable, issue: Callable[[], Awaitable[IssuedSecret]]
    ) -> IssuedSecret:
        kept = self._kept.get(key)
        if kept is not None and self._clock() < kept[1]:
            return kept[0]
        running = self._running.get(key)
        if running is None:
            running = asyncio.ensure_future(self._issue(key, issue))
            self._running[key] = running
            running.add_done_callback(lambda _: self._running.pop(key, None))
        # Shielded: one caller giving up does not cancel the issue the others
        # wait for.
        return await asyncio.shield(running)

    def forget(self, prefix: Hashable) -> None:
        """Drop everything kept for keys starting with `prefix` (an account)."""
        for key in [one for one in self._kept if isinstance(one, tuple) and one[:1] == (prefix,)]:
            del self._kept[key]

    async def _issue(
        self, key: Hashable, issue: Callable[[], Awaitable[IssuedSecret]]
    ) -> IssuedSecret:
        secret = await issue()
        now = self._clock()
        until = (
            now + MAX_KEEP_SECONDS
            if secret.expires_at is None
            else secret.expires_at - MARGIN_SECONDS
        )
        self._prune(now)
        # One that is about to expire is handed out once and not kept.
        if until > now:
            self._kept[key] = (secret, until)
        return secret

    def _prune(self, now: float) -> None:
        for key in [one for one, (_, until) in self._kept.items() if until <= now]:
            del self._kept[key]
