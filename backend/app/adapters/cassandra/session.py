"""How to talk to a Cassandra or ScyllaDB node over CQL (D340).

Knows about clusters, statements and the server's errors, and nothing about
what the caller wants; the catalog, the rows and everything after are built on
it. The driver keeps its connections on a loop of its own in a thread; a
statement is waited for on the application's loop through the driver's
callbacks, so no thread is held while the server works.
"""

import asyncio
import hashlib
import logging
import re
import ssl
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

from cassandra import (
    AuthenticationFailed,
    ConsistencyLevel,
    InvalidRequest,
    OperationTimedOut,
    ReadTimeout,
    Unauthorized,
    Unavailable,
    WriteTimeout,
)
from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import (
    EXEC_PROFILE_DEFAULT,
    Cluster,
    ExecutionProfile,
    NoHostAvailable,
    ResponseFuture,
    Session,
    ShardAwareOptions,
)
from cassandra.policies import AddressTranslator, HostDistance, LoadBalancingPolicy
from cassandra.protocol import ConfigurationException, SyntaxException
from cassandra.query import PreparedStatement, SimpleStatement, tuple_factory

from app.adapters.cassandra.options import (
    CassandraOptions,
    CassandraUserPassword,
    Consistency,
)
from app.adapters.cassandra.types import driver_value
from app.adapters.protocol import AdapterError, ConnectionCheckResult, ErrorKind
from app.adapters.resources import Pooling
from app.adapters.tunnels import TunnelAccess, reach
from app.core.logs import record_failure, with_ref
from app.core.translation import N_, say

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 5.0
# How long one statement may take before the driver gives up on it. A page of
# a big table filtered outside its key reads the table, so longer than a
# connection.
REQUEST_TIMEOUT_SECONDS = 30.0

# The oldest servers this source speaks to (D340): both describe a schema on
# the server, which the DDL view reads.
OLDEST_CASSANDRA = (4, 0)
OLDEST_SCYLLA = (5, 4)

_LEVELS: dict[Consistency, int] = {
    "ONE": ConsistencyLevel.ONE,
    "LOCAL_ONE": ConsistencyLevel.LOCAL_ONE,
    "QUORUM": ConsistencyLevel.QUORUM,
    "LOCAL_QUORUM": ConsistencyLevel.LOCAL_QUORUM,
    "EACH_QUORUM": ConsistencyLevel.EACH_QUORUM,
    "ALL": ConsistencyLevel.ALL,
}

# A ScyllaDB release with tablets answers its version here; Cassandra has no
# such table, and ScyllaDB's `release_version` is a compatibility 3.0.8.
_SCYLLA_VERSION = "SELECT version FROM system.versions WHERE key = 'local'"
_RELEASE = "SELECT release_version, cluster_name, data_center FROM system.local"


@dataclass(frozen=True)
class ServerProfile:
    """What the node is: which product, and its version."""

    scylla: bool
    version: tuple[int, ...]
    # "5.0.9" or "2026.3.5": the number and nothing else.
    text: str
    cluster_name: str = ""
    data_center: str = ""

    @property
    def product(self) -> str:
        return "ScyllaDB" if self.scylla else "Cassandra"

    @property
    def oldest(self) -> tuple[int, int]:
        return OLDEST_SCYLLA if self.scylla else OLDEST_CASSANDRA

    @property
    def supported(self) -> bool:
        return self.version[:2] >= self.oldest


_VERSION = re.compile(r"(\d+(?:\.\d+)*)")


def read_profile(
    release: str,
    scylla_version: str | None,
    cluster_name: str = "",
    data_center: str = "",
) -> ServerProfile:
    found = _VERSION.search(scylla_version if scylla_version is not None else release)
    text = found.group(1) if found else "0"
    return ServerProfile(
        scylla=scylla_version is not None,
        version=tuple(int(part) for part in text.split(".")),
        text=text,
        cluster_name=cluster_name,
        data_center=data_center,
    )


def _all_refused_sign_in(exc: NoHostAvailable) -> bool:
    errors = list(exc.errors.values()) if isinstance(exc.errors, dict) else []
    return bool(errors) and all(
        isinstance(error, AuthenticationFailed) for error in errors
    )


