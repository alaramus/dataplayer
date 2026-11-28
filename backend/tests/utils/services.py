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
import ssl
import struct
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit

import bson
import pytest

from app.core.config import Settings, settings
from app.prepare_test_database import TEST_SUFFIX, database_name, suite_database_url

# Long enough for a service container on a CI network, short enough that a
# refused port on Windows — which retries before it gives up — costs a second.
PROBE_SECONDS = 1.0


def _mongodb_hello() -> bytes:
    """An OP_MSG asking `hello`, which a server answers before authentication."""
    body = struct.pack("<I", 0) + b"\x00" + bson.encode({"hello": 1, "$db": "admin"})
    return struct.pack("<iiii", 16 + len(body), 1, 0, 2013) + body


def _kafka_api_versions() -> bytes:
    """ApiVersions v0, which a broker answers before any authentication."""
    client = b"dataplayer-probe"
    body = struct.pack("!hhih", 18, 0, 1, len(client)) + client
    return struct.pack("!i", len(body)) + body


@dataclass(frozen=True)
class _Protocol:
    port: int
    hello: bytes
    # How the first byte of a live server's reply may start.
    replies: tuple[bytes, ...]
    # Said inside TLS, its certificate not checked: a server that speaks only
    # TLS closes a plain socket without a word.
    tls: bool = False


