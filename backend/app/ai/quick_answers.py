"""The quick-chat answers this process is writing, so Stop can reach one (D158).

Process-local, like the agent's runs and for the same reason: a task does not
cross a process, and there is one (D124).
"""

import asyncio
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class Writing:
    task: asyncio.Task[None]
    owner_id: uuid.UUID
    # Stop was pressed. A task cancelled without it is the request going away.
    stopped: bool = False


class QuickAnswers:
    def __init__(self) -> None:
        self._writing: dict[uuid.UUID, Writing] = {}

    @contextmanager
    def writing(
        self, chat_id: uuid.UUID, owner_id: uuid.UUID, task: asyncio.Task[None]
    ) -> Iterator[Writing]:
        entry = Writing(task=task, owner_id=owner_id)
        self._writing[chat_id] = entry
        try:
            yield entry
        finally:
            if self._writing.get(chat_id) is entry:
                del self._writing[chat_id]

    def writes(self, chat_id: uuid.UUID) -> bool:
        return chat_id in self._writing

    def stop(self, chat_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        """Stop the answer being written in this chat. False if none is."""
        entry = self._writing.get(chat_id)
        if entry is None or entry.owner_id != owner_id:
            return False
        entry.stopped = True
        entry.task.cancel()
        return True