def _asks_for_sign_in(exc: NoHostAvailable) -> bool:
    errors = list(exc.errors.values()) if isinstance(exc.errors, dict) else []
    # The driver's own words when a server wants credentials it was not given.
    return any("requires authentication" in str(error) for error in errors)


def classify(
    exc: BaseException, *, fallback_message: str = N_("Connection failed")
) -> tuple[ErrorKind, str]:
    """Reduce a failure to a safe (kind, message) pair (D184).

    By the driver's exception classes, never by their text, which quotes the
    statement and sometimes the address.
    """
    if isinstance(exc, AdapterError):
        return exc.error_kind, exc.message
    if isinstance(exc, NoHostAvailable):
        if _all_refused_sign_in(exc):
            return "auth", say("Authentication failed")
        if _asks_for_sign_in(exc):
            return "auth", say("The server asks for a user and a password")
        return "network", say("Could not reach the database server")
    if isinstance(exc, AuthenticationFailed):
        return "auth", say("Authentication failed")
    if isinstance(exc, Unauthorized):
        return "auth", say("The server does not let this user do that")
    if isinstance(exc, OperationTimedOut | ReadTimeout | WriteTimeout | TimeoutError):
        return "timeout", say("The server did not answer in time")
    if isinstance(exc, Unavailable):
        return "network", say(
            "Not enough replicas are up for the consistency level asked"
        )
    if isinstance(exc, OSError):
        return "network", say("Could not reach the database server")
    ref = record_failure(logger, f"Cassandra: {fallback_message}", exc)
    return "unknown", with_ref(say(fallback_message), ref)


def is_refusal(exc: BaseException) -> bool:
    """The server read the statement and refused it, rather than failing to answer."""
    return isinstance(exc, InvalidRequest | SyntaxException | ConfigurationException)


def refusal_text(exc: BaseException) -> str:
    """The server's own sentence for a refused statement, without the driver's frame.

    A refusal names the statement's own parts and nothing about the connection,
    so the console and a filter may show it.
    """
    message = getattr(exc, "message", None)
    text = message if isinstance(message, str) else str(exc)
    found = re.search(r'message="(.*)"', text, re.DOTALL)
    return (found.group(1) if found else text).strip()


def quoted_name(*parts: str) -> str:
    """A name quoted for CQL, each part apart: "keyspace"."table"."""
    return ".".join('"' + part.replace('"', '""') + '"' for part in parts)


_SECURE_WORDS = frozenset({"1", "true", "yes", "on"})
_SCHEMES = ("cassandra", "scylla", "scylladb", "cql")


def compose_url(
    *,
    host: str,
    port: int | None = None,
    user: str = "",
    keyspace: str = "",
    secure: bool = False,
) -> str:
    """A Cassandra address, quoted part by part for the reason MySQL's is."""
    authority = quote(host, safe="") if ":" not in host else f"[{host}]"
    if user != "":
        authority = f"{quote(user, safe='')}@{authority}"
    if port is not None:
        authority += f":{port}"
    url = f"cassandra://{authority}"
    if keyspace != "":
        url += f"/{quote(keyspace, safe='')}"
    return url + "?ssl=true" if secure else url


def compose_url_with_password(
    *,
    host: str,
    port: int | None = None,
    user: str = "",
    keyspace: str = "",
    secure: bool = False,
    password: str = "",
) -> str:
    """The same address with the password in it, for somebody to paste (D89)."""
    plain = compose_url(
        host=host, port=port, user=user, keyspace=keyspace, secure=secure
    )
    if password == "" or user == "":
        return plain
    named = quote(user, safe="")
    return plain.replace(f"{named}@", f"{named}:{quote(password, safe='')}@", 1)


