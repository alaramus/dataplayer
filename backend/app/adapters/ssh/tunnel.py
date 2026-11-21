"""Connections carried through an SSH server to an address it reaches (D282).

The target is a host and port, or a Unix socket on the SSH server itself,
opened as a `direct-streamlocal@openssh.com` channel: a Docker daemon's socket
(D405).

One listener on loopback per SSH connection and target. Every connection a
driver makes to it becomes a channel of one signed-in session, made again when
the server has closed it, so the port a pool was built with keeps working
across a dropped network.

The listener outlives the request that asked for it, and the place that asks
is not always a request: the health monitor, the metrics collector and the
search-keeper build sources with no resource store. So the forwarders are kept
here, the way the keyring is a module (D147), each bound to the event loop that
made it.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import asyncssh

from app.adapters.credentials import SigningKey
from app.adapters.protocol import AdapterError
from app.adapters.ssh.options import SshOptions
from app.adapters.ssh.session import connect, identity_of, reduced
from app.core.translation import say

logger = logging.getLogger(__name__)

LOOPBACK = "127.0.0.1"
# A forwarder nothing has asked for and nothing flows through for this long
# closes its port and signs out. A pool holding an idle connection keeps it.
IDLE_SECONDS = 600.0
_CHUNK = 65_536


class Forwarder:
    """A port on loopback that reaches `host:port`, or a socket, from one SSH server."""

    def __init__(
        self, options: SshOptions, host: str, port: int, socket: str | None = None
    ) -> None:
        self._options = options
        self._host = host
        self._port = port
        self._socket = socket
        self.loop = asyncio.get_running_loop()
        # The key the last caller held. A channel opened later, for a pool
        # filling itself, signs in again with it; the caller asked the keyring
        # first, so a locked key has already stopped the request (D147).
        self._signing: SigningKey | None = None
        self._connection: asyncssh.SSHClientConnection | None = None
        self._lock = asyncio.Lock()
        self._server: asyncio.Server | None = None
        self._flowing = 0
        self._used_at = time.monotonic()

    def idle(self) -> bool:
        return self._flowing == 0 and time.monotonic() - self._used_at > IDLE_SECONDS

    async def endpoint(self, signing: SigningKey | None) -> tuple[str, int]:
        """Where to dial, once the SSH server has said it can reach the target.

        Signing in happens here rather than when a channel is opened, so a
        refused key or a server that does not forward is the caller's answer
        instead of a database that hung up.
        """
        self._signing = signing
        self._used_at = time.monotonic()
        await self._connected()
        if self._server is None:
            self._server = await asyncio.start_server(self._accept, LOOPBACK, 0)
        port: int = self._server.sockets[0].getsockname()[1]
        return LOOPBACK, port

    async def close(self) -> None:
        server, connection = self._server, self._connection
        self._server, self._connection = None, None
        if server is not None:
            server.close()
        if connection is not None:
            connection.close()
            await connection.wait_closed()

    async def _connected(self) -> asyncssh.SSHClientConnection:
        async with self._lock:
            if self._connection is not None and not self._connection.is_closed():
                return self._connection
            try:
                connection = await connect(self._options, self._signing)
            except (asyncssh.Error, OSError, TimeoutError) as failure:
                raise reduced(failure) from None
            try:
                # One channel opened and closed: whether this server forwards
                # at all, and whether it reaches the target, is said now.
                _, writer = await self._open(connection)
                writer.close()
            except asyncssh.ChannelOpenError as failure:
                connection.close()
                raise self._refused(failure) from None
            except BaseException:
                connection.close()
                raise
            self._connection = connection
            return connection

    async def _open(
        self, connection: asyncssh.SSHClientConnection
    ) -> tuple[asyncssh.SSHReader[bytes], asyncssh.SSHWriter[bytes]]:
        if self._socket is not None:
            return await connection.open_unix_connection(self._socket, encoding=None)
        return await connection.open_connection(self._host, self._port, encoding=None)

    def _refused(self, failure: asyncssh.ChannelOpenError) -> AdapterError:
        logger.warning("SSH tunnel refused: %r", failure)
        if self._socket is not None:
            # OpenSSH answers a missing socket, one the account may not open
            # and socket forwarding switched off alike: "open failed", code 2
            # (checked on OpenSSH 10.3). So one sentence names all three.
            return AdapterError(
                "config",
                say(
                    "The SSH server could not open {socket}: nothing may be listening there, {user} may not be allowed to use it (the docker group), or AllowStreamLocalForwarding is off",
                    socket=self._socket,
                    user=self._options.username,
                ),
            )
        if failure.code == asyncssh.OPEN_ADMINISTRATIVELY_PROHIBITED:
            return AdapterError(
                "config",
                say("The SSH server does not forward connections; AllowTcpForwarding is off there"),
            )
        return AdapterError(
            "network",
            say(
                "The SSH server could not reach {host}:{port}",
                host=self._host,
                port=self._port,
            ),
        )

    async def _accept(
        self, local_reader: asyncio.StreamReader, local_writer: asyncio.StreamWriter
    ) -> None:
        self._flowing += 1
        try:
            try:
                connection = await self._connected()
                remote_reader, remote_writer = await self._open(connection)
            except (AdapterError, asyncssh.Error, OSError, TimeoutError) as failure:
                # The driver sees its connection closed and says so; what went
                # wrong is said to the next caller of `endpoint`.
                logger.warning("SSH tunnel could not open a channel: %r", failure)
                local_writer.close()
                return
            try:
                await asyncio.gather(
                    _pipe(local_reader, remote_writer), _pipe(remote_reader, local_writer)
                )
            finally:
                remote_writer.close()
                local_writer.close()
        finally:
            self._flowing -= 1
            self._used_at = time.monotonic()


async def _pipe(
    reader: asyncio.StreamReader | asyncssh.SSHReader[bytes],
    writer: asyncio.StreamWriter | asyncssh.SSHWriter[bytes],
) -> None:
    """Copy one direction until it ends, then say so to the other side."""
    try:
        while chunk := await reader.read(_CHUNK):
            writer.write(chunk)
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()
    except (OSError, asyncssh.Error):
        writer.close()


@dataclass
class Tunnels:
    """Every forwarder of this process, by server, account and target."""

    _forwarders: dict[tuple[str, str, int], Forwarder] = field(default_factory=dict)

    async def endpoint(
        self, options: SshOptions, signing: SigningKey | None, host: str, port: int
    ) -> tuple[str, int]:
        return await self._forwarder(
            (identity_of(options), host.lower(), port),
            lambda: Forwarder(options, host, port),
            signing,
        )

    async def socket_endpoint(
        self, options: SshOptions, signing: SigningKey | None, path: str
    ) -> tuple[str, int]:
        """A port on loopback reaching a Unix socket on the SSH server (D405)."""
        return await self._forwarder(
            # No host name has a slash, so a path never meets a host's key.
            (identity_of(options), path, 0),
            lambda: Forwarder(options, "", 0, socket=path),
            signing,
        )

    async def _forwarder(
        self,
        key: tuple[str, str, int],
        make: Callable[[], Forwarder],
        signing: SigningKey | None,
    ) -> tuple[str, int]:
        await self._sweep()
        found = self._forwarders.get(key)
        # A forwarder belongs to the loop that made it; a test's loop or a
        # second process never reaches one of another's.
        if found is None or found.loop is not asyncio.get_running_loop():
            found = make()
            self._forwarders[key] = found
        return await found.endpoint(signing)

    async def _sweep(self) -> None:
        loop = asyncio.get_running_loop()
        for key in [
            key
            for key, forwarder in self._forwarders.items()
            if forwarder.loop is loop and forwarder.idle()
        ]:
            await self._forwarders.pop(key).close()


TUNNELS = Tunnels()
