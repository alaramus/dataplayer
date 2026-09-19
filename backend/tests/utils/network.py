import asyncio
import socket
import struct
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field


@contextmanager
def silent_endpoint() -> Iterator[int]:
    """A port that accepts the connection and then says nothing.

    A closed port cannot stand in for an unreachable server: Linux refuses it
    at once and Windows leaves the client waiting, so a test written against
    one of them asserts about the platform rather than about the adapter. This
    listens without ever accepting, so the kernel completes the handshake from
    the backlog and the client waits for a greeting that never comes — the same
    everywhere, and the timeout budget is what ends it.
    """
    server = socket.socket()
    try:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port: int = server.getsockname()[1]
        yield port
    finally:
        server.close()


_SSL_REQUEST = 80877103
_GSSENC_REQUEST = 80877104
_AUTH_CLEARTEXT_PASSWORD = 3


@dataclass
class PasswordTrap:
    """What a hostile PostgreSQL server was sent, and how often it was reached."""

    port: int = 0
    connections: int = 0
    passwords: list[str] = field(default_factory=list)


@asynccontextmanager
async def password_trap() -> AsyncIterator[PasswordTrap]:
    """A host that speaks PostgreSQL just long enough to be sent a password.

    It asks for the password in clear text, which any server may do and libpq
    obeys, so a connection pointed here hands over whatever password it holds.
    Connections are counted too, so a test can say nothing arrived at all
    rather than only that nothing useful did.

    Served on the running loop, which is the one the ASGI client runs the
    application on, so the driver reaches it within the same request.
    """
    trap = PasswordTrap()

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        trap.connections += 1
        try:
            while True:
                (length,) = struct.unpack("!i", await reader.readexactly(4))
                body = await reader.readexactly(length - 4)
                (code,) = struct.unpack("!i", body[:4])
                if code not in (_SSL_REQUEST, _GSSENC_REQUEST):
                    break
                # Neither encryption is offered, so the password comes in clear.
                writer.write(b"N")
                await writer.drain()
            writer.write(b"R" + struct.pack("!ii", 8, _AUTH_CLEARTEXT_PASSWORD))
            await writer.drain()
            kind = await reader.readexactly(1)
            (length,) = struct.unpack("!i", await reader.readexactly(4))
            body = await reader.readexactly(length - 4)
            if kind == b"p":
                trap.passwords.append(body.rstrip(b"\0").decode())
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    trap.port = server.sockets[0].getsockname()[1]
    try:
        yield trap
    finally:
        server.close()
        await server.wait_closed()