def options_from_url(url: str) -> dict[str, Any]:
    """A connection string taken apart into the fields of the form.

    `cassandra://`, `scylla://` and `cql://`; `?ssl=true` is TLS, and
    `?consistency=` names a level.
    """
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        raise ValueError(say("The connection string names no usable port")) from None
    if parts.scheme.lower() not in _SCHEMES:
        raise ValueError(say("That is not a Cassandra connection string"))
    if not parts.hostname:
        raise ValueError(say("The connection string names no host"))
    query = parse_qs(parts.query)
    secure = any(
        value.lower() in _SECURE_WORDS
        for key in ("ssl", "tls", "secure")
        for value in query.get(key, [])
    )
    options: dict[str, Any] = {"host": unquote(parts.hostname), "secure": secure}
    if port is not None:
        options["port"] = port
    keyspace = unquote(parts.path.lstrip("/")) or next(
        iter(query.get("keyspace", [])), ""
    )
    if keyspace:
        options["keyspace"] = keyspace
    level = next(iter(query.get("consistency", [])), "").upper()
    if level in _LEVELS:
        options["consistency"] = level
    if parts.username:
        options["auth_method"] = "user_password"
        options["user"] = unquote(parts.username)
        options["password"] = unquote(parts.password or "")
    else:
        options["auth_method"] = "no_password"
    return options


class _OneAddress(AddressTranslator):  # type: ignore[misc]  # the driver ships no types
    """Every node is the address dialled (D340).

    The driver reads each node's own address from the server and connects
    there; behind a published port, a NAT or an SSH tunnel that address is not
    reachable from here, and the one in the form is.
    """

    def __init__(self, address: str) -> None:
        self._address = address

    def translate(self, addr: str) -> str:
        return self._address


class _OneCoordinator(LoadBalancingPolicy):  # type: ignore[misc]  # the driver ships no types
    """One node to send to, since every node is the same address here.

    A pool per node would be several pools to the one address dialled. The
    first node that is up is used, and the next one when it goes down.
    """

    def __init__(self) -> None:
        super().__init__()
        self._hosts: list[Any] = []
        self._chosen: Any = None

    def populate(self, cluster: Any, hosts: Any) -> None:
        self._hosts = list(hosts)
        self._choose()

    def _choose(self) -> None:
        if (
            self._chosen is not None
            and self._chosen in self._hosts
            and self._chosen.is_up is not False
        ):
            return
        up = [host for host in self._hosts if host.is_up is not False]
        self._chosen = up[0] if up else (self._hosts[0] if self._hosts else None)

    def distance(self, host: Any) -> int:
        self._choose()
        return int(HostDistance.LOCAL if host is self._chosen else HostDistance.IGNORED)

    def make_query_plan(self, working_keyspace: Any = None, query: Any = None) -> Any:
        self._choose()
        return iter([self._chosen] if self._chosen is not None else [])

    def on_up(self, host: Any) -> None:
        if host not in self._hosts:
            self._hosts.append(host)
        self._choose()

    def on_down(self, host: Any) -> None:
        if host is self._chosen:
            self._chosen = None
        self._choose()

    def on_add(self, host: Any) -> None:
        self.on_up(host)

    def on_remove(self, host: Any) -> None:
        if host in self._hosts:
            self._hosts.remove(host)
        self.on_down(host)


def _profile(level: Consistency) -> ExecutionProfile:
    return ExecutionProfile(
        load_balancing_policy=_OneCoordinator(),
        consistency_level=_LEVELS[level],
        request_timeout=REQUEST_TIMEOUT_SECONDS,
        row_factory=tuple_factory,
    )


def make_cluster(options: CassandraOptions, address: tuple[str, int]) -> Cluster:
    host, port = address
    auth = (
        PlainTextAuthProvider(options.user, options.password.get_secret_value())
        if isinstance(options, CassandraUserPassword)
        else None
    )
    tls: dict[str, Any] = {}
    if options.secure:
        context = ssl.create_default_context()
        # The name the certificate is for is the server's, also when the
        # connection goes to this end of an SSH tunnel (D282).
        tls = {"ssl_context": context, "ssl_options": {"server_hostname": options.host}}
    return Cluster(
        contact_points=[host],
        port=port,
        auth_provider=auth,
        execution_profiles={EXEC_PROFILE_DEFAULT: _profile(options.consistency)},
        address_translator=_OneAddress(host),
        # A second port per shard that nobody published (D340).
        shard_aware_options=ShardAwareOptions(disable=True),
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        control_connection_timeout=CONNECT_TIMEOUT_SECONDS,
        # The catalog reads `system_schema` itself, when it is asked; the
        # driver's own copy of every schema is a long read at every connect.
        schema_metadata_enabled=False,
        token_metadata_enabled=False,
        # Dropped at the first failure rather than retried in the background:
        # the next request connects again.
        reconnection_policy=None,
        **tls,
    )


