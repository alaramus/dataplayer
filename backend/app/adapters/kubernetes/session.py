"""How this application reaches a cluster's API server, and nothing about what for.

HTTPS with httpx, no client library (D464). The endpoint a way in resolves to
is dialled directly or through the owner's SSH tunnel (D282), the certificate
checked against the server's own name either way (D448). The server's version
is asked once per session and held to a floor.

Neither the cluster's words nor httpx's cross this boundary: a `Status`
message names the identity and its groups, and httpx's the address (D467).
"""

import asyncio
import json
import logging
import ssl
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from anyio import to_thread

from app.adapters.kubernetes.endpoint import Endpoint, endpoint_of
from app.adapters.kubernetes.options import KubernetesConnection
from app.adapters.protocol import AdapterError, ConnectionCheckResult, NodeNotFound
from app.adapters.tls import TlsSettings, ssl_context
from app.adapters.tunnels import TunnelAccess, tunnel_of
from app.core.translation import say

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20.0
# The oldest minor still in a cloud's extended support when this was written.
FLOOR = (1, 27)
TABLE = "application/json;as=Table;v=v1;g=meta.k8s.io,application/json"
# A list whose items carry their metadata alone: a count costs no specs.
METADATA = "application/json;as=PartialObjectMetadataList;v=v1;g=meta.k8s.io,application/json"


def segment(name: str) -> str:
    """A name as one segment of the API's path, never concatenated raw."""
    return quote(name, safe="")


def version_of(body: Any) -> tuple[int, int] | None:
    """`major` and `minor` of `/version`; a minor may read "27+" (GKE, EKS)."""
    if not isinstance(body, dict):
        return None
    major = str(body.get("major") or "").rstrip("+")
    minor = str(body.get("minor") or "").rstrip("+")
    if not major.isdigit() or not minor.isdigit():
        return None
    return int(major), int(minor)


@dataclass(frozen=True)
class Forbidden:
    """What was asked, so a 403 can be said by the verb and the resource (D467)."""

    verb: str
    resource: str


def refused(status: int, asked: Forbidden | None, body: Any) -> AdapterError:
    """The cluster's status in this repository's words (D467)."""
    if status == 401:
        return AdapterError("auth", say("The cluster did not accept these credentials"))
    if status == 403:
        if asked is None:
            return AdapterError("auth", say("The cluster does not let this connection do that"))
        return AdapterError(
            "auth",
            say(
                "The cluster does not let this connection {verb} {resource}",
                verb=asked.verb,
                resource=asked.resource,
            ),
        )
    if status == 404:
        return AdapterError("config", say("The cluster has no such thing"))
    if status == 409:
        return AdapterError("config", say("It changed since it was read; read it again"))
    if status == 422:
        fields = _invalid_fields(body)
        if fields:
            return AdapterError(
                "config", say("The cluster refused these fields: {fields}", fields=", ".join(fields))
            )
        return AdapterError("config", say("The cluster refused it as invalid"))
    if status == 429:
        return AdapterError("unknown", say("The cluster asked to wait; try again in a moment"))
    logger.warning("The Kubernetes API answered %s", status)
    return AdapterError("unknown", say("The cluster could not do that"))


def _invalid_fields(body: Any) -> list[str]:
    """The field paths of a 422's causes: the request's own, safe to say."""
    details = body.get("details") if isinstance(body, dict) else None
    causes = details.get("causes") if isinstance(details, dict) else None
    found: list[str] = []
    for cause in causes or []:
        field = cause.get("field") if isinstance(cause, dict) else None
        if isinstance(field, str) and field and len(field) <= 200 and field not in found:
            found.append(field)
    return found[:10]


def _tls_failure(cause: BaseException | None) -> ssl.SSLError | None:
    seen: set[int] = set()
    while cause is not None and id(cause) not in seen:
        if isinstance(cause, ssl.SSLError):
            return cause
        seen.add(id(cause))
        cause = cause.__cause__ or cause.__context__
    return None


