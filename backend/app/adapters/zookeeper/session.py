"""How this application talks to a ZooKeeper server, and nothing about what for.

kazoo is synchronous and runs threads of its own, so a whole operation — open
a session, do the work, close it — is one call into the thread pool rather than
one per request (D297). A session per operation, as Redis has one: a znode is
a handful of round trips, and a session kept open would be an ephemeral
lifetime on the server for nobody.

kazoo's own message names the address it failed on, so none of it crosses
this boundary.
"""

import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote

from kazoo.client import KazooClient
from kazoo.exceptions import (
    AuthFailedError,
    BadVersionError,
    InvalidACLError,
    KazooException,
    NoAuthError,
    NodeExistsError,
    NoNodeError,
    NotEmptyError,
    ZookeeperError,
)
from kazoo.handlers.threading import KazooTimeoutError
from starlette.concurrency import run_in_threadpool

from app.adapters.actions import ActionRefused
from app.adapters.content import ContentConflict
from app.adapters.protocol import (
    AdapterError,
    ConnectionCheckResult,
    ErrorKind,
    NodeNotFound,
)
from app.adapters.tunnels import TunnelAccess, reach
from app.adapters.zookeeper.options import (
    ZookeeperDigest,
    ZookeeperOptions,
    chroot_problem,
)
from app.core.logs import record_failure, with_ref
from app.core.translation import say

logger = logging.getLogger(__name__)

# What opening a session and one call may cost.
TIMEOUT_SECONDS = 5.0


class ZookeeperSession:
    """A way to reach one ZooKeeper server, opened per operation."""

    def __init__(
        self, options: ZookeeperOptions, tunnels: TunnelAccess | None = None
    ) -> None:
        self._options = options
        self._tunnels = tunnels

    @property
    def options(self) -> ZookeeperOptions:
        return self._options

    async def run[T](self, work: Callable[[KazooClient], T], node_id: str = "") -> T:
        """`work` on a session of its own, in the thread pool, failures reduced.

        A missing znode is an answer (404) and a changed version a conflict,
        so both pass through as this repository's own exceptions; anything
        else the driver raises is reduced to a kind and a sentence.
        """
        host, port = await reach(
            self._tunnels,
            self._options.ssh_tunnel,
            self._options.host,
            self._options.port,
        )
        return await run_in_threadpool(self._run, f"{host}:{port}", work, node_id)

    def _run[T](
        self, address: str, work: Callable[[KazooClient], T], node_id: str
    ) -> T:
        client = self._client(address)
        try:
            client.start(timeout=TIMEOUT_SECONDS)
            return work(client)
        except NodeNotFound, ContentConflict, AdapterError, ActionRefused, ValueError:
            raise
        except NoNodeError:
            raise NodeNotFound(node_id) from None
        except BadVersionError:
            raise ContentConflict() from None
        except (KazooException, KazooTimeoutError, OSError) as failure:
            raise reduced(failure) from None
        finally:
            _close(client)

    async def held(self) -> KazooClient:
        """A session kept open for watches (D303), which reconnects by itself.

        The only one this source keeps: the first connection fails fast, as a
        request's would, and a dropped one is tried again for as long as the
        watch is wanted.
        """
        host, port = await reach(
            self._tunnels,
            self._options.ssh_tunnel,
            self._options.host,
            self._options.port,
        )
        return await run_in_threadpool(self._held, f"{host}:{port}")

    def _held(self, address: str) -> KazooClient:
        client = self._client(address, held=True)
        try:
            client.start(timeout=TIMEOUT_SECONDS)
        except (KazooException, KazooTimeoutError, OSError) as failure:
            _close(client)
            raise reduced(failure) from None
        return client

    def _client(self, address: str, *, held: bool = False) -> KazooClient:
        options = self._options
        auth: list[tuple[str, str]] = []
        if isinstance(options, ZookeeperDigest):
            auth.append(
                ("digest", f"{options.user}:{options.password.get_secret_value()}")
            )
        return KazooClient(
            hosts=address + options.chroot,
            timeout=TIMEOUT_SECONDS,
            # One attempt: a person is waiting on the answer, and the retries
            # kazoo would make are a minute of silence about a wrong address.
            connection_retry=(
                {"max_tries": -1, "max_delay": 30} if held else {"max_tries": 0, "max_delay": 1}
            ),
            command_retry={"max_tries": 0},
            auth_data=auth or None,
            use_ssl=options.tls,
            verify_certs=True,
            read_only=False,
        )

    async def check(self) -> ConnectionCheckResult:
        """Open a session and read the root, in words that name no address."""
        started = time.perf_counter()
        try:
            # Below a root path that is not there, the root reads as absent
            # rather than failing; kazoo only warns.
            found = await self.run(lambda client: client.exists("/"))
        except AdapterError as failure:
            return _refused(failure.error_kind, failure.message)
        except NodeNotFound:
            found = None
        if found is None:
            return _refused(
                "config", say("The root path does not exist on this server")
            )
        elapsed = int((time.perf_counter() - started) * 1000)
        return ConnectionCheckResult(
            ok=True, message=say("Connection successful"), latency_ms=elapsed
        )

    async def server_version(self) -> str | None:
        """What the server says it is running, or nothing when it will not say."""
        try:
            version = await self.run(lambda client: client.server_version())
        except AdapterError, NodeNotFound:
            return None
        if not isinstance(version, tuple) or not version:
            return None
        return ".".join(str(part) for part in version)


