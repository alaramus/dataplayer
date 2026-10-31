"""A source that says when what is on screen has changed (D303).

The screen names the nodes it shows; the source watches those and says which
levels and which nodes to read again. A source that cannot is read again by
hand, as every source was before.

The capability holds a connection open for as long as somebody looks, unlike
every other one here, so it is opened and closed by whoever subscribed rather
than per request.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Changed:
    """What to read again: levels whose children changed, and nodes that did.

    None among the levels is the top of the connection.
    """

    levels: frozenset[str | None] = frozenset()
    nodes: frozenset[str] = frozenset()


# Called from whatever thread the source's driver tells it on, never awaited:
# whoever passes it in moves the news onto its own loop.
type ChangeSink = Callable[[Changed], None]


class ChangeWatch(Protocol):
    """The watches one subscriber's screen asked for on one connection."""

    async def follow(self, node_ids: Sequence[str | None]) -> None:
        """Watch exactly these from now on: the ones left out stop."""
        ...

    async def close(self) -> None: ...


@runtime_checkable
class SupportsChangeWatch(Protocol):
    async def watch_changes(self, sink: ChangeSink) -> ChangeWatch:
        """An open watch that tells `sink`; raises AdapterError when it cannot open."""
        ...
