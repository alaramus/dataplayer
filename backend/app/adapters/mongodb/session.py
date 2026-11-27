"""How to talk to a MongoDB server, through pymongo's asynchronous client (D283).

Knows about clients, addresses and the server's errors, and nothing about what
the caller wants; the catalog, the documents and everything after are built on
it. pymongo is imported by this package and by nothing else.
"""

import hashlib
import logging
import re
import time
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager, contextmanager
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

from pymongo import AsyncMongoClient
from pymongo.errors import (
    BulkWriteError,
    ConfigurationError,
    ConnectionFailure,
    ExecutionTimeout,
    NetworkTimeout,
    OperationFailure,
    ServerSelectionTimeoutError,
    WTimeoutError,
)

from app.adapters.cloud import CloudAccess
from app.adapters.mongodb.options import (
    MongodbAwsIam,
    MongodbOptions,
    MongodbSecretStore,
    MongodbSignIn,
    MongodbUserPassword,
)
from app.adapters.protocol import (
    AdapterError,
    ConnectionCheckResult,
    ErrorKind,
    NodeNotFound,
)
from app.adapters.resources import Pooling
from app.adapters.tls import (
    PROGRAM_PAIR,
    TlsFiles,
    TlsSettings,
    name_not_verifiable,
    program_paths,
)
from app.adapters.tunnels import TunnelAccess, reach
from app.adapters.update import RowConflict
from app.core.config import settings
from app.core.logs import record_failure, with_ref
from app.core.translation import N_, say

logger = logging.getLogger(__name__)

# How long a server may take to be found, and a connection to be made: the
# timeout of a direct attempt everywhere else.
SELECT_MILLISECONDS = 5000

# The oldest this source speaks to (D283): the oldest release whose catalog
# commands and aggregation stages everything here uses.
OLDEST = (5, 0)

# The server's error codes rather than its text, which quotes the user and
# sometimes the document.
AUTHENTICATION_FAILED = 18
UNAUTHORIZED = 13
NAMESPACE_NOT_FOUND = 26
MAX_TIME_EXPIRED = 50
DUPLICATE_KEY = 11000
DOCUMENT_VALIDATION_FAILURE = 121


class ServerProfile:
    def __init__(self, version: tuple[int, ...], text: str) -> None:
        self.version = version
        # "8.0.15": the number and nothing else.
        self.text = text

    @property
    def supported(self) -> bool:
        return self.version[: len(OLDEST)] >= OLDEST


_VERSION = re.compile(r"(\d+(?:\.\d+)*)")


def read_profile(version: str) -> ServerProfile:
    found = _VERSION.search(version)
    text = found.group(1) if found else "0"
    return ServerProfile(tuple(int(part) for part in text.split(".")), text)


def classify(
    exc: BaseException, *, fallback_message: str = N_("Connection failed")
) -> tuple[ErrorKind, str]:
    """Reduce a failure to a safe (kind, message) pair (D184)."""
    if isinstance(exc, ExecutionTimeout | NetworkTimeout | WTimeoutError | TimeoutError):
        return "timeout", say("The server did not answer in time")
    if isinstance(exc, OperationFailure):
        if exc.code == AUTHENTICATION_FAILED:
            return "auth", say("Authentication failed")
        if exc.code == UNAUTHORIZED:
            return "auth", say("The server does not let this user do that")
        if exc.code == MAX_TIME_EXPIRED:
            return "timeout", say("The server did not answer in time")
    if isinstance(exc, ServerSelectionTimeoutError | ConnectionFailure | OSError):
        return "network", say("Could not reach the database server")
    if isinstance(exc, ConfigurationError):
        return "config", say("The connection settings are not usable")
    ref = record_failure(logger, f"MongoDB: {fallback_message}", exc)
    return "unknown", with_ref(say(fallback_message), ref)


def named_refusal(exc: BaseException, refusals: Mapping[int, str] | None) -> str | None:
    """The caller's own sentence for an error code it anticipated, or nothing."""
    if refusals is None or not isinstance(exc, OperationFailure):
        return None
    code = exc.code
    if isinstance(exc, BulkWriteError):
        errors = exc.details.get("writeErrors") or [{}]
        code = errors[0].get("code")
    if code is None:
        return None
    named = refusals.get(code)
    return None if named is None else say(named)


