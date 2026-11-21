"""How this application reaches a Docker daemon, and nothing about what for.

The daemon's socket is forwarded through the owner's SSH connection and the
Engine API is spoken over the forwarded port (D405); the client is the one
the managed services use (D406). The API version is negotiated once per
session: the lower of what this source is written for and what the daemon
speaks, never below 1.41.

Neither the daemon's words nor httpx's cross this boundary: the daemon's name
host paths and digests, and httpx's the address.
"""

import asyncio
import json
import logging
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from app.adapters.docker.options import DockerOptions
from app.adapters.docker_api.client import (
    EngineClient,
    EngineRefused,
    EngineUnreachable,
)
from app.adapters.protocol import AdapterError, ConnectionCheckResult, NodeNotFound
from app.adapters.tunnels import TunnelAccess, tunnel_of
from app.core.translation import say

logger = logging.getLogger(__name__)

# What one request may cost. Disk usage walks every volume and has its own.
TIMEOUT_SECONDS = 15.0
SLOW_SECONDS = 120.0

# The oldest API this source is written to (Docker 20.10), and the newest it
# asks for: what it needs exists at the oldest, and nothing newer is used
# without asking the version first.
FLOOR = (1, 41)
CEILING = (1, 47)


def version_of(text: object) -> tuple[int, int] | None:
    if not isinstance(text, str):
        return None
    major, dot, minor = text.partition(".")
    if not dot or not major.isdigit() or not minor.isdigit():
        return None
    return int(major), int(minor)


def spoken(daemon: tuple[int, int]) -> tuple[int, int]:
    """The version both sides speak, or a refusal naming the daemon's."""
    if daemon < FLOOR:
        raise AdapterError(
            "config",
            say(
                "The Docker server speaks API {version}; 1.41 (Docker 20.10) or newer is needed",
                version=f"{daemon[0]}.{daemon[1]}",
            ),
        )
    return min(daemon, CEILING)


def segment(name: str) -> str:
    """An id or a name as one segment of the API's path, never concatenated raw."""
    return quote(name, safe="")