class KubernetesSession:
    """One cluster's API server, through one client kept for the session."""

    def __init__(
        self,
        options: KubernetesConnection,
        tunnels: TunnelAccess | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._options = options
        self._tunnels = tunnels
        # A test answers with what the stand recorded.
        self._transport = transport
        self._endpoint: Endpoint | None = None
        self._client: httpx.AsyncClient | None = None
        self._client_port = 0
        self._version: tuple[int, int] | None = None
        self._git_version = ""
        self._lock = asyncio.Lock()

    @property
    def options(self) -> KubernetesConnection:
        return self._options

    @property
    def version(self) -> tuple[int, int] | None:
        return self._version

    @property
    def git_version(self) -> str:
        """The server's own version string, `v1.33.6+k3s1`, once asked."""
        return self._git_version

    def endpoint(self) -> Endpoint:
        if self._endpoint is None:
            self._endpoint = endpoint_of(self._options)
        return self._endpoint

    def _server_parts(self) -> tuple[str, int, str]:
        parts = urlsplit(self.endpoint().server)
        host = parts.hostname or ""
        return host, parts.port or 443, parts.path.rstrip("/")

    async def _address(self) -> tuple[str, int]:
        host, port, _ = self._server_parts()
        through = tunnel_of(self._options.ssh_tunnel)
        if through is None:
            return host, port
        if self._tunnels is None:
            raise AdapterError(
                "config", say("This connection goes through an SSH tunnel, and none is at hand")
            )
        return await self._tunnels.endpoint(through, host, port)

    def _context(self) -> ssl.SSLContext:
        """Blocking: a client key is loaded through a file. Called in a thread."""
        endpoint = self.endpoint()
        host, _, _ = self._server_parts()
        made = ssl_context(
            TlsSettings(
                mode="verify_full",
                ca=endpoint.ca,
                client_certificate=endpoint.client_certificate,
                client_key=endpoint.client_key,
            ),
            # The certificate names the server, not a forwarded port (D448).
            server_name=endpoint.server_name or host,
        )
        assert made is not None  # noqa: S101 - TLS is always on
        return made

    async def client(self) -> httpx.AsyncClient:
        """The client at a checked version; asked before every request, so a
        closed tunnel or a refused certificate is said there."""
        host, port = await self._address()
        async with self._lock:
            if self._client is None or self._client_port != port:
                if self._client is not None:
                    await self._client.aclose()
                context = await to_thread.run_sync(self._context)
                endpoint = self.endpoint()
                _, _, prefix = self._server_parts()
                headers = {"User-Agent": "DataPlayer"}
                if endpoint.token:
                    headers["Authorization"] = f"Bearer {endpoint.token}"
                shown = f"[{host}]" if ":" in host else host
                self._client = httpx.AsyncClient(
                    base_url=f"https://{shown}:{port}{prefix}",
                    headers=headers,
                    verify=context,
                    transport=self._transport,
                    timeout=TIMEOUT_SECONDS,
                    follow_redirects=False,
                )
                self._client_port = port
                self._version = None
            if self._version is None:
                await self._ask_version(self._client)
            return self._client

    async def _ask_version(self, client: httpx.AsyncClient) -> None:
        try:
            answer = await client.get("/version")
        except httpx.HTTPError as failure:
            raise self._not_reached(failure) from None
        if answer.status_code != 200:
            raise refused(answer.status_code, None, _body(answer))
        body = _body(answer)
        version = version_of(body)
        if version is None:
            raise AdapterError("config", say("Something answers there, but not as a Kubernetes API server"))
        if version < FLOOR:
            raise AdapterError(
                "config",
                say(
                    "The cluster runs Kubernetes {version}; 1.27 or newer is needed",
                    version=f"{version[0]}.{version[1]}",
                ),
            )
        self._version = version
        git = body.get("gitVersion") if isinstance(body, dict) else None
        self._git_version = str(git)[:100] if git else f"v{version[0]}.{version[1]}"

    def _not_reached(self, failure: BaseException) -> AdapterError:
        problem = _tls_failure(failure)
        host, port, _ = self._server_parts()
        address = f"{host}:{port}"
        if isinstance(problem, ssl.SSLCertVerificationError):
            if "Hostname mismatch" in str(problem.verify_message):
                return AdapterError(
                    "config",
                    say("The API server's certificate is not for {host}", host=host),
                )
            return AdapterError(
                "config", say("The API server's certificate is not signed by the CA certificate")
            )
        if problem is not None:
            return AdapterError(
                "auth", say("The API server at {address} refused the TLS handshake", address=address)
            )
        if isinstance(failure, httpx.TimeoutException):
            return AdapterError(
                "timeout", say("The API server at {address} did not answer in time", address=address)
            )
        return AdapterError(
            "network", say("The API server does not answer at {address}", address=address)
        )

    async def request(
        self,
        method: str,
        path: str,
        params: Mapping[str, str | int] | None = None,
        *,
        asked: Forbidden | None = None,
        node_id: str = "",
        accept: str = "application/json",
        body: Any | None = None,
        content_type: str = "application/json",
        expected: tuple[int, ...] = (200,),
        seconds: float = TIMEOUT_SECONDS,
    ) -> httpx.Response:
        """An answer whose status is among `expected`, or a reduced failure.

        `content_type` names a patch's kind (merge, strategic, apply); the
        body is JSON whichever it is, which an apply takes as YAML.
        """
        client = await self.client()
        headers = {"Accept": accept}
        if body is not None:
            headers["Content-Type"] = content_type
        try:
            answer = await client.request(
                method,
                path,
                params=params,
                content=None if body is None else json.dumps(body).encode(),
                headers=headers,
                timeout=seconds,
            )
        except httpx.HTTPError as failure:
            raise self._not_reached(failure) from None
        if answer.status_code in expected:
            return answer
        if answer.status_code == 404 and node_id:
            raise NodeNotFound(node_id)
        raise refused(answer.status_code, asked, _body(answer))

    async def get(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
        *,
        asked: Forbidden | None = None,
        node_id: str = "",
        accept: str = "application/json",
    ) -> Any:
        answer = await self.request(
            "GET", path, params, asked=asked, node_id=node_id, accept=accept
        )
        return _json(answer)

    async def check(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        try:
            await self.client()
        except AdapterError as failure:
            return ConnectionCheckResult(ok=False, message=failure.message, error_kind=failure.error_kind)
        return ConnectionCheckResult(
            ok=True,
            message=say("Connection successful; Kubernetes {version}", version=self._git_version),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _body(answer: httpx.Response) -> Any:
    try:
        return answer.json()
    except ValueError:
        return None


def _json(answer: httpx.Response) -> Any:
    try:
        return json.loads(answer.content)
    except ValueError:
        raise AdapterError(
            "network", say("Something answers there, but not as a Kubernetes API server")
        ) from None
