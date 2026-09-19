"""Passphrases somebody typed lately, held in this process and nowhere else (D147).

A key whose owner chose to be asked keeps no passphrase in the database, so
what opens it after a person unlocked it has to live somewhere, for a while.
Here: in memory, for fifteen minutes, an hour or eight hours, and gone when
the process ends — a restarted server knows no passphrase at all, which is the
property the choice was for.

One instance for the process, reached as `KEYRING`, and a known deviation
from "dependencies are passed in" (ENGINEERING.md): every place a source is
built needs it — the routes, the health monitor, the agent's tools — and the
health monitor is made by a topic factory that takes nothing. It holds no
connection and runs no task, and the backend is one process (D124), so the
module is the process.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.schemas import get_datetime_utc


@dataclass(frozen=True)
class _Unlocked:
    passphrase: str
    deadline: float
    until: datetime

    def __repr__(self) -> str:
        return f"_Unlocked(until={self.until.isoformat()})"


class Keyring:
    """Which keys are open, with what, and until when.

    The deadline is kept on the monotonic clock, so moving the system clock
    cannot keep a key open; the wall-clock time beside it is only what a
    screen shows.
    """

    def __init__(self) -> None:
        self._open: dict[uuid.UUID, _Unlocked] = {}

    def unlock(self, key_id: uuid.UUID, passphrase: str, *, seconds: int) -> datetime:
        until = get_datetime_utc() + timedelta(seconds=seconds)
        self._open[key_id] = _Unlocked(
            passphrase=passphrase,
            deadline=time.monotonic() + seconds,
            until=until,
        )
        return until

    def passphrase(self, key_id: uuid.UUID) -> str | None:
        found = self._current(key_id)
        return None if found is None else found.passphrase

    def until(self, key_id: uuid.UUID) -> datetime | None:
        found = self._current(key_id)
        return None if found is None else found.until

    def lock(self, key_id: uuid.UUID) -> None:
        self._open.pop(key_id, None)

    def clear(self) -> None:
        self._open.clear()

    def _current(self, key_id: uuid.UUID) -> _Unlocked | None:
        found = self._open.get(key_id)
        if found is not None and found.deadline <= time.monotonic():
            del self._open[key_id]
            return None
        return found


KEYRING = Keyring()