def _close(client: KazooClient) -> None:
    try:
        client.stop()
        client.close()
    except Exception:  # noqa: BLE001 - closing a session that failed to open
        logger.debug("ZooKeeper session did not close cleanly", exc_info=True)


def _refused(kind: ErrorKind, message: str) -> ConnectionCheckResult:
    return ConnectionCheckResult(ok=False, message=message, error_kind=kind)


def reduced(failure: BaseException) -> AdapterError:
    """The driver's failure as a kind and a sentence of this repository's.

    Logged on the server, where the address it names is already known, and
    never passed on: an expected one as a line, anything else whole, with the
    ref the sentence carries (D184).
    """
    known = _known(failure)
    if known is not None:
        logger.warning("ZooKeeper failed: %r", failure)
        return known
    ref = record_failure(logger, "ZooKeeper: an unexpected failure", failure)
    return AdapterError(
        "unknown", with_ref(say("The ZooKeeper server could not do that"), ref)
    )


def _known(failure: BaseException) -> AdapterError | None:
    if isinstance(failure, AuthFailedError):
        return AdapterError("auth", say("This connection was refused by the server"))
    if isinstance(failure, NoAuthError):
        return AdapterError(
            "auth", say("This connection may not do that to this znode")
        )
    if isinstance(failure, KazooTimeoutError):
        return AdapterError("timeout", say("Could not reach the ZooKeeper server"))
    if isinstance(failure, OSError):
        return AdapterError("network", say("Could not reach the ZooKeeper server"))
    if isinstance(failure, NodeExistsError):
        return AdapterError("config", say("A znode with that name already exists"))
    if isinstance(failure, NotEmptyError):
        return AdapterError("config", say("The znode has children"))
    if isinstance(failure, InvalidACLError):
        return AdapterError("config", say("The server refused that ACL"))
    if isinstance(failure, ZookeeperError):
        return AdapterError("unknown", say("The ZooKeeper server refused that"))
    return None


# --- the address, as `zkCli.sh -server` takes it -----------------------------


def compose_url(*, host: str, port: int | None = None, chroot: str = "") -> str:
    """`host:port/chroot`, ZooKeeper's own connect string; never a password."""
    authority = f"[{host}]" if ":" in host else host
    if port is not None:
        authority += f":{port}"
    return authority + chroot


def options_from_url(url: str) -> dict[str, Any]:
    """A connect string taken apart into the fields of the form.

    `host:port/chroot`, with `zookeeper://` before it allowed. A list of
    servers names an ensemble to choose from, and this source is pointed at one
    (D297).
    """
    text = url.strip()
    if text.lower().startswith("zookeeper://"):
        text = text[len("zookeeper://") :]
    authority, slash, path = text.partition("/")
    if authority == "":
        raise ValueError(say("The connection string names no host"))
    if "," in authority:
        raise ValueError(say("Name one server; a list of servers is not supported"))
    if "@" in authority:
        raise ValueError(
            say("A ZooKeeper connect string carries no user; choose Digest instead")
        )
    host, port = _host_and_port(authority)
    options: dict[str, Any] = {"host": host, "auth_method": "anonymous"}
    if port is not None:
        options["port"] = port
    chroot = unquote(slash + path).rstrip("/") if path else ""
    problem = chroot_problem(chroot)
    if problem is not None:
        raise ValueError(problem)
    if chroot:
        options["chroot"] = chroot
    return options


def _host_and_port(authority: str) -> tuple[str, int | None]:
    if authority.startswith("["):
        host, _, rest = authority[1:].partition("]")
        port_text = rest.removeprefix(":")
    else:
        host, _, port_text = authority.partition(":")
    if host == "":
        raise ValueError(say("The connection string names no host"))
    if port_text == "":
        return host, None
    if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
        raise ValueError(say("The connection string names no usable port"))
    return host, int(port_text)
