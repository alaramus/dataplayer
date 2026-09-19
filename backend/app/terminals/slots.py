"""How many terminals each person holds open (D149)."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

# Enough for a person to work in several at once; each is a signed-in
# connection to somebody's server and a shell running there.
MAX_TERMINALS_PER_USER = 8


class TooManyTerminals(Exception):
    pass


class TerminalSlots:
    """Counted in this process, which is correct because there is one (D124).

    Not a lock: the event loop is the only thread that counts, and nothing is
    awaited between looking at a count and changing it.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._held: dict[uuid.UUID, int] = {}

    def held_by(self, user_id: uuid.UUID) -> int:
        return self._held.get(user_id, 0)

    @contextmanager
    def taken(self, user_id: uuid.UUID) -> Iterator[None]:
        """One slot for as long as the block runs, or `TooManyTerminals`."""
        held = self.held_by(user_id)
        if held >= self.limit:
            raise TooManyTerminals
        self._held[user_id] = held + 1
        try:
            yield
        finally:
            remaining = self._held[user_id] - 1
            if remaining == 0:
                del self._held[user_id]
            else:
                self._held[user_id] = remaining


SLOTS = TerminalSlots(MAX_TERMINALS_PER_USER)