def compose_url(
    *,
    host: str,
    port: int | None = None,
    user: str = "",
    database: str = "",
    auth_source: str = "",
    tls: bool = False,
    tls_query: Sequence[tuple[str, str]] = (),
) -> str:
    """A MongoDB address, every part quoted, as `mongosh` accepts it.

    `tls_query` is what a program needs beyond `tls=true`: its files and how
    much it checks (`program_tls`).
    """
    authority = f"[{host}]" if ":" in host else quote(host, safe="")
    if user != "":
        authority = f"{quote(user, safe='')}@{authority}"
    if port is not None:
        authority += f":{port}"
    url = f"mongodb://{authority}/"
    if database != "":
        url += quote(database, safe="")
    query: list[str] = []
    if user != "" and auth_source != "":
        query.append(f"authSource={quote(auth_source, safe='')}")
    if tls:
        query.append("tls=true")
        query += [f"{name}={quote(value, safe='/')}" for name, value in tls_query]
    return url + ("?" + "&".join(query) if query else "")


def compose_url_with_password(
    *,
    host: str,
    port: int | None = None,
    user: str = "",
    database: str = "",
    auth_source: str = "",
    tls: bool = False,
    tls_query: Sequence[tuple[str, str]] = (),
    password: str = "",
) -> str:
    """The same address with the password in it, for somebody to paste (D89)."""
    plain = compose_url(
        host=host,
        port=port,
        user=user,
        database=database,
        auth_source=auth_source,
        tls=tls,
        tls_query=tls_query,
    )
    if password == "" or user == "":
        return plain
    named = quote(user, safe="")
    return plain.replace(f"//{named}@", f"//{named}:{quote(password, safe='')}@", 1)


_TRUE_WORDS = frozenset({"1", "true", "yes", "on"})


def options_from_url(url: str) -> dict[str, Any]:
    """A connection string taken apart into the fields of the form.

    `mongodb://` with one host. A seed list and `mongodb+srv://` name a
    replica set to discover, which this source does not do (D283).
    """
    text = url.strip()
    if text.lower().startswith("mongodb+srv://"):
        raise ValueError(
            say("A mongodb+srv address is not supported; name one server with mongodb://")
        )
    if not text.lower().startswith("mongodb://"):
        raise ValueError(say("That is not a MongoDB connection string"))
    if "," in text.split("/", 3)[2]:
        raise ValueError(say("Name one server; a list of servers is not supported"))
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        raise ValueError(say("The connection string names no usable port")) from None
    if not parts.hostname:
        raise ValueError(say("The connection string names no host"))
    query = parse_qs(parts.query)
    tls = any(
        value.lower() in _TRUE_WORDS for value in query.get("tls", []) + query.get("ssl", [])
    )
    options: dict[str, Any] = {
        "host": unquote(parts.hostname),
        "tls_mode": "verify_full" if tls else "disabled",
    }
    if port is not None:
        options["port"] = port
    database = unquote(parts.path.lstrip("/"))
    if database:
        options["database"] = database
    if parts.username:
        options["auth_method"] = "user_password"
        options["user"] = unquote(parts.username)
        options["password"] = unquote(parts.password or "")
        options["auth_source"] = next(iter(query.get("authSource", [])), "") or database or "admin"
    else:
        options["auth_method"] = "no_password"
    return options


type Client = AsyncMongoClient[dict[str, Any]]


