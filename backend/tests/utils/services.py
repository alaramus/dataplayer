"""The servers the backend suite talks to, and what a test does without one.

The application database is the base of the suite: without it a run stops at
once, with one line saying how to start it. Every other server belongs to the
tests of one piece, and a test that cannot reach its server is skipped with
that line, so working on one piece never needs another piece's server.
`--require-services` stops the run instead, and CI passes it: there the full
suite is the gate, and a server missing from the pipeline must not pass for
tests that were skipped.

A test reaches a server only through `require()`. Reading an address from the
environment anywhere else is refused by `tests/test_services.py`.
"""

import os
import socket
import struct
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import NoReturn
from urllib.parse import urlsplit

import pytest

from app.core.config import settings

# Long enough for a service container on a CI network, short enough that a
# refused port on Windows — which retries before it gives up — costs a second.
PROBE_SECONDS = 1.0


@dataclass(frozen=True)
class _Protocol:
    port: int
    hello: bytes
    # How the first byte of a live server's reply may start.
    replies: tuple[bytes, ...]


# A port that accepts is not a server that answers: Docker Desktop accepts on a
# published port as soon as the container runs, before the server inside
# listens, and then closes the connection. So the probe says hello in the
# server's own protocol and waits for a reply.
_PROTOCOLS = {
    # SSLRequest, the one message answered before authentication: S or N.
    "postgresql": _Protocol(5432, struct.pack("!ii", 8, 80877103), (b"S", b"N")),
    # PING is answered without the password too, if only with -NOAUTH.
    "redis": _Protocol(6379, b"PING\r\n", (b"+", b"-")),
}

_required = False


@dataclass(frozen=True)
class Server:
    name: str
    # Where the address comes from, named in the message a skip prints.
    variable: str
    # The command that starts the server for this checkout.
    start: str
    read: Callable[[], str]
    # A base server is needed by every test, so its absence stops the run.
    base: bool = False

    def url(self) -> str:
        """The address, without asking whether anything answers there."""
        return self.read()

    def available(self) -> bool:
        return _answers(self.url())

    def require(self) -> str:
        """The address of a server that answers, or no test at all."""
        url = self.url()
        if _answers(url):
            return url
        if self.base:
            _stop(self.absence())
        if _required:
            pytest.fail(self.absence(), pytrace=False)
        pytest.skip(self.absence())

    def absence(self) -> str:
        return (
            f"{self.name} does not answer at {_where(self.url())}: "
            f"start it with `{self.start}` or set {self.variable}"
        )


POSTGRES = Server(
    name="the application database",
    variable="DATABASE_URL",
    start="docker compose up -d db",
    read=lambda: str(settings.DATABASE_URL),
    base=True,
)

# Database 15, deliberately not 0: the tests empty the one they use.
REDIS = Server(
    name="Redis",
    variable="TEST_REDIS_URL",
    start="docker compose up -d redis",
    read=lambda: os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15"),
)

# The compatibility source v2_30_pg18, whose role may create databases. At
# 127.0.0.1: `localhost` on Windows tries IPv6 first and waits out every
# connection attempt.
TIMESCALE = Server(
    name="TimescaleDB for the metrics store",
    variable="TEST_METRICS_STORE_URL",
    start="docker compose -f backend/compatibility/timescale/compose.yml up -d v2_30_pg18",
    read=lambda: os.environ.get(
        "TEST_METRICS_STORE_URL",
        "postgresql://fixture_admin:fixture-only@127.0.0.1:55431/postgres",
    ),
)

SERVERS = (POSTGRES, REDIS, TIMESCALE)


def require_all() -> None:
    """Every server answers for the whole run, or the run does not start."""
    global _required
    missing = [server.absence() for server in SERVERS if not server.available()]
    if missing:
        _stop("--require-services: " + "; ".join(missing))
    _required = True


def _stop(reason: str) -> NoReturn:
    pytest.exit(reason, returncode=pytest.ExitCode.USAGE_ERROR)


def _where(url: str) -> str:
    """Host and port only: a URL carries the password."""
    parts = urlsplit(url)
    return f"{parts.hostname}:{parts.port or _protocol(parts.scheme).port}"


def _protocol(scheme: str) -> _Protocol:
    # `postgresql+psycopg` names the same server as `postgresql`.
    protocol = _PROTOCOLS.get(scheme.split("+")[0])
    if protocol is None:
        raise ValueError(f"no probe for {scheme}:// servers; add one to _PROTOCOLS")
    return protocol


@cache
def _answers(url: str) -> bool:
    parts = urlsplit(url)
    protocol = _protocol(parts.scheme)
    if parts.hostname is None:
        return False
    try:
        with socket.create_connection(
            (parts.hostname, parts.port or protocol.port), timeout=PROBE_SECONDS
        ) as connection:
            connection.sendall(protocol.hello)
            reply = connection.recv(1)
    except OSError:
        return False
    return reply.startswith(protocol.replies) and reply != b""
