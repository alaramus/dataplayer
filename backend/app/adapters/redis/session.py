"""How this application talks to a Redis server, and nothing about what for.

One place that opens a connection, one place that turns a driver's failure
into something safe to show, and nothing else. The catalog, the reader and the
actions are built on this rather than inside it — the same split PostgreSQL
has, and for the same reason: a class that knew both connections and key
spaces would grow along two axes at once.

A driver's own message names the host, the port and sometimes the password of
the connection it failed on, so none of it crosses this boundary.
"""

import logging
import ssl
import time
from collections.abc import AsyncIterator, Awaitable, Mapping
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis
from redis.exceptions import (
    AuthenticationError,
    RedisError,
    ResponseError,
)
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)
from redis.exceptions import (
    TimeoutError as RedisTimeoutError,
)

from app.adapters.cloud import CloudAccess
from app.adapters.cloud.signin import SignIn
from app.adapters.protocol import AdapterError, ConnectionCheckResult, ErrorKind
from app.adapters.redis.options import RedisOptions
from app.adapters.tls import ssl_context
from app.adapters.tunnels import TunnelAccess, reach
from app.core.logs import record_failure, with_ref
from app.core.translation import say

logger = logging.getLogger(__name__)

# What a call may cost. A server that has not answered in this long is one
# somebody is waiting on a page for.
TIMEOUT_SECONDS = 5.0

# What a value is decoded as when it is text, and what happens when it is not.
# Redis holds bytes and says nothing about what they mean; a viewer has to
# show something, and a replacement character is more honest than a refusal to
# show a key that happens to hold a JPEG.
ENCODING = "utf-8"


def read_version(info: Mapping[str, object]) -> str | None:
    """What `INFO server` says the server is, named when it is a fork (D377).

    Valkey keeps `redis_version` at 7.2.4 for clients that read it and names
    itself in `server_name`; KeyDB names itself only by its program; Dragonfly
    in a field of its own, "df-v2.1" (D378).
    """
    if info.get("server_name") == "valkey":
        valkey = info.get("valkey_version")
        if isinstance(valkey, str) and valkey:
            return f"Valkey {valkey}"
    dragonfly = info.get("dragonfly_version")
    if isinstance(dragonfly, str) and dragonfly:
        return f"Dragonfly {dragonfly.removeprefix('df-').removeprefix('v')}"
    version = info.get("redis_version")
    if not isinstance(version, str) or not version:
        return None
    program = str(info.get("executable", "")).rsplit("/", 1)[-1]
    return f"KeyDB {version}" if program == "keydb-server" else version


class _TlsConnection(redis.Connection):
    """A connection that wraps its socket in a context made elsewhere."""

    def __init__(self, *, tls_context: ssl.SSLContext, **kwargs: Any) -> None:
        self._tls_context = tls_context
        super().__init__(**kwargs)

    def _connection_arguments(self) -> Mapping[str, Any]:
        return {**super()._connection_arguments(), "ssl": self._tls_context}


