"""What runs a source's client program as a terminal, as the socket sees it (D286).

A protocol rather than the container runtime itself: the runtime belongs to
`app.services`, which sits above this package, so the application hands its
engine in at start-up and the socket asks it through this.
"""

import uuid
from typing import Protocol, runtime_checkable

from app.adapters.terminal import ConsoleProgram, Terminal, TerminalSize


class ConsoleRefused(Exception):
    """The program could not be started; the message is safe to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@runtime_checkable
class ConsoleRunner(Protocol):
    async def open_console(
        self, program: ConsoleProgram, size: TerminalSize, *, owner: uuid.UUID
    ) -> Terminal:
        """The program, running with the terminal as its screen.

        Raises `ConsoleRefused` when it cannot be run here.
        """
        ...