def make_client(
    host: str, port: int, options: MongodbOptions, signed: MongodbSignIn, *, pool_size: int
) -> Client:
    """A client of one server, as it is (D283).

    `directConnection`: the server named is the server spoken to, whether it
    is alone or one member of a replica set, so a tunnel's end is not traded
    for the names the set calls its members by. Moments come back aware and in
    UTC, and a UUID is the standard binary subtype.
    """
    credentials: dict[str, Any] = {}
    if signed.user:
        credentials = {
            "username": signed.user,
            "password": signed.password,
            "authSource": signed.auth_source,
        }
    if signed.mechanism:
        credentials["authMechanism"] = signed.mechanism
    if signed.session_token:
        credentials["authMechanismProperties"] = {"AWS_SESSION_TOKEN": signed.session_token}
    # pymongo reads its files once, while the client is made (D447).
    with TlsFiles(options.tls()) as files:
        return AsyncMongoClient(
            host=host,
            port=port,
            directConnection=True,
            serverSelectionTimeoutMS=SELECT_MILLISECONDS,
            connectTimeoutMS=SELECT_MILLISECONDS,
            tz_aware=True,
            uuidRepresentation="standard",
            appname="DataPlayer",
            maxPoolSize=pool_size,
            connect=False,
            **_tls_arguments(options.tls(), files),
            **credentials,
        )


def _tls_arguments(settings: TlsSettings, files: TlsFiles) -> dict[str, Any]:
    """pymongo's words for the TLS block (D446)."""
    if not settings.enabled:
        return {"tls": False}
    found: dict[str, Any] = {"tls": True}
    if settings.mode == "required":
        found["tlsAllowInvalidCertificates"] = True
    elif settings.mode == "verify_ca":
        found["tlsAllowInvalidHostnames"] = True
    if files.ca is not None and settings.verifies:
        found["tlsCAFile"] = str(files.ca)
    if files.pair is not None:
        found["tlsCertificateKeyFile"] = str(files.pair)
    return found


def auth_query(signed: MongodbSignIn) -> list[tuple[str, str]]:
    """The mechanism in a program's address, MONGODB-AWS's session token too."""
    found: list[tuple[str, str]] = []
    if signed.mechanism:
        found.append(("authMechanism", signed.mechanism))
    if signed.session_token:
        found.append(("authMechanismProperties", f"AWS_SESSION_TOKEN:{signed.session_token}"))
    return found


def program_tls(settings: TlsSettings) -> list[tuple[str, str]]:
    """The same, as a program's address names it, its files where
    `tls.with_program_files` writes them."""
    if not settings.enabled:
        return []
    found: list[tuple[str, str]] = []
    if settings.mode == "required":
        found.append(("tlsAllowInvalidCertificates", "true"))
    elif settings.mode == "verify_ca":
        found.append(("tlsAllowInvalidHostnames", "true"))
    paths = program_paths(settings)
    if paths.ca is not None and settings.verifies:
        found.append(("tlsCAFile", paths.ca))
    if paths.certificate is not None:
        # mongosh takes the certificate and its key as one file.
        found.append(("tlsCertificateKeyFile", PROGRAM_PAIR))
    return found



class KeptClient:
    """A client held in the resource store; it is a pool of its own."""

    def __init__(self, client: Client) -> None:
        self.client = client

    async def close(self) -> None:
        await self.client.close()