class DockerSession:
    """One daemon, reached through a forwarded socket, a request at a time."""

    def __init__(
        self,
        options: DockerOptions,
        tunnels: TunnelAccess | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._options = options
        self._tunnels = tunnels
        # A test answers with what the stand recorded; a deployment dials the
        # forwarded port.
        self._transport = transport
        self._engine: EngineClient | None = None
        # The forwarded port the client was made for: a forwarder closed for
        # idleness comes back on another one.
        self._engine_port = 0
        self._version: tuple[int, int] | None = None
        self._lock = asyncio.Lock()

    @property
    def options(self) -> DockerOptions:
        return self._options

    @property
    def version(self) -> tuple[int, int] | None:
        """The API version spoken, once the session has negotiated it."""
        return self._version

    async def _address(self) -> tuple[str, int]:
        connection_id = tunnel_of(self._options.ssh_connection)
        if connection_id is None:  # pragma: no cover - the options require one
            raise AdapterError("config", say("Choose the SSH connection the daemon is reached through"))
        if self._tunnels is None:
            raise AdapterError(
                "config", say("This connection goes through an SSH tunnel, and none is at hand")
            )
        return await self._tunnels.socket_endpoint(connection_id, self._options.socket)

    async def engine(self) -> EngineClient:
        """The client at the negotiated version; asked before every request,
        so a locked key or a closed SSH connection is said there."""
        host, port = await self._address()
        async with self._lock:
            if self._engine is None or self._engine_port != port:
                transport = self._transport
                plain = EngineClient(
                    lambda: transport or httpx.AsyncHTTPTransport(),
                    base_url=f"http://{host}:{port}",
                )
                self._version = spoken(await self._daemon_version(plain))
                self._engine = plain.at_version(f"{self._version[0]}.{self._version[1]}")
                self._engine_port = port
            return self._engine

    async def _daemon_version(self, plain: EngineClient) -> tuple[int, int]:
        try:
            ping = await plain.request("GET", "/_ping", expected=(200,), seconds=TIMEOUT_SECONDS)
            answer = await plain.request(
                "GET", "/version", expected=(200,), seconds=TIMEOUT_SECONDS
            )
        except EngineUnreachable:
            raise _unreachable() from None
        except EngineRefused as refused:
            raise _refused(refused.status, "") from None
        if ping.body.strip() != b"OK":
            raise AdapterError(
                "config", say("Something answers on that socket, but not as a Docker server")
            )
        body = answer.json()
        version = version_of(body.get("ApiVersion") if isinstance(body, dict) else None)
        if version is None:
            raise AdapterError(
                "config", say("Something answers on that socket, but not as a Docker server")
            )
        return version

    async def get(
        self,
        path: str,
        params: Mapping[str, str] | None = None,
        *,
        node_id: str = "",
        expected: tuple[int, ...] = (200,),
        seconds: float = TIMEOUT_SECONDS,
    ) -> tuple[int, Any]:
        """The daemon's answer to a GET, as status and JSON, or a reduced failure."""
        answer = await self.raw(
            path, params, node_id=node_id, expected=expected, seconds=seconds
        )
        return answer[0], _json(answer[1])

    async def raw(
        self,
        path: str,
        params: Mapping[str, str] | None = None,
        *,
        node_id: str = "",
        expected: tuple[int, ...] = (200,),
        seconds: float = TIMEOUT_SECONDS,
    ) -> tuple[int, bytes]:
        engine = await self.engine()
        try:
            answer = await engine.request(
                "GET", path, params=params, expected=expected, seconds=seconds
            )
        except EngineUnreachable:
            raise _unreachable() from None
        except EngineRefused as refused:
            if refused.status == 404 and node_id:
                raise NodeNotFound(node_id) from None
            raise _refused(refused.status, path) from None
        return answer.status, answer.body

    async def send(
        self,
        method: str,
        path: str,
        params: Mapping[str, str] | None = None,
        body: Any | None = None,
        *,
        expected: tuple[int, ...],
        node_id: str = "",
        seconds: float = TIMEOUT_SECONDS,
    ) -> tuple[int, Any]:
        """A change: the status among `expected` and the JSON, or a reduced failure.

        A status the caller expects is its to word; any other is said here.
        """
        engine = await self.engine()
        try:
            answer = await engine.request(
                method, path, params=params, json=body, expected=expected, seconds=seconds
            )
        except EngineUnreachable:
            raise _unreachable() from None
        except EngineRefused as refused:
            if refused.status == 404 and node_id:
                raise NodeNotFound(node_id) from None
            raise _refused(refused.status, path) from None
        return answer.status, _json(answer.body) if answer.body.strip() else None

    async def check(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        try:
            await self.engine()
            assert self._version is not None
        except AdapterError as failure:
            return ConnectionCheckResult(
                ok=False, message=failure.message, error_kind=failure.error_kind
            )
        return ConnectionCheckResult(
            ok=True,
            message=say(
                "Connection successful; API {version}",
                version=f"{self._version[0]}.{self._version[1]}",
            ),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _json(body: bytes) -> Any:
    try:
        return json.loads(body) if body else None
    except ValueError:
        raise AdapterError(
            "network", say("Something answers on that socket, but not as a Docker server")
        ) from None


def _unreachable() -> AdapterError:
    return AdapterError(
        "network", say("The Docker server stopped answering through the SSH connection")
    )


def _refused(status: int, path: str) -> AdapterError:
    """The daemon's status in this repository's words (D409)."""
    if status == 403:
        # An authorization plugin or a filtering proxy in front of the socket.
        return AdapterError("auth", say("The Docker server did not allow this"))
    if status == 404:
        return AdapterError("config", say("The Docker server has no such thing"))
    logger.warning("Docker answered %s to %s", status, path)
    return AdapterError("unknown", say("The Docker server could not do that"))
