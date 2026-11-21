"""How this application reaches a Docker daemon, and nothing about what for.

The daemon's socket is forwarded through the owner's SSH connection and the
Engine API is spoken over the forwarded port (D405), or the daemon is dialled
on TCP with mutual TLS, through an SSH tunnel when one is chosen (D418); the
client is the one the managed services use (D406). The API version is negotiated once per
session: the lower of what this source is written for and what the daemon
speaks, never below 1.41.

Neither the daemon's words nor httpx's cross this boundary: the daemon's name
host paths and digests, and httpx's the address.
"""

import asyncio
import json
import logging
import os
import ssl
import tempfile
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx
from anyio import to_thread

from app.adapters.docker.options import (
    DockerConnection,
    DockerSshOptions,
    DockerTlsOptions,
)
from app.adapters.docker_api.client import (
    EngineClient,
    EngineRefused,
    EngineUnreachable,
)
from app.adapters.docker_api.hijack import UpgradeRefused, upgrade_request
from app.adapters.docker_api.hijack import upgraded as read_upgrade
from app.adapters.protocol import AdapterError, ConnectionCheckResult, NodeNotFound
from app.adapters.tunnels import TunnelAccess, tunnel_of
from app.core.translation import say

logger = logging.getLogger(__name__)

# What one request may cost. Disk usage walks every volume and has its own.
UPGRADE_SECONDS = 15.0
TIMEOUT_SECONDS = 15.0
SLOW_SECONDS = 120.0
# How long the question "does a daemon answer here without TLS" may take.
PLAIN_PROBE_SECONDS = 3.0

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


def tls_context(options: DockerTlsOptions) -> ssl.SSLContext:
    """The daemon's CA trusted, and the client's certificate and key offered.

    The standard library loads a certificate chain only from files, so the
    two are written to a directory only this process may read and removed
    before this returns. Blocking: called in a thread.
    """
    try:
        made = ssl.create_default_context(cadata=options.ca_certificate)
    except ssl.SSLError:
        raise AdapterError("config", say("The CA certificate could not be read")) from None
    with tempfile.TemporaryDirectory(prefix="dp-docker-") as folder:
        certificate = os.path.join(folder, "cert.pem")
        key = os.path.join(folder, "key.pem")
        for path, text in (
            (certificate, options.client_certificate),
            (key, options.client_key.get_secret_value()),
        ):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(text)
        try:
            made.load_cert_chain(certificate, key)
        except ssl.SSLError:
            raise AdapterError(
                "config",
                say("The client certificate and key could not be read, or are not a pair"),
            ) from None
    return made


def ssl_error_of(failure: BaseException | None) -> ssl.SSLError | None:
    """The TLS failure under what httpx raised, if it was one."""
    seen: set[int] = set()
    while failure is not None and id(failure) not in seen:
        if isinstance(failure, ssl.SSLError):
            return failure
        seen.add(id(failure))
        failure = failure.__cause__ or failure.__context__
    return None


def url_host(host: str) -> str:
    """A host as a URL writes it: an IPv6 address in brackets."""
    return f"[{host}]" if ":" in host else host


def segment(name: str) -> str:
    """An id or a name as one segment of the API's path, never concatenated raw."""
    return quote(name, safe="")


