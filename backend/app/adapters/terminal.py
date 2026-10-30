"""A shell on the machine a source runs on, driven a keystroke at a time (D149).

The capability says nothing about sockets: a driver hands back a stream of
bytes each way and a size it can be told about, and `app.terminals` carries
that to a browser. Which shell, which machine and how it is signed in to is the
driver's alone.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

# Wider and taller than any screen draws, so a real window is never refused,
# and small enough that a client cannot ask the far side for a terminal of a
# million cells.
MAX_COLUMNS = 1000
MAX_ROWS = 500


class TerminalSize(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cols: int = Field(ge=1, le=MAX_COLUMNS)
    rows: int = Field(ge=1, le=MAX_ROWS)


class Terminal(Protocol):
    """One running shell. Closed by whoever opened it, whatever happened."""

    async def read(self) -> bytes:
        """What the shell printed since the last read; empty once it has ended."""
        ...

    async def write(self, data: bytes) -> None:
        """Keystrokes, as the terminal on the other side sent them."""
        ...

    def resize(self, size: TerminalSize) -> None: ...

    async def exit_status(self) -> int | None:
        """How the shell ended, asked once `read` has come back empty.

        None when the far side never said. A server may report the status a
        moment after the output ends, so this may wait that moment.
        """
        ...

    async def close(self) -> None: ...


@runtime_checkable
class SupportsTerminal(Protocol):
    async def open_terminal(self, size: TerminalSize) -> Terminal:
        """A shell of the account this source signs in as, already running.

        Raises `AdapterError` when it cannot be had, in the same words the rest
        of the source uses: a locked key, a server key that does not match.
        """
        ...


@dataclass(frozen=True)
class ConsoleProgram:
    """A program whose screen is the terminal, run in a container of its own (D286).

    For a source whose shell is a client program rather than a login: the
    driver says what to run and the server runs it, as a backup is run (D87).
    The password is in the environment, never in the arguments.
    """

    image: str
    argv: tuple[str, ...]
    environment: Mapping[str, str]

    def __repr__(self) -> str:
        keys = ", ".join(sorted(self.environment))
        return f"ConsoleProgram(image={self.image!r}, argv={self.argv!r}, environment keys: {keys})"


@runtime_checkable
class SupportsConsoleProgram(Protocol):
    async def console_program(self) -> ConsoleProgram:
        """The client program that is this source's terminal.

        Raises `AdapterError` when the program could not reach the source from
        a container: through an SSH tunnel, for one.
        """
        ...