class RedisSession:
    """A way to reach one Redis server, opened per operation."""

    def __init__(
        self,
        options: RedisOptions,
        tunnels: TunnelAccess | None = None,
        cloud: CloudAccess | None = None,
    ) -> None:
        self._options = options
        self._tunnels = tunnels
        # Asked at every new connection by a variant whose token is issued (D449).
        self._cloud = cloud
        self._tls: ssl.SSLContext | None = None

    async def _address(self) -> tuple[str, int]:
        """Where to dial now: through the tunnel when there is one (D282)."""
        options = self._options
        return await reach(self._tunnels, options.ssh_tunnel, options.host, options.port)

    @property
    def database(self) -> int:
        return self._options.database

    async def sign_in(self) -> SignIn:
        return await self._options.sign_in(self._cloud)

    async def _open(self, database: int | None = None) -> redis.Redis:
        """A client signed in now: an issued token is good for fifteen minutes."""
        return self._client(await self._address(), await self.sign_in(), database)

    def _client(
        self, address: tuple[str, int], signed: SignIn, database: int | None = None
    ) -> redis.Redis:
        """A client on one of the server's key spaces.

        Which one is asked for per call rather than fixed at construction: the
        number in the connection says where the catalog opens, and the catalog
        is free to be told to look at another (D91). A number out of the
        server's range is refused by the server on connect, which is the only
        party that knows how many it was started with.
        """
        password = signed.password
        host, port = address
        user = signed.user
        arguments: dict[str, Any] = {
            "host": host,
            "port": port,
            "db": self._options.database if database is None else database,
            # Named so the driver signs in inside HELLO: Dragonfly refuses a
            # HELLO sent before AUTH, which Redis answers (D378). RESP3 needs
            # Redis 6, whose default user this is.
            "username": (user or "default") if password is not None else None,
            "password": password,
            "socket_connect_timeout": TIMEOUT_SECONDS,
            "socket_timeout": TIMEOUT_SECONDS,
            # Bytes, decoded where a value is shown rather than by the driver:
            # a key may hold anything at all, and a driver that decoded would
            # raise on the first one that is not text.
            "decode_responses": False,
        }
        context = self._tls_context()
        if context is None:
            return redis.Redis(**arguments)
        # redis-py's own TLS connection builds its context from file names;
        # this one is handed the context the TLS block made (D446, D448).
        pool = redis.ConnectionPool(
            connection_class=_TlsConnection, tls_context=context, **arguments
        )
        return redis.Redis.from_pool(pool)

    def _tls_context(self) -> ssl.SSLContext | None:
        if self._tls is None:
            # The certificate names the server, also at a tunnel's end.
            self._tls = ssl_context(self._options.tls(), server_name=self._options.host)
        return self._tls

    @asynccontextmanager
    async def connection(
        self, database: int | None = None
    ) -> AsyncIterator[redis.Redis]:
        """One connection, closed however the caller leaves.

        No pooling. Everything this source does is a handful of round trips
        against a server that answers in microseconds; a pool would be a
        lifetime to manage for no gain, and `check_connection` deliberately
        opens its own anyway.
        """
        client = await self._open(database)
        try:
            yield client
        except RedisError as failure:
            raise _reduced(failure) from None
        finally:
            await client.aclose()

    async def server_version(self) -> str | None:
        """What the server says it is running, or nothing when it will not say.

        The fields of `INFO server` that name the server and no more: the rest
        of that answer is the machine, the process and the uptime of somebody
        else's server, none of which was asked for. Never worth failing over — whether the connection
        works is what the caller asked, and this is a line beside the answer.
        """
        try:
            client = await self._open()
        except AdapterError:
            return None
        try:
            info: dict[str, object] = await client.info("server")
        except RedisError:
            return None
        finally:
            await client.aclose()
        return read_version(info)

    async def check(self) -> ConnectionCheckResult:
        """Say hello, and say what happened in words that name no address."""
        try:
            client = await self._open()
        except AdapterError as failure:
            return _refused(failure.error_kind, failure.message)
        started = time.perf_counter()
        try:
            await client.ping()
        except AuthenticationError:
            return _refused("auth", say("Authentication failed"))
        except RedisTimeoutError:
            return _refused("timeout", say("Connection timed out"))
        except RedisConnectionError:
            return _refused("network", say("Could not reach the Redis server"))
        except RedisError:
            return _refused("unknown", say("The Redis server refused the connection"))
        finally:
            await client.aclose()
        elapsed = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=elapsed
        )


def _refused(kind: ErrorKind, message: str) -> ConnectionCheckResult:
    return ConnectionCheckResult(ok=False, message=message, error_kind=kind)


def _reduced(failure: RedisError) -> AdapterError:
    """The driver's failure as a kind and a sentence of this repository's.

    Logged on the server, where the address it names is already known, and
    never passed on: an expected one as a line, anything else whole, with the
    ref the sentence carries (D184).
    """
    known = _known(failure)
    if known is not None:
        logger.warning("Redis failed: %s", failure)
        return known
    ref = record_failure(logger, "Redis: an unexpected failure", failure)
    return AdapterError(
        "unknown", with_ref(say("The Redis server could not do that"), ref)
    )


def _known(failure: RedisError) -> AdapterError | None:
    if isinstance(failure, AuthenticationError):
        return AdapterError("auth", say("This connection was refused by the server"))
    if isinstance(failure, RedisTimeoutError):
        return AdapterError("timeout", say("The Redis server did not answer in time"))
    if isinstance(failure, RedisConnectionError):
        return AdapterError("network", say("Could not reach the Redis server"))
    if isinstance(failure, ResponseError):
        return AdapterError("unknown", say("The Redis server refused that command"))
    return None


def text(raw: Any) -> str:
    """What a value looks like on a screen.

    Redis holds bytes and says nothing about what they mean. A key that holds
    a JPEG is still a key somebody may want to see listed, so the bytes are
    decoded with replacement rather than refused.
    """
    if isinstance(raw, bytes):
        return raw.decode(ENCODING, errors="replace")
    return str(raw)


async def resolved[T](value: Awaitable[T]) -> T:
    """The answer to one command."""
    return await value