@dataclass
class Answer:
    """What one page of a statement answered."""

    names: list[str]
    types: list[Any]
    rows: list[tuple[Any, ...]]
    paging_state: bytes | None = None

    def dicts(self) -> list[dict[str, Any]]:
        return [dict(zip(self.names, row, strict=True)) for row in self.rows]


async def waited(future: ResponseFuture) -> Answer:
    """A page the driver answers on its own thread, waited for on this loop."""
    loop = asyncio.get_running_loop()
    done: asyncio.Future[None] = loop.create_future()

    def settle(*_: Any) -> None:
        if not done.done():
            done.set_result(None)

    def call(*_: Any) -> None:
        loop.call_soon_threadsafe(settle)

    future.add_callbacks(call, call)
    await done
    # Settled, so `result` hands over what is already there.
    result = future.result()
    names = list(result.column_names or [])
    return Answer(
        names=names,
        types=list(result.column_types or []),
        rows=list(result.current_rows),
        paging_state=result.paging_state,
    )


@dataclass
class PageStates:
    """Where each page a relation was read in ended (D342).

    Keyed by everything that makes two reads different, then by the offset
    the state goes on from. Bounded both ways: a few reads, a few hundred
    positions each.
    """

    reads: OrderedDict[str, dict[int, bytes]] = field(default_factory=OrderedDict)
    max_reads: int = 64
    max_positions: int = 512

    def nearest(self, read: str, offset: int) -> tuple[int, bytes | None]:
        positions = self.reads.get(read)
        if not positions:
            return 0, None
        self.reads.move_to_end(read)
        before = [position for position in positions if position <= offset]
        if not before:
            return 0, None
        best = max(before)
        return best, positions[best]

    def keep(self, read: str, offset: int, state: bytes) -> None:
        positions = self.reads.setdefault(read, {})
        self.reads.move_to_end(read)
        positions[offset] = state
        if len(positions) > self.max_positions:
            del positions[min(positions)]
        while len(self.reads) > self.max_reads:
            self.reads.popitem(last=False)


class KeptCluster:
    """A cluster held in the resource store, connected on first use.

    Connecting happens outside the store's lock: the store makes this empty
    holder, and the first request through it connects under a lock of its own.
    """

    def __init__(self, options: CassandraOptions, address: tuple[str, int]) -> None:
        self._options = options
        self._address = address
        self._cluster: Cluster | None = None
        self._session: Session | None = None
        self._lock = asyncio.Lock()
        self._prepared: OrderedDict[str, PreparedStatement] = OrderedDict()
        self.profile: ServerProfile | None = None
        self.pages = PageStates()

    async def session(self) -> Session:
        if self._session is not None and not self._session.is_shutdown:
            return self._session
        async with self._lock:
            if self._session is not None and not self._session.is_shutdown:
                return self._session
            cluster = make_cluster(self._options, self._address)
            try:
                self._session = await asyncio.to_thread(cluster.connect)
            except BaseException:
                await asyncio.to_thread(cluster.shutdown)
                raise
            self._cluster = cluster
            return self._session

    async def prepared(self, text: str) -> PreparedStatement:
        found = self._prepared.get(text)
        if found is not None:
            self._prepared.move_to_end(text)
            return found
        session = await self.session()
        statement = await asyncio.to_thread(session.prepare, text)
        self._prepared[text] = statement
        while len(self._prepared) > 256:
            self._prepared.popitem(last=False)
        return statement

    @asynccontextmanager
    async def own_session(self, keyspace: str | None) -> AsyncIterator[Session]:
        """A session of this cluster for one console run (D343).

        Of its own, so a `USE` in the run changes the keyspace of that run and
        of no page anybody else is reading.
        """
        await self.session()
        cluster = self._cluster
        if cluster is None:
            raise AdapterError("network", say("Could not reach the database server"))
        session = await asyncio.to_thread(cluster.connect, keyspace)
        try:
            yield session
        finally:
            await asyncio.to_thread(session.shutdown)

    async def close(self) -> None:
        cluster, self._cluster, self._session = self._cluster, None, None
        if cluster is not None:
            await asyncio.to_thread(cluster.shutdown)