class MongodbSession:
    """How to talk to one MongoDB server."""

    def __init__(
        self,
        options: MongodbOptions,
        pooling: Pooling | None = None,
        tunnels: TunnelAccess | None = None,
        cloud: CloudAccess | None = None,
    ) -> None:
        self._options = options
        self._pooling = pooling
        self._tunnels = tunnels
        # Asked as a client is made, by a variant whose keys are issued (D449).
        self._cloud = cloud
        self._profile: ServerProfile | None = None

    @property
    def options(self) -> MongodbOptions:
        return self._options

    async def credentials(self) -> MongodbSignIn:
        """Who signs in, asked as a client is made: AWS's keys may be a
        role's, good for an hour (D449)."""
        return await self._options.sign_in(self._cloud)

    def connection_string(self) -> str:
        """The address for a person to copy, with the user the form names."""
        options = self._options
        user = options.user if isinstance(options, MongodbUserPassword | MongodbSecretStore) else ""
        auth_source = (
            options.auth_source
            if isinstance(options, MongodbUserPassword | MongodbSecretStore)
            else "$external" if isinstance(options, MongodbAwsIam) else ""
        )
        return compose_url(
            host=options.host,
            port=options.port,
            user=user,
            database=options.database,
            auth_source=auth_source,
            tls=options.tls().enabled,
        )

    def database(self) -> str:
        """The database the connection names, or nothing when it names none."""
        return self._options.database

    async def _address(self) -> tuple[str, int]:
        options = self._options
        # pymongo checks the name it dialled, a tunnel's loopback (D448).
        name_not_verifiable(options.tls(), options.ssh_tunnel)
        return await reach(self._tunnels, options.ssh_tunnel, options.host, options.port)

    @asynccontextmanager
    async def client(self) -> AsyncIterator[Client]:
        """A client to ask through: the connector's kept one when there is one.

        Asked for the address every time, so a tunnel that moved is followed;
        the address is part of the key, and a moved tunnel is a new client.
        """
        host, port = await self._address()
        signed = await self.credentials()
        if self._pooling is not None:
            store = self._pooling.store
            # pymongo signs every connection of a client with what it was
            # made with, so the client is keyed by them: a role's keys,
            # renewed, make a new client, and the old one goes when idle.
            fingerprint = hashlib.sha256(
                f"{host}:{port}:{self._options.tls().fingerprint()}:{signed.user}:"
                f"{signed.password}:{signed.auth_source}:{signed.mechanism}:"
                f"{signed.session_token}".encode()
            ).hexdigest()[:16]
            key = f"mongodb:{self._pooling.connector_id}:{fingerprint}"
            kept: KeptClient | None
            if store.keeps:

                async def create() -> KeptClient:
                    return KeptClient(
                        make_client(
                            host, port, self._options, signed, pool_size=settings.POOL_MAX_SIZE
                        )
                    )

                kept = await store.get_or_create(key, KeptClient, create)
            else:
                kept = await store.existing(key, KeptClient)
            if kept is not None:
                yield kept.client
                return
        client = make_client(host, port, self._options, signed, pool_size=2)
        try:
            yield client
        finally:
            await client.close()

    @contextmanager
    def failures(self, refusals: Mapping[int, str] | None = None) -> Iterator[None]:
        """Every driver failure inside, reduced to an `AdapterError` (D184).

        A refusal the caller anticipated by its code is a `ValueError` with the
        caller's sentence: the request was wrong, not the server.
        """
        try:
            yield
        except (AdapterError, NodeNotFound, ValueError, RowConflict):
            raise
        except Exception as exc:
            named = named_refusal(exc, refusals)
            if named is not None:
                raise ValueError(named) from None
            kind, message = classify(exc, fallback_message=N_("The server refused the request"))
            raise AdapterError(kind, message) from None

    async def check(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        try:
            host, port = await self._address()
            client = make_client(host, port, self._options, await self.credentials(), pool_size=1)
            try:
                build = await client.admin.command("buildInfo")
                # Authenticated as well as reachable: a server with access
                # control answers buildInfo to anybody.
                await client.admin.command(
                    "listDatabases", nameOnly=True, authorizedDatabases=True
                )
            finally:
                await client.close()
        except AdapterError as failure:
            return ConnectionCheckResult(
                ok=False, message=failure.message, error_kind=failure.error_kind
            )
        except OperationFailure as exc:
            if exc.code == UNAUTHORIZED and not isinstance(self._options, MongodbUserPassword):
                return ConnectionCheckResult(
                    ok=False,
                    message=say("The server asks for a user and a password"),
                    error_kind="auth",
                )
            error_kind, message = classify(exc)
            return ConnectionCheckResult(ok=False, message=message, error_kind=error_kind)
        except Exception as exc:
            error_kind, message = classify(exc)
            return ConnectionCheckResult(ok=False, message=message, error_kind=error_kind)
        profile = read_profile(str(build.get("version", "")))
        if not profile.supported:
            return ConnectionCheckResult(
                ok=False,
                message=say(
                    "MongoDB {version} is older than this source supports ({oldest})",
                    version=profile.text,
                    oldest=".".join(str(part) for part in OLDEST),
                ),
                error_kind="config",
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=latency_ms
        )

    async def profile(self) -> ServerProfile:
        """Which server this is; asked once per session and kept."""
        if self._profile is None:
            async with self.client() as client:
                with self.failures():
                    build = await client.admin.command("buildInfo")
            self._profile = read_profile(str(build.get("version", "")))
        return self._profile
