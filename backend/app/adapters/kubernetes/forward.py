"""A port of a pod, or of a Service, reached through the cluster (D474).

A Kubernetes connection carries a tunnel the way an SSH connection does
(D282): another connection names it as its `ssh_tunnel`, and its host says
what in the cluster — `<pod>.<namespace>.pod`, or `<service>.<namespace>.svc`
as the cluster's DNS spells a Service. One listener on loopback per cluster
and target; every connection a driver makes to it is one `portforward`
WebSocket (`v4.channel.k8s.io`, *checked* on k3s 1.33). Each of its two
channels, data and error, first carries the port as two bytes, little end
first; then a frame's first byte is its channel. A Service is followed to a
ready pod behind it, and its port to that pod's, at every connection, so a
pod made again is found.

Kept here as the SSH tunnels are (`ssh/tunnel.py`), for the same reason: the
listener outlives the request, and the health monitor, the metrics collector
and the search-keeper build sources with no resource store.
"""

import asyncio
import contextlib
import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

from app.adapters.kubernetes.endpoint import endpoint_of
from app.adapters.kubernetes.options import KubernetesConnection
from app.adapters.kubernetes.session import Forbidden, KubernetesSession, segment
from app.adapters.protocol import AdapterError
from app.adapters.tunnels import TunnelAccess, TunnelTarget
from app.core.translation import say

logger = logging.getLogger(__name__)

LOOPBACK = "127.0.0.1"
IDLE_SECONDS = 600.0
PROTOCOLS = ["v4.channel.k8s.io"]
_CHUNK = 65_536
_DATA, _ERROR = 0, 1
_LABEL = r"[a-z0-9]([-a-z0-9]*[a-z0-9])?"
_ADDRESS = re.compile(
    rf"^(?P<name>{_LABEL}(\.{_LABEL})*)\.(?P<namespace>{_LABEL})\.(?P<kind>pod|svc)(\.cluster\.local)?$"
)


@dataclass(frozen=True)
class Reach:
    """What a tunnelled host names in the cluster."""

    kind: Literal["pod", "svc"]
    namespace: str
    name: str

    @property
    def host(self) -> str:
        return f"{self.name}.{self.namespace}.{self.kind}"


def reach_of(host: str) -> Reach:
    found = _ADDRESS.match(host.lower())
    if found is None:
        raise AdapterError(
            "config",
            say(
                "Through a Kubernetes connection the host is <pod>.<namespace>.pod or <service>.<namespace>.svc, not {host}",
                host=host[:100],
            ),
        )
    kind: Literal["pod", "svc"] = "pod" if found["kind"] == "pod" else "svc"
    return Reach(kind, found["namespace"], found["name"])


def _ready(pod: dict[str, Any]) -> bool:
    status = pod.get("status") or {}
    if status.get("phase") != "Running" or (pod.get("metadata") or {}).get(
        "deletionTimestamp"
    ):
        return False
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in status.get("conditions") or []
        if isinstance(condition, dict)
    )


def pod_port(pod: dict[str, Any], wanted: int | str) -> int | None:
    """A port of the pod: a number as it is, a name by its containers' ports."""
    if isinstance(wanted, int):
        return wanted
    if wanted.isdigit():
        return int(wanted)
    for container in (pod.get("spec") or {}).get("containers") or []:
        for port in (
            (container.get("ports") or []) if isinstance(container, dict) else []
        ):
            if (
                isinstance(port, dict)
                and port.get("name") == wanted
                and isinstance(port.get("containerPort"), int)
            ):
                return int(port["containerPort"])
    return None


def service_target(service: dict[str, Any], port: int) -> int | str:
    """The pod's port behind a Service's `port`; a Service that does not
    serve it is refused."""
    for one in (service.get("spec") or {}).get("ports") or []:
        if (
            isinstance(one, dict)
            and one.get("port") == port
            and (one.get("protocol") or "TCP") == "TCP"
        ):
            target = one.get("targetPort")
            return target if isinstance(target, int | str) and target != "" else port
    raise AdapterError("config", say("The service has no TCP port {port}", port=port))


async def resolved(
    session: KubernetesSession, reach: Reach, port: int
) -> tuple[str, int]:
    """The running pod and its port that `reach:port` leads to now."""
    namespace = segment(reach.namespace)
    if reach.kind == "pod":
        pod = await session.get(
            f"/api/v1/namespaces/{namespace}/pods/{segment(reach.name)}",
            asked=Forbidden("get", "pods"),
        )
        if (
            not isinstance(pod, dict)
            or (pod.get("status") or {}).get("phase") != "Running"
        ):
            raise AdapterError(
                "config", say("The pod {name} is not running", name=reach.name)
            )
        return reach.name, port
    service = await session.get(
        f"/api/v1/namespaces/{namespace}/services/{segment(reach.name)}",
        asked=Forbidden("get", "services"),
    )
    target = service_target(service if isinstance(service, dict) else {}, port)
    selector = ((service or {}).get("spec") or {}).get("selector") or {}
    if not isinstance(selector, dict) or not selector:
        raise AdapterError(
            "config", say("The service {name} selects no pods", name=reach.name)
        )
    pods = await session.get(
        f"/api/v1/namespaces/{namespace}/pods",
        {
            "labelSelector": ",".join(
                f"{key}={value}" for key, value in sorted(selector.items())
            ),
            "limit": 100,
        },
        asked=Forbidden("list", "pods"),
    )
    for pod in (pods.get("items") if isinstance(pods, dict) else None) or []:
        if isinstance(pod, dict) and _ready(pod):
            number = pod_port(pod, target)
            if number is not None:
                return str((pod.get("metadata") or {}).get("name")), number
    raise AdapterError(
        "config", say("No pod behind the service {name} is ready", name=reach.name)
    )