def key_for(pooling: Pooling, fingerprint_source: str) -> str:
    """Hashed, as MySQL's pool key is: the source carries the password."""
    fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()[:16]
    return f"cassandra:{pooling.connector_id}:{fingerprint}"


class CassandraSession:
    """How to talk to one Cassandra or ScyllaDB cluster."""

    def __init__(
        self,
        options: CassandraOptions,
        pooling: Pooling | None = None,
        tunnels: TunnelAccess | None = None,
    ) -> None:
        self._options = options
        self._pooling = pooling
        self._tunnels = tunnels
        self._profile: ServerProfile | None = None
        self._pages = PageStates()

    @property
    def options(self) -> CassandraOptions:
        return self._options

    def keyspace(self) -> str:
        """The keyspace the connection names, or nothing when it names none."""
        return self._options.keyspace

    def _password(self) -> str:
        if not isinstance(self._options, CassandraUserPassword):
            return ""
        return self._options.password.get_secret_value()

    def connection_string(self) -> str:
        options = self._options
        return compose_url(
            host=options.host,
            port=options.port,
            user=options.user if isinstance(options, CassandraUserPassword) else "",
            keyspace=options.keyspace,
            secure=options.secure,
        )

    async def _address(self) -> tuple[str, int]:
        options = self._options
        return await reach(
            self._tunnels, options.ssh_tunnel, options.host, options.port
        )

    @asynccontextmanager
    async def cluster(self) -> AsyncIterator[KeptCluster]:
        """The connector's kept cluster, or one for this request alone."""
        address = await self._address()
        if self._pooling is not None:
            options = self._options
            user = options.user if isinstance(options, CassandraUserPassword) else ""
            # What makes two clusters different, and nothing about a request;
            # the address dialled too, which a tunnel may change.
            fingerprint = (
                f"{address[0]}:{address[1]}:{options.host}:{options.secure}:"
                f"{options.consistency}:{user}:{self._password()}"
            )
            key = key_for(self._pooling, fingerprint)
            store = self._pooling.store

            async def create() -> KeptCluster:
                return KeptCluster(options, address)

            kept = (
                await store.get_or_create(key, KeptCluster, create)
                if store.keeps
                else await store.existing(key, KeptCluster)
            )
            if kept is not None:
                yield kept
                return
        own = KeptCluster(self._options, address)
        own.pages = self._pages
        try:
            yield own
        finally:
            await own.close()

    async def _run(
        self,
        kept: KeptCluster,
        statement: str,
        params: Sequence[Any] | None,
        *,
        fetch_size: int | None,
        paging_state: bytes | None,
        wait_seconds: float | None,
    ) -> Answer:
        session = await kept.session()
        query: Any
        if params is None:
            query = SimpleStatement(statement, fetch_size=fetch_size)
        else:
            query = await kept.prepared(statement)
            types = [column.type for column in query.column_metadata or []]
            query = query.bind(
                [
                    driver_value(value, cql_type)
                    for value, cql_type in zip(params, types, strict=False)
                ]
            )
            query.fetch_size = fetch_size
        future = session.execute_async(
            query,
            paging_state=paging_state,
            timeout=REQUEST_TIMEOUT_SECONDS if wait_seconds is None else wait_seconds,
        )
        return await waited(future)

    async def page(
        self,
        statement: str,
        params: Sequence[Any] | None = None,
        *,
        fetch_size: int | None = 5000,
        paging_state: bytes | None = None,
        wait_seconds: float | None = None,
        refusals: Mapping[type[BaseException], str] | None = None,
    ) -> Answer:
        """One page of a statement; values bound to a prepared statement.

        `params` None runs the text as it is, with nothing bound; a list
        prepares it, so every value travels typed by its column.
        """
        try:
            async with self.cluster() as kept:
                return await self._run(
                    kept,
                    statement,
                    params,
                    fetch_size=fetch_size,
                    paging_state=paging_state,
                    wait_seconds=wait_seconds,
                )
        except Exception as exc:
            raise self.failure(exc, refusals) from None

    async def rows(
        self,
        statement: str,
        params: Sequence[Any] | None = None,
        *,
        limit: int = 100_000,
        refusals: Mapping[type[BaseException], str] | None = None,
    ) -> Answer:
        """Every row a statement answers, page after page, up to a ceiling."""
        try:
            async with self.cluster() as kept:
                answer = await self._run(
                    kept,
                    statement,
                    params,
                    fetch_size=5000,
                    paging_state=None,
                    wait_seconds=None,
                )
                while answer.paging_state is not None and len(answer.rows) < limit:
                    more = await self._run(
                        kept,
                        statement,
                        params,
                        fetch_size=5000,
                        paging_state=answer.paging_state,
                        wait_seconds=None,
                    )
                    answer.rows.extend(more.rows)
                    answer.paging_state = more.paging_state
                del answer.rows[limit:]
                return answer
        except Exception as exc:
            raise self.failure(exc, refusals) from None

    async def query(
        self, statement: str, params: Sequence[Any] | None = None
    ) -> list[dict[str, Any]]:
        """Every row of a catalog read, as names and values."""
        return (await self.rows(statement, params)).dicts()

    def failure(
        self,
        exc: BaseException,
        refusals: Mapping[type[BaseException], str] | None = None,
    ) -> Exception:
        """A driver's exception as the adapter's, with the caller's words for what it expected.

        A statement the server read and refused is the caller's mistake, and
        comes back as a ValueError with the server's sentence, as ClickHouse's
        does; everything else is the source failing.
        """
        if isinstance(exc, AdapterError | ValueError):
            return exc
        if refusals is not None:
            for kind, words in refusals.items():
                if isinstance(exc, kind):
                    return ValueError(say(words))
        if is_refusal(exc):
            return ValueError(refusal_text(exc))
        error_kind, message = classify(exc, fallback_message=N_("Query failed"))
        return AdapterError(error_kind, message)

    async def page_states(self) -> PageStates:
        """Where the pages of this connector's reads ended (D342)."""
        async with self.cluster() as kept:
            return kept.pages

    async def profile(self) -> ServerProfile:
        if self._profile is not None:
            return self._profile
        try:
            async with self.cluster() as kept:
                if kept.profile is None:
                    kept.profile = await self._read_profile(kept)
                self._profile = kept.profile
                return kept.profile
        except Exception as exc:
            raise self.failure(exc) from None

    async def _read_profile(self, kept: KeptCluster) -> ServerProfile:
        release = await self._run(
            kept, _RELEASE, None, fetch_size=None, paging_state=None, wait_seconds=None
        )
        row = release.dicts()[0] if release.rows else {}
        try:
            versions = await self._run(
                kept,
                _SCYLLA_VERSION,
                None,
                fetch_size=None,
                paging_state=None,
                wait_seconds=None,
            )
            scylla: str | None = str(versions.rows[0][0]) if versions.rows else None
        except InvalidRequest:
            scylla = None
        return read_profile(
            str(row.get("release_version") or ""),
            scylla,
            str(row.get("cluster_name") or ""),
            str(row.get("data_center") or ""),
        )

    async def check(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        try:
            address = await self._address()
            own = KeptCluster(self._options, address)
            try:
                profile = await self._read_profile(own)
                if self._options.keyspace and not await self._keyspace_exists(
                    own, self._options.keyspace
                ):
                    raise AdapterError("config", say("Keyspace does not exist"))
            finally:
                await own.close()
        except Exception as exc:
            error_kind, message = classify(exc)
            return ConnectionCheckResult(
                ok=False, message=message, error_kind=error_kind
            )
        if not profile.supported:
            return ConnectionCheckResult(
                ok=False,
                message=say(
                    "{product} {version} is older than this source supports ({oldest})",
                    product=profile.product,
                    version=profile.text,
                    oldest=".".join(str(part) for part in profile.oldest),
                ),
                error_kind="config",
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=latency_ms
        )

    async def _keyspace_exists(self, kept: KeptCluster, keyspace: str) -> bool:
        answer = await self._run(
            kept,
            "SELECT keyspace_name FROM system_schema.keyspaces WHERE keyspace_name = ?",
            [keyspace],
            fetch_size=None,
            paging_state=None,
            wait_seconds=None,
        )
        return bool(answer.rows)
