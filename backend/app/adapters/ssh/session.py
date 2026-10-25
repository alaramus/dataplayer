"""How this application reaches an SSH server, and nothing about what for.

One place that signs in, one place that turns the library's failures into
sentences of this repository's, and the one connection a stored connector
keeps between requests. The catalog, the reader and the actions are built on
this, the split PostgreSQL and Redis have.

Three things are refused here rather than trusted to the library's defaults,
because each default reaches outside what the connection says:

- no server is trusted but the one whose key the connection pinned (D145) —
  no `known_hosts` file, and never "accept anything";
- no key is offered but the one the connection names — no agent of this
  process, no `~/.ssh` of whoever runs it;
- no `~/.ssh/config` is read, which could otherwise send the connection
  through a proxy or to another host.
"""

import asyncio
import hashlib
import json
import logging
import posixpath
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import asyncssh

from app.adapters.credentials import SigningKey
from app.adapters.explorer.storage import is_plain_name
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.adapters.registry import AdapterContext
from app.adapters.ssh import keys
from app.adapters.ssh.options import SshKeyAuth, SshOptions, SshPassword
from app.core.logs import record_failure, with_ref
from app.core.translation import say

logger = logging.getLogger(__name__)

# What connecting may cost, and what a person is left waiting for on a page.
TIMEOUT_SECONDS = 10.0
# A kept connection says something now and then, so a firewall that drops
# idle sessions does not leave it half-open until the next request finds out.
KEEPALIVE_SECONDS = 30.0

# Which of a server's keys is asked for first when it is fetched (D145). The
# one a person compares is usually `ssh_host_ed25519_key.pub`, so ED25519 is
# preferred, then ECDSA, then RSA for servers that have nothing newer. Once a
# key is pinned only its own algorithm is offered, so this decides nothing
# after the first fetch.
PREFERRED_HOST_KEY_ALGORITHMS = (
    "ssh-ed25519",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "rsa-sha2-512",
    "rsa-sha2-256",
    "ssh-rsa",
)


@dataclass(frozen=True)
class Remote:
    """A live SSH/SFTP session and the folder the catalog stands in."""

    sftp: asyncssh.SFTPClient
    root: str
    connection: asyncssh.SSHClientConnection

    def path_of(self, node_id: str | None) -> str:
        """The remote path of a node, which is always inside the root.

        A node id is the path below the root, segment by segment, and every
        segment must be a plain name: the catalog never builds a path out of
        a `..` a client sent. Not a wall around the server — its own
        permissions are that — but where browsing stands (D144).
        """
        if node_id is None or node_id == "":
            return self.root
        parts = node_id.split("/")
        if not all(map(is_plain_name, parts)):
            raise ValueError(say("Not a path below this folder: {path}", path=node_id))
        return posixpath.join(self.root, *parts)


class SshLink:
    """One signed-in connection and its SFTP channel, kept between requests.

    Made again when the server has closed it — a reboot, a dropped network —
    rather than failing every request until it ages out. Whoever uses it has
    already asked for the key (see `SshSession.remote`), so a key that has
    been locked since stops the source even while this is still open.
    """

    def __init__(self, options: SshOptions) -> None:
        self._options = options
        self._connection: asyncssh.SSHClientConnection | None = None
        self._remote: Remote | None = None
        self._lock = asyncio.Lock()

    async def remote(self, signing: SigningKey | None) -> Remote:
        async with self._lock:
            if self._remote is not None and not _closed(self._connection):
                return self._remote
            await self._drop()
            connection = await connect(self._options, signing)
            try:
                sftp = await connection.start_sftp_client()
                root = await sftp.realpath(self._options.path or ".")
            except BaseException:
                connection.close()
                raise
            self._connection = connection
            self._remote = Remote(sftp=sftp, root=root, connection=connection)
            return self._remote

    async def close(self) -> None:
        async with self._lock:
            await self._drop()

    async def _drop(self) -> None:
        remote, connection = self._remote, self._connection
        self._remote, self._connection = None, None
        if remote is not None:
            remote.sftp.exit()
        if connection is not None:
            connection.close()
            await connection.wait_closed()


class SshSession:
    """A way to reach one SSH server, kept between requests when it may be."""

    def __init__(self, options: SshOptions, context: AdapterContext) -> None:
        self._options = options
        self._context = context

    @property
    def options(self) -> SshOptions:
        return self._options

    @asynccontextmanager
    async def remote(self, *, kept: bool = True) -> AsyncIterator[Remote]:
        """The server's files, reached through a connection that is signed in.

        The key is asked for on every use, not only on signing in: a key whose
        passphrase has stopped being held must stop the source now, not when a
        kept connection happens to close (D147). `kept=False` signs in afresh
        whatever the connector keeps, which is what a check is for (D10).
        """
        signing = await self._signing_key()
        pooling = self._context.pooling if kept else None
        try:
            if pooling is None:
                link = SshLink(self._options)
                try:
                    yield await link.remote(signing)
                finally:
                    await link.close()
                return
            link = await pooling.store.get_or_create(
                _key_for(pooling.connector_id, self._options),
                SshLink,
                _maker(self._options),
            )
            yield await link.remote(signing)
        except (asyncssh.Error, OSError, TimeoutError) as failure:
            raise reduced(failure) from None

    async def check(self) -> ConnectionCheckResult:
        """Sign in and find the folder, then say so in words that name no address."""
        started = time.perf_counter()
        try:
            async with self.remote(kept=False):
                pass
        except AdapterError as failure:
            return ConnectionCheckResult(
                ok=False, message=failure.message, error_kind=failure.error_kind
            )
        elapsed = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(ok=True, message=say("Connection successful"), latency_ms=elapsed)

    async def signed_in(self) -> asyncssh.SSHClientConnection:
        """A connection of the caller's own, signed in afresh, closed by the caller.

        Never the kept one: a terminal holds its connection for as long as the
        shell runs, and the kept one is made again whenever the server drops
        it, which would take the shell along (D149).
        """
        signing = await self._signing_key()
        try:
            return await connect(self._options, signing)
        except (asyncssh.Error, OSError, TimeoutError) as failure:
            raise reduced(failure) from None

    async def _signing_key(self) -> SigningKey | None:
        if not isinstance(self._options, SshKeyAuth):
            return None
        if self._context.keys is None:
            raise AdapterError(
                "config", say("This connection signs in with a key, and none is at hand")
            )
        return await self._context.keys.signing_key(self._options.key_id)