class DockerSession:
    """One daemon, reached through a forwarded socket or over TLS, a request at
    a time."""

    def __init__(
        self,
        options: DockerConnection,
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
        self._here = ("127.0.0.1", 0)
        self._version: tuple[int, int] | None = None
        self._tls: ssl.SSLContext | None = None
        self._lock = asyncio.Lock()

    @property
    def options(self) -> DockerConnection:
        return self._options

    @property
    def version(self) -> tuple[int, int] | None:
        """The API version spoken, once the session has negotiated it."""
        return self._version

    def _daemon_host(self) -> str:
        """The name the daemon's TLS certificate is checked against."""
        options = self._options
        return options.host.strip("[]") if isinstance(options, DockerTlsOptions) else ""

    async def _address(self) -> tuple[str, int]:
        options = self._options
        through = tunnel_of(
            options.ssh_connection if isinstance(options, DockerSshOptions) else options.ssh_tunnel
        )
        if through is None:
            if isinstance(options, DockerSshOptions):  # pragma: no cover - required
                raise AdapterError(
                    "config", say("Choose the SSH connection the daemon is reached through")
                )
            return self._daemon_host(), options.port
        if self._tunnels is None:
            raise AdapterError(
                "config", say("This connection goes through an SSH tunnel, and none is at hand")
            )
        if isinstance(options, DockerSshOptions):
            return await self._tunnels.socket_endpoint(through, options.socket)
        return await self._tunnels.endpoint(through, self._daemon_host(), options.port)

    async def _tls_context(self) -> ssl.SSLContext | None:
        options = self._options
        if not isinstance(options, DockerTlsOptions):
            return None
        if self._tls is None:
            self._tls = await to_thread.run_sync(tls_context, options)
        return self._tls

    async def engine(self) -> EngineClient:
        """The client at the negotiated version; asked before every request,
        so a locked key, a closed SSH connection or a refused certificate is
        said there."""
        host, port = await self._address()
        self._here = (host, port)
        async with self._lock:
            if self._engine is None or self._engine_port != port:
                transport = self._transport
                context = await self._tls_context()
                scheme = "http" if context is None else "https"
                plain = EngineClient(
                    lambda: transport or httpx.AsyncHTTPTransport(verify=context or True),
                    base_url=f"{scheme}://{url_host(host)}:{port}",
                    # The certificate names the daemon, not a forwarded port.
                    server_name=self._daemon_host() or None,
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
        except EngineUnreachable as failure:
            raise await self._not_reached(failure.cause) from None
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
            raise self.unreachable() from None
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
            raise self.unreachable() from None
        except EngineRefused as refused:
            if refused.status == 404 and node_id:
                raise NodeNotFound(node_id) from None
            raise _refused(refused.status, path) from None
        return answer.status, _json(answer.body) if answer.body.strip() else None

    async def upgraded(
        self, path: str, body: Mapping[str, Any]
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """A request the daemon turns into a raw stream: an exec's start (D406)."""
        engine = await self.engine()
        host, port = self._here
        context = await self._tls_context()
        try:
            if context is None:
                reader, writer = await asyncio.open_connection(host, port)
            else:
                reader, writer = await asyncio.open_connection(
                    host, port, ssl=context, server_hostname=self._daemon_host()
                )
        except OSError:
            raise self.unreachable() from None
        try:
            writer.write(upgrade_request(engine.prefix + path, json.dumps(body).encode()))
            await writer.drain()
            await read_upgrade(reader, UPGRADE_SECONDS)
        except (UpgradeRefused, TimeoutError, OSError, asyncio.IncompleteReadError):
            writer.close()
            raise AdapterError(
                "unknown", say("The Docker server did not open the terminal")
            ) from None
        return reader, writer

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


    def unreachable(self) -> AdapterError:
        """A daemon that stopped answering, said by the way it is reached."""
        options = self._options
        if isinstance(options, DockerSshOptions):
            return AdapterError(
                "network", say("The Docker server stopped answering through the SSH connection")
            )
        return AdapterError(
            "network",
            say(
                "The Docker server does not answer at {address}",
                address=f"{options.host}:{options.port}",
            ),
        )

    async def _not_reached(self, cause: BaseException | None) -> AdapterError:
        """Why the first exchange failed: over TLS, which part of the handshake."""
        options = self._options
        failure = ssl_error_of(cause)
        if not isinstance(options, DockerTlsOptions) or failure is None:
            return self.unreachable()
        if isinstance(failure, ssl.SSLCertVerificationError):
            if "Hostname mismatch" in str(failure.verify_message):
                return AdapterError(
                    "config",
                    say(
                        "The Docker server's certificate is not for {host}; use the name it was issued for",
                        host=options.host,
                    ),
                )
            return AdapterError(
                "config",
                say("The Docker server's certificate is not signed by the CA certificate"),
            )
        reason = (failure.reason or "").upper()
        if "CERTIFICATE" in reason or "UNKNOWN_CA" in reason:
            return AdapterError(
                "auth", say("The Docker server did not accept the client certificate")
            )
        if await self._answers_plainly():
            return AdapterError(
                "config",
                say(
                    "This Docker server listens without TLS, which is refused: whoever reaches its port owns the machine"
                ),
            )
        return AdapterError(
            "network",
            say(
                "The Docker server at {address} did not answer over TLS",
                address=f"{options.host}:{options.port}",
            ),
        )

    async def _answers_plainly(self) -> bool:
        """Whether a daemon answers here without TLS, port 2375's way (D418).

        Asked only after a handshake failed, so that the refusal names the
        reason rather than reading like a broken network. Only `/_ping`.
        """
        host, port = self._here
        transport = self._transport
        probe = EngineClient(
            lambda: transport or httpx.AsyncHTTPTransport(),
            base_url=f"http://{url_host(host)}:{port}",
        )
        try:
            answer = await probe.request(
                "GET", "/_ping", expected=(200,), seconds=PLAIN_PROBE_SECONDS
            )
        except (EngineUnreachable, EngineRefused):
            return False
        return answer.body.strip() == b"OK"


def _json(body: bytes) -> Any:
    try:
        return json.loads(body) if body else None
    except ValueError:
        raise AdapterError(
            "network", say("Something answers on that socket, but not as a Docker server")
        ) from None


def _refused(status: int, path: str) -> AdapterError:
    """The daemon's status in this repository's words (D409)."""
    if status == 403:
        # An authorization plugin or a filtering proxy in front of the socket.
        return AdapterError("auth", say("The Docker server did not allow this"))
    if status == 404:
        return AdapterError("config", say("The Docker server has no such thing"))
    logger.warning("Docker answered %s to %s", status, path)
    return AdapterError("unknown", say("The Docker server could not do that"))