# A port that accepts is not a server that answers: Docker Desktop accepts on a
# published port as soon as the container runs, before the server inside
# listens, and then closes the connection. So the probe says hello in the
# server's own protocol and waits for a reply.
_PROTOCOLS = {
    # SSLRequest, the one message answered before authentication: S or N.
    "postgresql": _Protocol(5432, struct.pack("!ii", 8, 80877103), (b"S", b"N")),
    # PING is answered without the password too, if only with -NOAUTH.
    "redis": _Protocol(6379, b"PING\r\n", (b"+", b"-")),
    "rediss": _Protocol(6379, b"PING\r\n", (b"+", b"-"), tls=True),
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
    # ZooKeeper answers `srvr` on its client port before any session, with
    # "Zookeeper version: ...".
    "zookeeper": _Protocol(2181, b"srvr", (b"Z",)),
    # Kafka waits to be asked; its reply starts with its length.
    "kafka": _Protocol(9092, _kafka_api_versions(), (b"",)),
    # An AMQP 0-9-1 header is answered by Connection.Start, a method frame
    # whose type is 1.
    "amqp": _Protocol(5672, b"AMQP\x00\x00\x09\x01", (b"\x01",)),
    # CQL's OPTIONS in protocol 4, which a node answers before authentication
    # with SUPPORTED in a response frame of the same version.
    "cassandra": _Protocol(9042, b"\x04\x00\x00\x00\x05\x00\x00\x00\x00", (b"\x84",)),
    # An S3 store answers HTTP, if only with a refusal of an unsigned request.
    "s3": _Protocol(9000, b"GET / HTTP/1.0\r\n\r\n", (b"H",)),
    # An IMAP server speaks first, with its `* OK` greeting.
    "imap": _Protocol(143, b"", (b"*",)),
    # A Docker daemon with TLS answers plain HTTP with a 400 of its own.
    "docker": _Protocol(2376, b"GET /_ping HTTP/1.0\r\n\r\n", (b"H",)),
    "vault": _Protocol(8200, b"GET /v1/sys/health HTTP/1.0\r\n\r\n", (b"H",)),
    # A Kubernetes API server answers `/version` over TLS before anybody signs in.
    "kubernetes": _Protocol(6443, b"GET /version HTTP/1.0\r\n\r\n", (b"H",), tls=True),
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
    # A server the pipeline does not run: a product card's smoke test (D377).
    # Its tests are skipped even under --require-services.
    local: bool = False

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
        if _required and not self.local:
            pytest.fail(self.absence(), pytrace=False)
        pytest.skip(self.absence())

    def absence(self) -> str:
        return (
            f"{self.name} does not answer at {_where(self.url())}: "
            f"start it with `{self.start}` or set {self.variable}"
        )


def refuse_unless_suite_database(url: str) -> None:
    """The suite deletes every user when it ends, so it runs only in a
    database whose name ends in `_test`."""
    name = database_name(url)
    if not name.endswith(TEST_SUFFIX):
        raise pytest.UsageError(
            f"The suite deletes every user when it ends, so it does not run in {name!r}: "
            f"give it a database whose name ends in {TEST_SUFFIX}"
        )


def point_at_suite_database() -> None:
    """Choose the suite's database before anything opens one.

    The application's with `_test` after the name, made by
    `python -m app.prepare_test_database`, or TEST_DATABASE_URL. Called on
    import of `tests/utils/suite_database.py`, the first thing the conftest
    imports: `app.core.db` builds its engine when it is first imported.
    """
    wanted = os.environ.get("TEST_DATABASE_URL") or suite_database_url(str(settings.DATABASE_URL))
    refuse_unless_suite_database(wanted)
    # Read through Settings, so the address becomes psycopg's as the
    # application's own does.
    settings.DATABASE_URL = Settings(DATABASE_URL=wanted).DATABASE_URL
    # And for any program the suite starts, which reads the environment.
    os.environ["DATABASE_URL"] = str(settings.DATABASE_URL)


POSTGRES = Server(
    name="the suite's database",
    variable="TEST_DATABASE_URL",
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

# A Docker daemon behind an SSH server (`docker-remote` in
# compose.override.yml), signing in as `dataplayer` with that password; the
# daemon's socket is /var/run/docker.sock there (D405).
DOCKER_REMOTE = Server(
    name="the Docker daemon behind SSH",
    variable="TEST_DOCKER_REMOTE_URL",
    start="docker compose up -d docker-remote",
    read=lambda: os.environ.get(
        "TEST_DOCKER_REMOTE_URL", "ssh://dataplayer:dataplayer@127.0.0.1:2223"
    ),
)

# A Docker daemon on TCP with mutual TLS (`docker-tls` in compose.override.yml),
# which makes its own CA and certificates on first start (D418).
DOCKER_TLS = Server(
    name="the Docker daemon on TCP with TLS",
    variable="TEST_DOCKER_TLS_URL",
    start="docker compose up -d docker-tls",
    read=lambda: os.environ.get("TEST_DOCKER_TLS_URL", "docker://127.0.0.1:2376"),
)


# A one-node k3s (`k3s` in compose.override.yml), which writes an
# administrator's kubeconfig into deploy/k3s on first start (D463).
K3S = Server(
    name="the k3s Kubernetes cluster",
    variable="TEST_K3S_URL",
    start="docker compose up -d k3s",
    read=lambda: os.environ.get("TEST_K3S_URL", "kubernetes://127.0.0.1:6443"),
)


def k3s_kubeconfig() -> Path:
    """Where k3s left its administrator's kubeconfig."""
    return Path(
        os.environ.get(
            "TEST_K3S_KUBECONFIG",
            str(Path(__file__).resolve().parents[3] / "deploy/k3s/kubeconfig"),
        )
    )


def docker_tls_certificates() -> Path:
    """Where the TLS daemon left its client's ca.pem, cert.pem and key.pem."""
    return Path(
        os.environ.get(
            "TEST_DOCKER_TLS_CERTS",
            str(Path(__file__).resolve().parents[3] / "deploy/docker-tls/certs/client"),
        )
    )


# A PostgreSQL that accepts only TLS, and Redis that speaks only TLS with an
# ACL user, both with certificates pg-tls makes on first start (`pg-tls` and
# `redis-tls` in compose.override.yml, D446).
PG_TLS = Server(
    name="the PostgreSQL that accepts only TLS",
    variable="TEST_PG_TLS_URL",
    start="docker compose up -d pg-tls",
    read=lambda: os.environ.get(
        "TEST_PG_TLS_URL", "postgresql://postgres:dataplayer@127.0.0.1:5442/postgres"
    ),
)
REDIS_TLS = Server(
    name="the Redis that speaks only TLS",
    variable="TEST_REDIS_TLS_URL",
    start="docker compose up -d redis-tls",
    read=lambda: os.environ.get("TEST_REDIS_TLS_URL", "rediss://reader:dataplayer@127.0.0.1:6390/0"),
)


def tls_test_certificates() -> Path:
    """Where pg-tls left its ca.crt, client.crt, client.key and client-encrypted.key."""
    return Path(
        os.environ.get(
            "TEST_TLS_CERTS",
            str(Path(__file__).resolve().parents[3] / "deploy/tls-test/certs"),
        )
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

# The development ZooKeeper (`zookeeper` in compose.override.yml), which asks
# for no authentication (D297).
ZOOKEEPER = Server(
    name="ZooKeeper",
    variable="TEST_ZOOKEEPER_URL",
    start="docker compose up -d zookeeper",
    read=lambda: os.environ.get("TEST_ZOOKEEPER_URL", "zookeeper://127.0.0.1:2182"),
)

# The development Kafka (`kafka` in compose.override.yml), at the listener it
# advertises to this machine; the SASL listener is the next port (D304).
KAFKA = Server(
    name="Kafka",
    variable="TEST_KAFKA_URL",
    start="docker compose up -d kafka",
    read=lambda: os.environ.get("TEST_KAFKA_URL", "kafka://127.0.0.1:9094"),
)

# The development RabbitMQ (`rabbitmq` in compose.override.yml). Its management
# API answers 10000 ports above AMQP, as RabbitMQ's own defaults do (D325).
RABBITMQ = Server(
    name="RabbitMQ",
    variable="TEST_RABBITMQ_URL",
    start="docker compose up -d rabbitmq",
    read=lambda: os.environ.get(
        "TEST_RABBITMQ_URL", "amqp://dataplayer:dataplayer@127.0.0.1:5673"
    ),
)

# The development Cassandra and ScyllaDB (`cassandra` and `scylla` in
# compose.override.yml), signing in as `cassandra`. Both, because the one
# source type speaks to both (D340); on a machine short of memory one runs at
# a time and the other's tests are skipped.
CASSANDRA = Server(
    name="Cassandra",
    variable="TEST_CASSANDRA_URL",
    start="docker compose up -d cassandra",
    read=lambda: os.environ.get(
        "TEST_CASSANDRA_URL", "cassandra://cassandra:cassandra@127.0.0.1:9043"
    ),
)

SCYLLA = Server(
    name="ScyllaDB",
    variable="TEST_SCYLLA_URL",
    start="docker compose up -d scylla",
    read=lambda: os.environ.get(
        "TEST_SCYLLA_URL", "cassandra://cassandra:cassandra@127.0.0.1:9044"
    ),
)

# The development mail server (`greenmail` in compose.override.yml): IMAP here,
# SMTP on the port the query names, mailboxes alice@ and bob@example.com with
# the password `dataplayer` (D368).
MAIL = Server(
    name="the mail server",
    variable="TEST_MAIL_URL",
    start="docker compose up -d greenmail",
    read=lambda: os.environ.get("TEST_MAIL_URL", "imap://127.0.0.1:3143?smtp=3025"),
)

# The development S3 store (`rustfs` in compose.override.yml), with the access
# key and secret in the address and plain HTTP (D382).
# Vault in dev mode (`vault` in compose.override.yml, D454): the root token is
# the URL's user. It reaches PostgreSQL as `db` in both compose and CI.
VAULT = Server(
    name="the Vault dev server",
    variable="TEST_VAULT_URL",
    start="docker compose up -d vault",
    read=lambda: os.environ.get("TEST_VAULT_URL", "vault://dataplayer@127.0.0.1:8210"),
)

S3 = Server(
    name="the S3 store",
    variable="TEST_S3_URL",
    start="docker compose up -d rustfs",
    read=lambda: os.environ.get(
        "TEST_S3_URL", "s3://dataplayer:dataplayer-secret@127.0.0.1:9010"
    ),
)

# Products that are a card of a type (D377), started by
# `docker compose up -d valkey keydb redpanda percona citus paradedb`.
VALKEY = Server(
    name="Valkey",
    variable="TEST_VALKEY_URL",
    start="docker compose up -d valkey",
    read=lambda: os.environ.get("TEST_VALKEY_URL", "redis://:dataplayer@127.0.0.1:6380/15"),
    local=True,
)

KEYDB = Server(
    name="KeyDB",
    variable="TEST_KEYDB_URL",
    start="docker compose up -d keydb",
    read=lambda: os.environ.get("TEST_KEYDB_URL", "redis://:dataplayer@127.0.0.1:6381/15"),
    local=True,
)

REDPANDA = Server(
    name="Redpanda",
    variable="TEST_REDPANDA_URL",
    start="docker compose up -d redpanda",
    read=lambda: os.environ.get("TEST_REDPANDA_URL", "kafka://127.0.0.1:9096"),
    local=True,
)

PERCONA = Server(
    name="Percona Server",
    variable="TEST_PERCONA_URL",
    start="docker compose up -d percona",
    read=lambda: os.environ.get("TEST_PERCONA_URL", "mysql://root:dataplayer@127.0.0.1:3309"),
    local=True,
)

CITUS = Server(
    name="Citus",
    variable="TEST_CITUS_URL",
    start="docker compose up -d citus",
    read=lambda: os.environ.get(
        "TEST_CITUS_URL", "postgresql://postgres:dataplayer@127.0.0.1:5434/postgres"
    ),
    local=True,
)

PARADEDB = Server(
    name="ParadeDB",
    variable="TEST_PARADEDB_URL",
    start="docker compose up -d paradedb",
    read=lambda: os.environ.get(
        "TEST_PARADEDB_URL", "postgresql://postgres:dataplayer@127.0.0.1:5435/postgres"
    ),
    local=True,
)

# Products that are a card with a list of what they lack (D378), started by
# `docker compose up -d dragonfly tidb`.
DRAGONFLY = Server(
    name="Dragonfly",
    variable="TEST_DRAGONFLY_URL",
    start="docker compose up -d dragonfly",
    read=lambda: os.environ.get("TEST_DRAGONFLY_URL", "redis://:dataplayer@127.0.0.1:6382/15"),
    local=True,
)

TIDB = Server(
    name="TiDB",
    variable="TEST_TIDB_URL",
    start="docker compose up -d tidb",
    read=lambda: os.environ.get("TEST_TIDB_URL", "mysql://root:dataplayer@127.0.0.1:4001"),
    local=True,
)

SERVERS = (
    POSTGRES,
    REDIS,
    TIMESCALE,
    SSH,
    DOCKER_REMOTE,
    DOCKER_TLS,
    K3S,
    PG_TLS,
    REDIS_TLS,
    MYSQL,
    MARIADB,
    CLICKHOUSE,
    MONGODB,
    ZOOKEEPER,
    KAFKA,
    RABBITMQ,
    CASSANDRA,
    SCYLLA,
    MAIL,
    S3,
    VAULT,
    VALKEY,
    KEYDB,
    REDPANDA,
    PERCONA,
    CITUS,
    PARADEDB,
    DRAGONFLY,
    TIDB,
)


def require_all() -> None:
    """Every server answers for the whole run, or the run does not start."""
    global _required
    missing = [
        server.absence()
        for server in SERVERS
        if not server.local and not server.available()
    ]
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
def _unverified() -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _answers(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme == "mongodb+srv":
        # A DNS seed list names no server to knock on (D457): the driver finds
        # them, and a test against Atlas is asked for by setting the address.
        return parts.hostname is not None
    protocol = _protocol(parts.scheme)
    if parts.hostname is None:
        return False
    try:
        with socket.create_connection(
            (parts.hostname, parts.port or protocol.port), timeout=PROBE_SECONDS
        ) as plain:
            connection = _unverified().wrap_socket(plain) if protocol.tls else plain
            connection.sendall(protocol.hello)
            reply = connection.recv(1)
    except OSError:
        return False
    return reply.startswith(protocol.replies) and reply != b""
