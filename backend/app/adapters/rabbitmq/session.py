"""How this application talks to a RabbitMQ broker, and nothing about what for.

Two doors (D325). The management API, over HTTP, says what there is; a client
per operation, since a catalog asks a few times a minute and the API on a
broker's own port answers in milliseconds. AMQP 0-9-1 moves messages; a
connection per operation as well, opened, used and closed inside one call.

Neither driver's text crosses this boundary: aiormq's names the address and
the user, and an HTTP error carries the URL.
"""

import logging
import ssl
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

import aio_pika
import httpx
from aio_pika.abc import AbstractChannel
from aiormq import exceptions as amqp

from app.adapters.protocol import (
    AdapterError,
    ConnectionCheckResult,
    ErrorKind,
    NodeNotFound,
)
from app.adapters.rabbitmq.options import RabbitmqOptions
from app.core.logs import record_failure, with_ref
from app.core.translation import say

logger = logging.getLogger(__name__)

# What one request to the broker may cost.
TIMEOUT_SECONDS = 5.0

# aiormq logs a refused connection at error level with the address in it,
# and the failure is reduced and logged once below.
logging.getLogger("aiormq.connection").setLevel(logging.CRITICAL)
logging.getLogger("aio_pika.connection").setLevel(logging.CRITICAL)


def segment(name: str) -> str:
    """A virtual host or a name as one segment of the API's path."""
    return quote(name, safe="")


class RabbitmqSession:
    """A way to reach one broker, opened per operation."""

    def __init__(self, options: RabbitmqOptions) -> None:
        self._options = options

    @property
    def options(self) -> RabbitmqOptions:
        return self._options

    def _ssl_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context()
        if self._options.ca_certificate.strip():
            context.load_verify_locations(cadata=self._options.ca_certificate)
        return context

    def _client(self) -> httpx.AsyncClient:
        options = self._options
        secure = options.management().startswith("https://")
        return httpx.AsyncClient(
            base_url=options.management() + "/api",
            auth=(options.user, options.password.get_secret_value()),
            verify=self._ssl_context() if secure else False,
            timeout=TIMEOUT_SECONDS,
            # A proxy named in the backend's environment is not the user's to
            # send their password through.
            trust_env=False,
        )

    async def api(
        self,
        path: str,
        params: dict[str, str] | None = None,
        node_id: str = "",
    ) -> Any:
        """The management API's answer to a GET, or a reduced failure."""
        try:
            async with self._client() as client:
                response = await client.get(path, params=params)
        except httpx.HTTPError as failure:
            raise _unreachable(failure) from None
        if response.status_code == 404 and node_id:
            raise NodeNotFound(node_id)
        if response.status_code >= 400:
            raise _refused_http(response.status_code)
        try:
            return response.json()
        except ValueError:
            raise AdapterError(
                "network", say("The management API did not answer as RabbitMQ does")
            ) from None

    @asynccontextmanager
    async def channel(
        self, node_id: str = "", vhost: str | None = None
    ) -> AsyncIterator[AbstractChannel]:
        """An AMQP channel on a connection of its own to a virtual host — the
        node's, or the connection's — closed after."""
        options = self._options
        try:
            connection = await aio_pika.connect(
                host=options.host,
                port=options.port,
                login=options.user,
                password=options.password.get_secret_value(),
                virtualhost=vhost or options.vhost or "/",
                ssl=options.tls,
                ssl_context=self._ssl_context() if options.tls else None,
                timeout=TIMEOUT_SECONDS,
                client_properties={"connection_name": "DataPlayer"},
            )
        except (amqp.AMQPError, OSError, TimeoutError) as failure:
            raise reduced(failure, node_id) from None
        try:
            async with connection:
                channel = await connection.channel()
                yield channel
        except NodeNotFound, AdapterError, ValueError:
            raise
        except (amqp.AMQPError, OSError, TimeoutError) as failure:
            raise reduced(failure, node_id) from None

    async def check(self) -> ConnectionCheckResult:
        """The management API and then AMQP, in words that name no address.

        AMQP refused with the API answering still saves the connection: its
        catalog works, and what moves messages says why it cannot (D325).
        """
        started = time.perf_counter()
        try:
            await self.api("/whoami")
        except AdapterError as failure:
            if failure.error_kind == "network":
                return _failed(
                    "network",
                    say(
                        "Could not reach the management API; RabbitMQ needs its "
                        "management plugin here"
                    ),
                )
            return _failed(failure.error_kind, failure.message)
        elapsed = int((time.perf_counter() - started) * 1000)
        try:
            async with self.channel():
                pass
        except AdapterError as failure:
            return ConnectionCheckResult(
                ok=True,
                message=say(
                    "The management API answers, but AMQP does not: {reason}",
                    reason=failure.message,
                ),
                latency_ms=elapsed,
            )
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=elapsed
        )


def _failed(kind: ErrorKind, message: str) -> ConnectionCheckResult:
    return ConnectionCheckResult(ok=False, message=message, error_kind=kind)


def _unreachable(failure: httpx.HTTPError) -> AdapterError:
    logger.warning("RabbitMQ management API unreachable: %s", type(failure).__name__)
    if isinstance(failure, httpx.ConnectError) and "CERTIFICATE" in str(failure):
        return AdapterError(
            "network", say("The broker's certificate could not be verified")
        )
    return AdapterError("network", say("Could not reach the RabbitMQ management API"))


def _refused_http(status: int) -> AdapterError:
    if status == 401:
        return AdapterError("auth", say("This connection was refused by the broker"))
    if status == 403:
        return AdapterError("auth", say("This connection may not do that"))
    if status == 404:
        return AdapterError(
            "config", say("The management API has no such address; check its path")
        )
    logger.warning("RabbitMQ management API answered %s", status)
    return AdapterError("unknown", say("The RabbitMQ broker could not do that"))


def reduced(failure: BaseException, node_id: str = "") -> AdapterError | NodeNotFound:
    """aiormq's failure as a kind and a sentence of this repository's (D21)."""
    if isinstance(failure, amqp.ChannelNotFoundEntity) and node_id:
        return NodeNotFound(node_id)
    if isinstance(failure, amqp.ProbableAuthenticationError):
        return AdapterError("auth", say("This connection was refused by the broker"))
    if isinstance(failure, amqp.ChannelAccessRefused):
        return AdapterError("auth", say("This connection may not do that"))
    if isinstance(failure, amqp.InvalidFrameError):
        # The broker closes the connection at `open` for a virtual host that
        # is not there or not this user's.
        return AdapterError(
            "auth", say("The broker refused the virtual host to this connection")
        )
    if isinstance(failure, ssl.SSLError):
        return AdapterError(
            "network", say("The broker's certificate could not be verified")
        )
    if isinstance(failure, OSError | TimeoutError | amqp.AMQPConnectionError):
        logger.warning("RabbitMQ AMQP unreachable: %s", type(failure).__name__)
        return AdapterError("network", say("Could not reach the broker over AMQP"))
    if isinstance(failure, amqp.ChannelPreconditionFailed):
        return AdapterError("config", say("The RabbitMQ broker refused that"))
    ref = record_failure(logger, "RabbitMQ: an unexpected failure", failure)
    return AdapterError(
        "unknown", with_ref(say("The RabbitMQ broker could not do that"), ref)
    )
