"""Requests to a Docker daemon, each held to its own timeout (D406).

The daemon's words never leave here except in the log: a refusal is its
status, and each caller says what that status means for what it asked.
"""

import json
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# How long an ordinary request may take.
COMMAND_TIMEOUT_SECONDS = 30.0

type TransportFactory = Callable[[], httpx.AsyncBaseTransport]


class EngineUnreachable(Exception):
    """The daemon did not answer at all: no socket, a dropped link, a timeout,
    a TLS handshake that failed. `cause` is what failed, for the caller to
    word; it never leaves the server."""

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class EngineRefused(Exception):
    """The daemon answered with a status the caller did not expect."""

    def __init__(self, status: int, method: str, path: str) -> None:
        super().__init__(f"{method} {path}: {status}")
        self.status = status
        self.method = method
        self.path = path


@dataclass(frozen=True)
class Answer:
    status: int
    body: bytes

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except ValueError:
            return None


class EngineClient:
    """One daemon, reached through a transport made afresh for each exchange.

    A factory rather than a transport: an `httpx.AsyncClient` closes the
    transport it was given when it closes.
    """

    def __init__(
        self,
        transport: TransportFactory,
        *,
        base_url: str,
        prefix: str = "",
        server_name: str | None = None,
    ) -> None:
        self._transport = transport
        self._base_url = base_url
        self.prefix = prefix
        # The name a TLS certificate is checked against when the address
        # dialled is another — a port forwarded through SSH (D418).
        self._extensions = {"sni_hostname": server_name} if server_name else {}

    def at_version(self, version: str) -> EngineClient:
        """The same daemon, every path prefixed with `/v<version>`."""
        return EngineClient(
            self._transport,
            base_url=self._base_url,
            prefix=f"/v{version}",
            server_name=self._extensions.get("sni_hostname"),
        )

    @asynccontextmanager
    async def client(self, seconds: float | None) -> AsyncIterator[httpx.AsyncClient]:
        """A client for one exchange, held to httpx's own timeout.

        The bound belongs to the request rather than to a task wrapper: a
        timed-out HTTP call must close its connection, which the transport
        does and `asyncio.timeout` around it would not.
        """
        async with httpx.AsyncClient(
            transport=self._transport(),
            base_url=self._base_url + self.prefix,
            timeout=seconds,
        ) as client:
            yield client

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Any | None = None,
        expected: tuple[int, ...],
        seconds: float = COMMAND_TIMEOUT_SECONDS,
    ) -> Answer:
        try:
            async with self.client(seconds) as client:
                response = await client.request(
                    method, path, params=params, json=json, extensions=self._extensions
                )
        # An ssl.SSLError raised after the handshake — a client certificate
        # the daemon refused, under TLS 1.3 — reaches here unwrapped by httpx.
        except (httpx.HTTPError, OSError) as failure:
            logger.warning("Docker is unreachable: %r", failure)
            raise EngineUnreachable(str(failure), failure) from None
        if response.status_code not in expected:
            # Logged with the daemon's own words, because they are useful to
            # whoever runs this server; answered without them, because they
            # name paths, digests and images of the host.
            logger.warning(
                "Docker refused %s %s: %s %s",
                method,
                path,
                response.status_code,
                response.text[:500],
            )
            raise EngineRefused(response.status_code, method, path)
        return Answer(status=response.status_code, body=response.content)

    @asynccontextmanager
    async def stream(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        seconds: float | None,
    ) -> AsyncIterator[httpx.Response]:
        """A response read as it arrives; any status but 200 is a refusal.

        None waits for ever between chunks: a followed log or the daemon's
        events may say nothing for hours.
        """
        try:
            async with self.client(seconds) as client:
                async with client.stream(
                    method, path, params=params, extensions=self._extensions
                ) as response:
                    if response.status_code != 200:
                        await response.aread()
                        logger.warning(
                            "Docker refused %s %s: %s %s",
                            method,
                            path,
                            response.status_code,
                            response.text[:500],
                        )
                        raise EngineRefused(response.status_code, method, path)
                    yield response
        except (httpx.HTTPError, OSError) as failure:
            logger.warning("Docker is unreachable: %r", failure)
            raise EngineUnreachable(str(failure), failure) from None
