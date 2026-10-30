"""A client program in a container, attached as a terminal (D286).

The daemon is played by a request function that records what it is asked and
a socket server that answers the attach the way the Engine API does.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest

from app.adapters.terminal import ConsoleProgram, TerminalSize
from app.services.consoles import console_body, open_console
from app.terminals.consoles import ConsoleRefused

PROGRAM = ConsoleProgram(
    image="mongo:8.0",
    argv=("mongosh", "--nodb"),
    environment={"DP_MONGODB_URI": "mongodb://u:secret@h/"},
)


@dataclass
class _Answer:
    status: int
    body: bytes = b""

    def json(self) -> Any:
        return json.loads(self.body) if self.body else None


class _Daemon:
    def __init__(self, *, has_image: bool = True) -> None:
        self.asked: list[tuple[str, str]] = []
        self.bodies: list[Any] = []
        self.pulled: list[str] = []
        self._has_image = has_image

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Any = None,
        json: Any = None,
        expected: tuple[int, ...],
    ) -> _Answer:
        self.asked.append((method, path.split("?")[0]))
        if json is not None:
            self.bodies.append(json)
        if path.endswith("/wait"):
            return _Answer(200, b'{"StatusCode": 3}')
        return _Answer(expected[0])

    async def has_image(self, image: str) -> bool:
        return self._has_image

    async def pull(self, image: str) -> None:
        self.pulled.append(image)


async def _attach_server(answer: bytes) -> AsyncIterator[tuple[str, int]]:
    """A socket that answers the attach, then echoes what it is sent."""

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(answer)
        await writer.drain()
        while data := await reader.read(1024):
            writer.write(data.upper())
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    address = server.sockets[0].getsockname()
    try:
        yield address[0], address[1]
    finally:
        server.close()
        await server.wait_closed()


@pytest.fixture
async def upgrading() -> AsyncIterator[tuple[str, int]]:
    async for address in _attach_server(
        b"HTTP/1.1 101 UPGRADED\r\nConnection: Upgrade\r\nUpgrade: tcp\r\n\r\n"
    ):
        yield address


@pytest.fixture
async def refusing() -> AsyncIterator[tuple[str, int]]:
    async for address in _attach_server(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"):
        yield address


def test_the_container_has_a_terminal_and_the_password_only_in_its_environment() -> None:
    body = console_body(PROGRAM, {"dataplayer.tool": "console"})

    assert body["Tty"] and body["OpenStdin"] and body["StdinOnce"]
    assert body["HostConfig"]["AutoRemove"]
    assert "secret" not in json.dumps(body["Cmd"])
    assert body["Env"] == ["DP_MONGODB_URI=mongodb://u:secret@h/"]
    assert "secret" not in repr(PROGRAM)


async def test_the_program_is_made_attached_started_and_typed_into(
    upgrading: tuple[str, int],
) -> None:
    daemon = _Daemon(has_image=False)
    console = await open_console(
        PROGRAM,
        TerminalSize(cols=100, rows=30),
        owner=uuid.uuid4(),
        request=daemon.request,
        has_image=daemon.has_image,
        pull=daemon.pull,
        connect=lambda: asyncio.open_connection(*upgrading),
    )
    try:
        await console.write(b"show dbs\n")
        assert await console.read() == b"SHOW DBS\n"
        assert await console.exit_status() == 3
    finally:
        await console.close()

    assert daemon.pulled == ["mongo:8.0"]
    methods = [method for method, _ in daemon.asked]
    paths = [path.rsplit("/", 1)[-1] for _, path in daemon.asked]
    # Attached before it starts, so its first screen is not lost.
    assert paths[:3] == ["create", "start", "resize"]
    assert (methods[-1], paths[-1].startswith("dataplayer-console-")) == ("DELETE", True)


async def test_a_refused_attach_leaves_no_container(refusing: tuple[str, int]) -> None:
    daemon = _Daemon()

    with pytest.raises(ConsoleRefused):
        await open_console(
            PROGRAM,
            TerminalSize(cols=80, rows=24),
            owner=uuid.uuid4(),
            request=daemon.request,
            has_image=daemon.has_image,
            pull=daemon.pull,
            connect=lambda: asyncio.open_connection(*refusing),
        )

    assert [method for method, _ in daemon.asked] == ["POST", "DELETE"]
