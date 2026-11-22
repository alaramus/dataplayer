"""A shell inside a container, as its owner's terminal (D413).

`POST /containers/{id}/exec` with a TTY, started over a connection the daemon
upgrades to a raw stream (D406), resized through `/exec/{id}/resize`. The
program is one of a closed list, as argv; it runs as the image's user, or as
root when that is asked for. A shell the image lacks still starts the stream
and the daemon prints its own error (exit 127, *checked*, Engine 29.10); that
line is replaced by a sentence of ours.
"""

import asyncio
import logging
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from app.adapters.actions import Action, ActionRefused, ActsOn
from app.adapters.catalog import NodeKind
from app.adapters.docker.actions import containers_of
from app.adapters.docker.session import DockerSession, segment
from app.adapters.layout import layout
from app.adapters.protocol import AdapterError
from app.adapters.terminal import Terminal, TerminalSize
from app.core.access import Access
from app.core.translation import N_, say

logger = logging.getLogger(__name__)

TERM_TYPE = "xterm-256color"
_READ_BYTES = 64 * 1024
# How long the end of a shell waits for the daemon to know its exit code.
_STATUS_SECONDS = 2.0
# What the daemon prints, as the first thing, when the program is not there.
_NOT_THERE = b"OCI runtime exec failed"

Shell = Literal["/bin/sh", "/bin/bash", "/bin/ash"]


class ShellParams(BaseModel):
    shell: Shell = Field(default="/bin/sh", title=N_("Shell"), json_schema_extra=layout())
    as_root: bool = Field(
        default=False, title=N_("As root, not as the image's user")
    )


class ExecTerminal:
    """One exec's stream: the program's screen both ways, a TTY so one stream."""

    def __init__(
        self,
        session: DockerSession,
        exec_id: str,
        shell: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._session = session
        self._exec_id = exec_id
        self._shell = shell
        self._reader = reader
        self._writer = writer
        self._first = True
        self._resizes: set[asyncio.Task[None]] = set()

    async def read(self) -> bytes:
        try:
            chunk = await self._reader.read(_READ_BYTES)
        except (ConnectionError, OSError):
            return b""
        if self._first and chunk:
            self._first = False
            if chunk.startswith(_NOT_THERE):
                logger.info("A container has no %s: %r", self._shell, chunk[:300])
                return (
                    say(
                        "There is no {shell} in this container; open the terminal again and choose another shell",
                        shell=self._shell,
                    )
                    + "\r\n"
                ).encode()
        return chunk

    async def write(self, data: bytes) -> None:
        if self._writer.is_closing():
            return
        try:
            self._writer.write(data)
            await self._writer.drain()
        except (ConnectionError, OSError):
            return

    def resize(self, size: TerminalSize) -> None:
        task = asyncio.create_task(self.resized(size))
        self._resizes.add(task)
        task.add_done_callback(self._resizes.discard)

    async def resized(self, size: TerminalSize) -> None:
        try:
            # 400 until the program has started, 404 once the exec is gone.
            await self._session.send(
                "POST",
                f"/exec/{segment(self._exec_id)}/resize",
                {"h": str(size.rows), "w": str(size.cols)},
                expected=(200, 201, 400, 404, 409),
            )
        except AdapterError as failure:
            # A window that did not change size is not worth ending a shell.
            logger.info("A container terminal was not resized: %s", failure.message)

    async def exit_status(self) -> int | None:
        try:
            async with asyncio.timeout(_STATUS_SECONDS):
                while True:
                    _, info = await self._session.get(
                        f"/exec/{segment(self._exec_id)}/json", expected=(200, 404)
                    )
                    if not isinstance(info, dict):
                        return None
                    if not info.get("Running"):
                        code = info.get("ExitCode")
                        return code if isinstance(code, int) else None
                    await asyncio.sleep(0.2)
        except (TimeoutError, AdapterError):
            return None

    async def close(self) -> None:
        for task in list(self._resizes):
            task.cancel()
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except (ConnectionError, OSError):
            pass


class ContainerTerminal(Action[ShellParams]):
    """Its form opens a terminal on the container rather than running (D413)."""

    name: ClassVar[str] = "docker_terminal"
    title: ClassVar[str] = N_("Terminal")
    icon: ClassVar[str | None] = "terminal"
    in_view: ClassVar[bool] = True
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"container"})
    acts_on: ClassVar[ActsOn] = "node"
    # Typing into a container is typing into what it can reach: its owner's
    # alone, as a shell on the SSH server is (D149).
    requires: ClassVar[Access] = "own"
    params_model = ShellParams

    def __init__(self, session: DockerSession) -> None:
        self._session = session

    async def open_terminal(
        self, node_id: str | None, raw: Mapping[str, Any], size: TerminalSize
    ) -> Terminal:
        params = self._validated(raw)
        if not (node_id or "").startswith("container:"):
            raise ActionRefused("not_applicable", say("Choose one container"))
        [one] = await containers_of(self._session, node_id)
        if one.get("State") != "running":
            raise ActionRefused(
                "not_applicable", say("The container is not running, so nothing runs in it")
            )
        status, made = await self._session.send(
            "POST",
            f"/containers/{segment(str(one['Id']))}/exec",
            body={
                "AttachStdin": True,
                "AttachStdout": True,
                "AttachStderr": True,
                "Tty": True,
                "Cmd": [params.shell],
                "Env": [f"TERM={TERM_TYPE}"],
                **({"User": "root"} if params.as_root else {}),
            },
            expected=(201, 409),
        )
        if status == 409 or not isinstance(made, dict):
            raise ActionRefused(
                "not_applicable", say("The container is not running, so nothing runs in it")
            )
        exec_id = str(made.get("Id"))
        reader, writer = await self._session.upgraded(
            f"/exec/{segment(exec_id)}/start", {"Detach": False, "Tty": True}
        )
        terminal = ExecTerminal(self._session, exec_id, params.shell, reader, writer)
        terminal.resize(size)
        return terminal
