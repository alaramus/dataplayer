"""A client program run in a container whose terminal is a person's (D286).

The container is made with a TTY and an open stdin, attached before it starts
so not a byte of its first screen is lost, and removed when the terminal
closes. The attach is the Engine API's own: an HTTP request the daemon
upgrades to a raw stream, which with a TTY carries the program's bytes as they
are both ways. httpx has no way to hand over a connection it upgraded, so the
request is written here on a socket of its own.
"""

import asyncio
import logging
import sys
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from app.adapters.terminal import ConsoleProgram, TerminalSize
from app.core.config import settings
from app.core.translation import say
from app.services.plan import OWNER_LABEL, TOOL_LABEL
from app.terminals.consoles import ConsoleRefused

logger = logging.getLogger(__name__)

# What the label on a console's container says it is, beside the owner.
CONSOLE_TOOL = "console"

# How long the daemon may take to answer the attach before the console is
# given up as not starting.
ATTACH_SECONDS = 30.0
# How long a program that has stopped printing may take to say how it ended.
EXIT_SECONDS = 5.0

type Connect = Callable[[], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]
type Request = Callable[..., Awaitable[Any]]


async def unix_connection(path: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """A socket of its own to the daemon, for the one request httpx cannot make."""
    if sys.platform == "win32":
        # The backend runs in a Linux container (AGENTS.md); Windows has no
        # Unix socket to the daemon.
        raise ConsoleRefused(say("This server cannot reach a container runtime"))
    return await asyncio.open_unix_connection(path)


def console_body(program: ConsoleProgram, labels: Mapping[str, str]) -> dict[str, Any]:
    """The container, as the Engine API wants it written.

    The limits a service is held to (D86), no restart, and removed by the
    daemon once the program ends, so a server that went away mid-session
    leaves nothing behind.
    """
    body: dict[str, Any] = {
        "Image": program.image,
        "Cmd": list(program.argv),
        "Env": [f"{key}={value}" for key, value in sorted(program.environment.items())],
        "Labels": dict(labels),
        "Tty": True,
        "OpenStdin": True,
        # Stdin closes when the attach does: a program reading it ends.
        "StdinOnce": True,
        "AttachStdin": True,
        "AttachStdout": True,
        "AttachStderr": True,
        "HostConfig": {
            "AutoRemove": True,
            "Memory": settings.SERVICE_MEMORY_MB * 1024 * 1024,
            "NanoCpus": int(settings.SERVICE_CPUS * 1_000_000_000),
            "PidsLimit": settings.SERVICE_PIDS_LIMIT,
        },
    }
    if settings.SERVICE_NETWORK:
        body["NetworkingConfig"] = {"EndpointsConfig": {settings.SERVICE_NETWORK: {}}}
    return body


def attach_request(container: str) -> bytes:
    return (
        f"POST /containers/{container}/attach?stream=1&stdin=1&stdout=1&stderr=1 HTTP/1.1\r\n"
        "Host: docker\r\n"
        "Upgrade: tcp\r\n"
        "Connection: Upgrade\r\n"
        "Content-Length: 0\r\n"
        "\r\n"
    ).encode()


async def upgraded(reader: asyncio.StreamReader) -> None:
    """Read the daemon's answer to the attach up to where the stream begins."""
    async with asyncio.timeout(ATTACH_SECONDS):
        head = await reader.readuntil(b"\r\n\r\n")
    status = head.split(b"\r\n", 1)[0].split(b" ")
    code = int(status[1]) if len(status) > 1 and status[1].isdigit() else 0
    # 101 from a daemon that honours the upgrade; 200 from an old one that
    # hijacks the connection without saying so.
    if code not in (101, 200):
        logger.warning("Docker refused to attach a console: %s", head[:200])
        raise ConsoleRefused(say("The console could not be attached"))


class DockerConsole:
    """One program in one container, as a terminal (D149's `Terminal`)."""

    def __init__(
        self,
        container: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        request: Request,
    ) -> None:
        self._container = container
        self._reader = reader
        self._writer = writer
        self._request = request
        self._resizes: set[asyncio.Task[None]] = set()
        self._closed = False

    async def read(self) -> bytes:
        try:
            return await self._reader.read(64 * 1024)
        except (ConnectionError, OSError):
            return b""

    async def write(self, data: bytes) -> None:
        self._writer.write(data)
        await self._writer.drain()

    def resize(self, size: TerminalSize) -> None:
        task = asyncio.create_task(self.resized(size))
        self._resizes.add(task)
        task.add_done_callback(self._resizes.discard)

    async def resized(self, size: TerminalSize) -> None:
        try:
            await self._request(
                "POST",
                f"/containers/{self._container}/resize",
                params={"h": str(size.rows), "w": str(size.cols)},
                expected=(200, 201, 404, 409),
            )
        except Exception as failure:
            # A window that did not change size is not worth ending a console.
            logger.info("A console could not be resized: %r", failure)

    async def exit_status(self) -> int | None:
        try:
            async with asyncio.timeout(EXIT_SECONDS):
                answer = await self._request(
                    "POST", f"/containers/{self._container}/wait", expected=(200,)
                )
        except Exception:
            # Removed already, by the daemon once it ended.
            return None
        code = answer.json().get("StatusCode") if answer.json() else None
        return int(code) if isinstance(code, int) else None

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for task in list(self._resizes):
            task.cancel()
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except (ConnectionError, OSError):
            pass
        try:
            await self._request(
                "DELETE",
                f"/containers/{self._container}",
                params={"force": "true"},
                expected=(204, 404, 409),
            )
        except Exception as failure:
            logger.warning("A console's container was not removed: %r", failure)


async def open_console(
    program: ConsoleProgram,
    size: TerminalSize,
    *,
    owner: uuid.UUID,
    request: Request,
    has_image: Callable[[str], Awaitable[bool]],
    pull: Callable[[str], Awaitable[None]],
    connect: Connect,
) -> DockerConsole:
    """Make, attach and start the container; remove it if any step fails."""
    if not await has_image(program.image):
        await pull(program.image)
    container = f"dataplayer-console-{uuid.uuid4().hex[:12]}"
    labels = {TOOL_LABEL: CONSOLE_TOOL, OWNER_LABEL: str(owner)}
    await request(
        "POST",
        "/containers/create",
        params={"name": container},
        json=console_body(program, labels),
        expected=(201,),
    )
    writer: asyncio.StreamWriter | None = None
    try:
        reader, writer = await connect()
        writer.write(attach_request(container))
        await writer.drain()
        await upgraded(reader)
        await request("POST", f"/containers/{container}/start", expected=(204, 304))
        console = DockerConsole(container, reader, writer, request)
        await console.resized(size)
        return console
    except BaseException:
        if writer is not None:
            writer.close()
        try:
            await request(
                "DELETE", f"/containers/{container}", params={"force": "true"}, expected=(204, 404)
            )
        except Exception as failure:
            logger.warning("A console's container was not removed: %r", failure)
        raise
