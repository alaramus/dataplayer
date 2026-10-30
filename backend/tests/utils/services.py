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

import bson
import pytest

from app.core.config import settings

# Long enough for a service container on a CI network, short enough that a
# refused port on Windows — which retries before it gives up — costs a second.
PROBE_SECONDS = 1.0


def _mongodb_hello() -> bytes:
    """An OP_MSG asking `hello`, which a server answers before authentication."""
    body = struct.pack("<I", 0) + b"\x00" + bson.encode({"hello": 1, "$db": "admin"})
    return struct.pack("<iiii", 16 + len(body), 1, 0, 2013) + body


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
    # An SSH server speaks first, with its version line; saying ours is polite
    # and changes nothing.
    "ssh": _Protocol(22, b"SSH-2.0-dataplayer-probe\r\n", (b"S",)),
    # MySQL and MariaDB speak first as well, with a handshake whose first byte
    # is its length: any byte at all is the server, and a closed socket is not.
    "mysql": _Protocol(3306, b"", (b"",)),
    # ClickHouse is spoken to over HTTP, and answers a ping without a password.
    "clickhouse": _Protocol(8123, b"GET /ping HTTP/1.0\r\n\r\n", (b"H",)),
    # MongoDB waits to be asked; its reply starts with its length.
    "mongodb": _Protocol(27017, _mongodb_hello(), (b"",)),
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

# The development SSH server (`sshd` in compose.override.yml), signing in as
# `dataplayer` with that password. A test that needs a key authorizes its own
# over SFTP first, so nothing about a key is kept in the repository.
SSH = Server(
    name="the SSH server",
    variable="TEST_SSH_URL",
    start="docker compose up -d sshd",
    read=lambda: os.environ.get(
        "TEST_SSH_URL", "ssh://dataplayer:dataplayer@127.0.0.1:2222"
    ),
)

# The development MySQL and MariaDB (`mysql` and `mariadb` in
# compose.override.yml), signing in as root. Both, because the one source
# type speaks to both and they differ where the catalog looks (D228).
MYSQL = Server(
    name="MySQL",
    variable="TEST_MYSQL_URL",
    start="docker compose up -d mysql",
    read=lambda: os.environ.get("TEST_MYSQL_URL", "mysql://root:dataplayer@127.0.0.1:3307"),
)

MARIADB = Server(
    name="MariaDB",
    variable="TEST_MARIADB_URL",
    start="docker compose up -d mariadb",
    read=lambda: os.environ.get(
        "TEST_MARIADB_URL", "mysql://root:dataplayer@127.0.0.1:3308"
    ),
)

# The development ClickHouse (`clickhouse` in compose.override.yml), signing
# in as `default`, over the HTTP interface (D267).
CLICKHOUSE = Server(
    name="ClickHouse",
    variable="TEST_CLICKHOUSE_URL",
    start="docker compose up -d clickhouse",
    read=lambda: os.environ.get(
        "TEST_CLICKHOUSE_URL", "clickhouse://default:dataplayer@127.0.0.1:8124"
    ),
)

# The development MongoDB (`mongodb` in compose.override.yml), signing in as
# root (D283).
MONGODB = Server(
    name="MongoDB",
    variable="TEST_MONGODB_URL",
    start="docker compose up -d mongodb",
    read=lambda: os.environ.get(
        "TEST_MONGODB_URL", "mongodb://root:dataplayer@127.0.0.1:27018/?authSource=admin"
    ),
)

SERVERS = (POSTGRES, REDIS, TIMESCALE, SSH, MYSQL, MARIADB, CLICKHOUSE, MONGODB)


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