async def connect(
    options: SshOptions, signing: SigningKey | None
) -> asyncssh.SSHClientConnection:
    """Sign in to the server whose key the connection pinned, and to no other."""
    if options.host_key == "":
        raise AdapterError(
            "config", say("Fetch the server's key and confirm it before connecting")
        )
    try:
        trusted = asyncssh.import_public_key(options.host_key)
    except (asyncssh.KeyImportError, ValueError):
        raise AdapterError(
            "config", say("The server key of this connection cannot be read")
        ) from None
    try:
        client_keys = None if signing is None else [keys.client_key(signing)]
    except ValueError:
        raise AdapterError(
            "auth", say("The SSH key could not be opened with its passphrase")
        ) from None
    password = options.password.get_secret_value() if isinstance(options, SshPassword) else None
    # The pinned key and nothing else: trusted keys, then empty lists of CA
    # keys, revoked keys and X.509 names. The library names this shape with a
    # private alias, hence `Any`.
    known_hosts: Any = ([trusted], [], [], [], [], [], [])
    return await asyncio.wait_for(
        asyncssh.connect(
            options.host,
            options.port,
            username=options.username,
            password=password,
            client_keys=client_keys,
            known_hosts=known_hosts,
            agent_path=None,
            config=None,
            connect_timeout=TIMEOUT_SECONDS,
            login_timeout=TIMEOUT_SECONDS,
            keepalive_interval=KEEPALIVE_SECONDS,
        ),
        timeout=TIMEOUT_SECONDS * 2,
    )


async def server_key(host: str, port: int) -> str:
    """The key a server presents, asked before anything is sent to it (D145).

    Nothing is signed in and no credential leaves this process: the key is
    exchanged before authentication begins, and the connection is closed
    straight after.
    """
    try:
        key = await asyncio.wait_for(
            asyncssh.get_server_host_key(
                host,
                port,
                config=None,
                server_host_key_algs=list(PREFERRED_HOST_KEY_ALGORITHMS),
            ),
            timeout=TIMEOUT_SECONDS,
        )
    except (asyncssh.Error, OSError, TimeoutError) as failure:
        raise reduced(failure) from None
    if key is None:
        raise AdapterError("unknown", say("The server did not present a key"))
    return keys.public_line(key)


def reduced(failure: BaseException) -> AdapterError:
    """The library's failure as a kind and a sentence of this repository's.

    Logged here, where the address it names is already known, and never
    passed on: the library's words name hosts, users and paths. An expected
    one is a line; anything else is written whole, with the ref the sentence
    carries (D184).
    """
    known = _known(failure)
    if known is not None:
        logger.warning("SSH failed: %r", failure)
        return known
    ref = record_failure(logger, "SSH: an unexpected failure", failure)
    return AdapterError("unknown", with_ref(say("The server could not do that"), ref))


def _known(failure: BaseException) -> AdapterError | None:
    if isinstance(failure, asyncssh.HostKeyNotVerifiable):
        return AdapterError(
            "config",
            say(
                "The server presented a different key than the one this connection "
                "trusts. If it was reinstalled, fetch its key again and compare it"
            ),
        )
    if isinstance(failure, asyncssh.PermissionDenied):
        return AdapterError("auth", say("The server refused these credentials"))
    if isinstance(failure, asyncssh.SFTPNoSuchFile | asyncssh.SFTPNoSuchPath):
        return AdapterError("unknown", say("That is no longer on the server"))
    if isinstance(failure, asyncssh.SFTPPermissionDenied):
        return AdapterError("unknown", say("The server does not let this user do that"))
    if isinstance(failure, asyncssh.SFTPError):
        return AdapterError("unknown", say("The server could not do that"))
    if isinstance(failure, TimeoutError):
        return AdapterError("timeout", say("The server did not answer in time"))
    if isinstance(failure, asyncssh.DisconnectError | OSError):
        return AdapterError("network", say("Could not reach the server"))
    return None


def _closed(connection: asyncssh.SSHClientConnection | None) -> bool:
    return connection is None or connection.is_closed()


def identity_of(options: SshOptions) -> str:
    """One string for a server, an account and the way it is signed in to.

    Hashed because the options hold a password. Two connections that differ in
    any of it — a different account may read different files — are two
    identities: the copies of their files are kept apart by it (D152).
    """
    dumped = json.dumps(
        {
            **options.model_dump(mode="json"),
            "password": (
                options.password.get_secret_value()
                if isinstance(options, SshPassword)
                else None
            ),
        },
        sort_keys=True,
    )
    return hashlib.sha256(dumped.encode()).hexdigest()


def _key_for(connector_id: uuid.UUID, options: SshOptions) -> str:
    """Where this connector's connection, with these options, is kept.

    The options are part of the key so that editing them makes a different
    connection by itself (D10).
    """
    return f"ssh:{connector_id}:{identity_of(options)[:16]}"


def _maker(options: SshOptions) -> Callable[[], Awaitable[SshLink]]:
    async def make() -> SshLink:
        return SshLink(options)

    return make
