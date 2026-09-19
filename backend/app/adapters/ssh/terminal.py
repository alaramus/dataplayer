"""The login shell of the account a connection signs in as (D149).

A shell on the server with a pseudo-terminal of the size the browser draws —
no program on this machine and no key written to its disk, which is what the
old application ran `ssh` in a local pty for. The connection is the
terminal's own and ends with it.
"""

import asyncio
from typing import Self

import asyncssh

from app.adapters.protocol import AdapterError
from app.adapters.ssh.session import SshSession, reduced
from app.adapters.terminal import TerminalSize

# What the browser's terminal understands, and so what `TERM` is on the far
# side: colours, cursor movement and the alternate screen an editor draws on.
TERM_TYPE = "xterm-256color"

# How much output one read may hand over. More is left for the next read
# rather than refused, so a `cat` of a big file arrives in pieces this size.
_READ_BYTES = 64 * 1024

# How long the end of a shell waits for its exit status.
_STATUS_SECONDS = 2.0


class SshTerminal:
    def __init__(
        self,
        connection: asyncssh.SSHClientConnection,
        process: asyncssh.SSHClientProcess[bytes],
    ) -> None:
        self._connection = connection
        self._process = process

    @classmethod
    async def open(cls, session: SshSession, size: TerminalSize) -> Self:
        connection = await session.signed_in()
        try:
            # Standard error joins standard output, as it does in any
            # terminal: a pty has one screen.
            process: asyncssh.SSHClientProcess[bytes] = await connection.create_process(
                term_type=TERM_TYPE,
                term_size=(size.cols, size.rows),
                stderr=asyncssh.STDOUT,
                encoding=None,
            )
        except BaseException as failure:
            connection.close()
            if isinstance(failure, asyncssh.ChannelOpenError):
                raise AdapterError(
                    "unknown", "The server did not open a shell for this account"
                ) from None
            if isinstance(failure, asyncssh.Error | OSError):
                raise reduced(failure) from None
            raise
        return cls(connection, process)

    async def read(self) -> bytes:
        try:
            return await self._process.stdout.read(_READ_BYTES)
        except (asyncssh.Error, OSError):
            # The connection went rather than the shell ending: to whoever is
            # watching, the terminal is over either way.
            return b""

    async def write(self, data: bytes) -> None:
        if self._process.stdin.is_closing():
            return
        try:
            self._process.stdin.write(data)
            await self._process.stdin.drain()
        except (asyncssh.Error, OSError):
            # Typing into a shell that has just ended; the next read says so.
            return

    def resize(self, size: TerminalSize) -> None:
        try:
            self._process.change_terminal_size(size.cols, size.rows)
        except (asyncssh.Error, OSError):
            return

    async def exit_status(self) -> int | None:
        # OpenSSH may send the end of output before the status, so the channel
        # is given a moment to close; a server that never says is not waited on.
        try:
            async with asyncio.timeout(_STATUS_SECONDS):
                await self._process.wait_closed()
        except TimeoutError:
            pass
        return self._process.exit_status

    async def close(self) -> None:
        self._process.close()
        self._connection.close()
        await self._connection.wait_closed()