class PortForwarder:
    """A port on loopback that reaches one target in one cluster."""

    def __init__(
        self,
        options: KubernetesConnection,
        tunnels: TunnelAccess | None,
        reach: Reach,
        port: int,
    ) -> None:
        self._session = KubernetesSession(options, tunnels)
        self._reach = reach
        self._port = port
        self.loop = asyncio.get_running_loop()
        self._server: asyncio.Server | None = None
        self._flowing = 0
        self._used_at = time.monotonic()

    def idle(self) -> bool:
        return self._flowing == 0 and time.monotonic() - self._used_at > IDLE_SECONDS

    async def endpoint(self) -> tuple[str, int]:
        """Where to dial, once the target is there: a pod that is gone or a
        Service with nothing ready behind it is the caller's answer."""
        self._used_at = time.monotonic()
        await resolved(self._session, self._reach, self._port)
        if self._server is None:
            self._server = await asyncio.start_server(self._accept, LOOPBACK, 0)
        port: int = self._server.sockets[0].getsockname()[1]
        return LOOPBACK, port

    async def close(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
        await self._session.close()

    async def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._flowing += 1
        try:
            try:
                pod, port = await resolved(self._session, self._reach, self._port)
                socket = await self._session.socket(
                    f"/api/v1/namespaces/{segment(self._reach.namespace)}/pods/{segment(pod)}/portforward",
                    [("ports", str(port))],
                    PROTOCOLS,
                    asked=Forbidden("create", "pods/portforward"),
                )
            except AdapterError as failure:
                # The driver sees its connection closed; the next `endpoint`
                # says what went wrong.
                logger.warning(
                    "A Kubernetes port forward did not open: %s", failure.message
                )
                writer.close()
                return
            await _carry(reader, writer, socket)
        finally:
            self._flowing -= 1
            self._used_at = time.monotonic()


async def _carry(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, socket: ClientConnection
) -> None:
    """Both directions until either ends: the protocol has no half-close."""

    async def outward() -> None:
        while chunk := await reader.read(_CHUNK):
            await socket.send(bytes([_DATA]) + chunk)

    async def inward() -> None:
        # The first frame of each channel is the port it is for.
        prefixed = {_DATA: True, _ERROR: True}
        async for frame in socket:
            data = frame.encode() if isinstance(frame, str) else frame
            if not data:
                continue
            channel, payload = data[0], data[1:]
            if prefixed.get(channel):
                prefixed[channel] = False
                payload = payload[2:]
            if channel == _DATA and payload:
                writer.write(payload)
                await writer.drain()
            elif channel == _ERROR and payload:
                logger.info(
                    "A Kubernetes port forward failed: %s",
                    payload[:300].decode(errors="replace"),
                )
                return

    tasks = [asyncio.create_task(outward()), asyncio.create_task(inward())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except ConnectionClosed, OSError:
        pass
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, ConnectionClosed, OSError):
                await task
        await socket.close()
        writer.close()


def _identity(options: KubernetesConnection) -> str:
    """Which cluster and as whom, without keeping a credential as a key."""
    endpoint = endpoint_of(options)
    parts = (
        endpoint.server,
        endpoint.server_name,
        endpoint.ca,
        endpoint.token,
        endpoint.client_certificate,
        endpoint.client_key,
    )
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


@dataclass
class Forwards:
    """Every port forward of this process, by cluster, identity and target."""

    _forwarders: dict[tuple[str, str, int], PortForwarder] = field(default_factory=dict)

    async def endpoint(
        self,
        options: KubernetesConnection,
        tunnels: TunnelAccess | None,
        host: str,
        port: int,
    ) -> tuple[str, int]:
        reach = reach_of(host)
        await self._sweep()
        key = (_identity(options), reach.host, port)
        found = self._forwarders.get(key)
        # A forwarder belongs to the loop that made it (see `ssh/tunnel.py`).
        if found is None or found.loop is not asyncio.get_running_loop():
            found = PortForwarder(options, tunnels, reach, port)
            self._forwarders[key] = found
        return await found.endpoint()

    async def _sweep(self) -> None:
        loop = asyncio.get_running_loop()
        for key in [
            key
            for key, one in self._forwarders.items()
            if one.loop is loop and one.idle()
        ]:
            await self._forwarders.pop(key).close()


FORWARDS = Forwards()


# How many places a form is offered; a cluster with more is typed into.
MAX_TARGETS = 500


def _selects(selector: dict[str, Any], pod: dict[str, Any]) -> bool:
    labels = (pod.get("metadata") or {}).get("labels") or {}
    return bool(selector) and all(
        labels.get(key) == value for key, value in selector.items()
    )


def _pod_ports(pod: dict[str, Any]) -> list[int]:
    found: list[int] = []
    for container in (pod.get("spec") or {}).get("containers") or []:
        for port in (
            (container.get("ports") or []) if isinstance(container, dict) else []
        ):
            number = port.get("containerPort") if isinstance(port, dict) else None
            if (
                isinstance(number, int)
                and (port.get("protocol") or "TCP") == "TCP"
                and number not in found
            ):
                found.append(number)
    return found


def _first(ports: list[int], wanted: int | None) -> list[int]:
    if wanted is None:
        return ports
    return [wanted, *(port for port in ports if port != wanted)]


def targets_of(
    services: list[dict[str, Any]],
    pods: list[dict[str, Any]],
    declared: Callable[[dict[str, Any]], tuple[str, int] | None],
) -> list[TunnelTarget]:
    """Services, then running pods, as places a form offers (D479).

    `declared` names the database a pod's image is and the port it serves
    (D417); a target leading to one says so and offers that port first.
    """
    found: list[TunnelTarget] = []
    running = [
        pod for pod in pods if (pod.get("status") or {}).get("phase") == "Running"
    ]
    for service in services:
        metadata = service.get("metadata") or {}
        spec = service.get("spec") or {}
        name, namespace = (
            str(metadata.get("name") or ""),
            str(metadata.get("namespace") or ""),
        )
        ports = [
            one["port"]
            for one in spec.get("ports") or []
            if isinstance(one, dict)
            and isinstance(one.get("port"), int)
            and (one.get("protocol") or "TCP") == "TCP"
        ]
        if not name or not namespace or not ports:
            continue
        label = say("Service {name} in {namespace}", name=name, namespace=namespace)
        selector = spec.get("selector") or {}
        behind = [
            pod
            for pod in running
            if (pod.get("metadata") or {}).get("namespace") == namespace
            and _selects(selector, pod)
        ]
        wanted = None
        for pod in behind:
            known = declared(pod)
            if known is not None:
                label = f"{label} · {known[0]}"
                wanted = service_port_to(service, pod, known[1])
                break
        found.append(
            TunnelTarget(
                host=f"{name}.{namespace}.svc",
                label=label[:300],
                ports=_first(ports, wanted)[:50],
            )
        )
    for pod in running:
        metadata = pod.get("metadata") or {}
        name, namespace = (
            str(metadata.get("name") or ""),
            str(metadata.get("namespace") or ""),
        )
        if not name or not namespace:
            continue
        ports = _pod_ports(pod)
        label = say("Pod {name} in {namespace}", name=name, namespace=namespace)
        known = declared(pod)
        if known is not None:
            label = f"{label} · {known[0]}"
            ports = _first(ports, known[1])
        if not ports:
            continue
        found.append(
            TunnelTarget(
                host=f"{name}.{namespace}.pod", label=label[:300], ports=ports[:50]
            )
        )
    return found[:MAX_TARGETS]


def service_port_to(
    service: dict[str, Any], pod: dict[str, Any], port: int
) -> int | None:
    """The Service's TCP port that leads to the pod's `port`."""
    for one in (service.get("spec") or {}).get("ports") or []:
        if not isinstance(one, dict) or (one.get("protocol") or "TCP") != "TCP":
            continue
        target = one.get("targetPort", one.get("port"))
        if (
            isinstance(target, int | str)
            and pod_port(pod, target) == port
            and isinstance(one.get("port"), int)
        ):
            return int(one["port"])
    return None


async def listed_targets(
    session: KubernetesSession,
    namespace: str | None,
    declared: Callable[[dict[str, Any]], tuple[str, int] | None],
) -> list[TunnelTarget]:
    """What the connection reaches, as far as it may list (D479): a kind the
    cluster will not list to it is left out rather than failing the form."""
    base = (
        "/api/v1" if namespace is None else f"/api/v1/namespaces/{segment(namespace)}"
    )
    lists: list[list[dict[str, Any]]] = []
    refusals = 0
    for resource in ("services", "pods"):
        params: dict[str, str | int] = {"limit": MAX_TARGETS}
        if resource == "pods":
            params["fieldSelector"] = "status.phase=Running"
        try:
            body = await session.get(
                f"{base}/{resource}", params, asked=Forbidden("list", resource)
            )
        except AdapterError as failure:
            if failure.error_kind != "auth":
                raise
            refusals += 1
            body = {}
        items = body.get("items") if isinstance(body, dict) else None
        lists.append([one for one in items or [] if isinstance(one, dict)])
    if refusals == 2:
        raise AdapterError(
            "auth",
            say("The cluster does not let this connection list services or pods"),
        )
    services, pods = lists
    return targets_of(services, pods, declared)
