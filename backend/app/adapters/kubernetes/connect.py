"""A database in the cluster as a connection of its own type (D474, on D417).

A pod whose container's image a type declares, or a Service in front of such
pods, drafts a connection of that type going through this Kubernetes
connection as its tunnel (`forward.py`): host `<pod>.<namespace>.pod` or
`<service>.<namespace>.svc`, the port the image's server listens on (a
Service's own port that leads to it). The options other than host and port
come from the container's environment by the image's conventions, literal
values only: one read from a Secret or a ConfigMap is left to the form, as
the cluster would have to be asked for what this connection may not read.
"""

from collections.abc import Mapping
from typing import Any, ClassVar

from app.adapters.actions import Action, ActionRefused, ActsOn, ConnectorDraft
from app.adapters.catalog import NodeKind
from app.adapters.kubernetes.actions import Kube, NoParams, Target, read, target_of
from app.adapters.kubernetes.discovery import Resource
from app.adapters.kubernetes.forward import Reach, resolved, service_port_to
from app.adapters.kubernetes.reviews import Asked
from app.adapters.kubernetes.session import Forbidden, segment
from app.adapters.protocol import AdapterError
from app.adapters.registry import AdapterType, ContainerImage, type_for_image
from app.core.access import Access
from app.core.translation import N_, say

PODS = "/pods"
SERVICES = "/services"


def environment(container: dict[str, Any]) -> dict[str, str]:
    """A container's literal `env`; the first of a repeated name wins."""
    found: dict[str, str] = {}
    for item in container.get("env") or []:
        if (
            isinstance(item, dict)
            and "value" in item
            and item.get("name")
            and item["name"] not in found
        ):
            found[str(item["name"])] = str(item.get("value") or "")
    return found


def declared_in(
    pod: dict[str, Any],
) -> tuple[AdapterType, ContainerImage, dict[str, Any]] | None:
    """The first container whose image a type declares, with that type."""
    for container in (pod.get("spec") or {}).get("containers") or []:
        if not isinstance(container, dict):
            continue
        declared = type_for_image(str(container.get("image") or ""))
        if declared is not None:
            return declared[0], declared[1], container
    return None


class OpenAsConnection(Action[NoParams]):
    name: ClassVar[str] = "kubernetes_open_as_connection"
    title: ClassVar[str] = N_("Open as connection")
    icon: ClassVar[str | None] = "cable"
    in_view: ClassVar[bool] = True
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"k8s_object"})
    acts_on: ClassVar[ActsOn] = "node"
    # The draft carries passwords from the pod's spec and goes through this
    # connection, so it is its owner's alone (D417).
    requires: ClassVar[Access] = "own"
    params_model = NoParams
    keys: ClassVar[frozenset[str]] = frozenset({PODS, SERVICES})

    def __init__(self, kube: Kube, connector_id: str | None) -> None:
        self._kube = kube
        self._connector_id = connector_id

    def fits(self, resource: Resource) -> bool:
        return resource.key in self.keys

    def asked(self, target: Target) -> Asked:
        return self.asked_at(target.resource, target.namespace)

    def asked_at(self, resource: Resource, namespace: str | None) -> Asked:
        return Asked(
            verb="create",
            group="",
            resource="pods",
            namespace=namespace,
            subresource="portforward",
        )

    async def _pod_of(
        self, target: Target
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """The pod, and the Service when the node is one."""
        body = await read(self._kube, target)
        if target.resource.key == PODS:
            return body, None
        reach = Reach("svc", target.namespace or "", target.name)
        ports = [
            one.get("port")
            for one in (body.get("spec") or {}).get("ports") or []
            if isinstance(one, dict)
        ]
        for port in ports:
            if not isinstance(port, int):
                continue
            try:
                pod_name, _ = await resolved(self._kube.session, reach, port)
            except AdapterError:
                continue
            pod = await self._kube.session.get(
                f"/api/v1/namespaces/{segment(target.namespace or '')}/pods/{segment(pod_name)}",
                asked=Forbidden("get", "pods"),
            )
            return (pod if isinstance(pod, dict) else {}), body
        raise ActionRefused(
            "not_applicable",
            say("No pod behind the service {name} is ready", name=target.name),
        )

    async def offered(self, node_id: str) -> bool:
        """Whether a type declares an image of the pod, or of a pod behind the Service."""
        try:
            target = await target_of(self._kube, node_id, set(self.keys))
            pod, _ = await self._pod_of(target)
        except ActionRefused, AdapterError:
            return False
        return declared_in(pod) is not None

    async def prepare_connector(
        self, node_id: str | None, raw: Mapping[str, Any]
    ) -> ConnectorDraft:
        self._validated(raw)
        if self._connector_id is None:
            raise ActionRefused(
                "not_applicable",
                say("Save this connection first; the new one goes through it"),
            )
        target = await target_of(self._kube, node_id, set(self.keys))
        pod, service = await self._pod_of(target)
        declared = declared_in(pod)
        if declared is None:
            images = ", ".join(
                str(one.get("image") or "")
                for one in (pod.get("spec") or {}).get("containers") or []
                if isinstance(one, dict)
            )
            raise ActionRefused(
                "not_applicable",
                say("No connection type here runs as {image}", image=images[:200]),
            )
        adapter_type, image, container = declared
        port = image.port
        kind = "pod"
        if service is not None:
            found = service_port_to(service, pod, image.port)
            if found is None:
                raise ActionRefused(
                    "not_applicable",
                    say(
                        "The service has no port that leads to {port}", port=image.port
                    ),
                )
            port, kind = found, "svc"
        return ConnectorDraft(
            name=target.name[:255],
            adapter_type=adapter_type.name,
            options={
                **image.options(environment(container)),
                "host": f"{target.name}.{target.namespace}.{kind}",
                "port": port,
                "ssh_tunnel": self._connector_id,
            },
        )


def declared_server(pod: dict[str, Any]) -> tuple[str, int] | None:
    """The database a pod's image is, by its type's title, and its port (D417)."""
    found = declared_in(pod)
    return None if found is None else (say(found[0].title), found[1].port)
