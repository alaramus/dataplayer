"""Node ids of a Kubernetes source, and the nodes the catalog shows (D465).

- `cluster` and `cluster/<report>` — the Cluster section and its reports;
- `namespaces`, `ns/<namespace>`, `ns/<namespace>/s/<section>` — the
  namespaces and the groups of kinds inside one; `*` is every namespace;
- `ns/<namespace>/k/<group>/<resource>` — a kind's objects in a namespace;
- `ns/<namespace>/o/<group>/<resource>/<name>` — one object, and with
  `/events`, `/pods` or `/logs/<container>` after it, one of its pages;
- `scoped`, `scoped/s/<section>`, `scoped/k/…`, `scoped/o/…` — the same for
  the cluster-scoped kinds.

The core group is written `core`. Every part is matched against the API's
own name rules here, and against discovery before a request is built.
"""

import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from app.adapters.catalog import DirectoryNode, KubeObjectNode, ReportNode
from app.adapters.content import NodeRepresentation
from app.adapters.kubernetes.discovery import (
    SECTION_TITLES,
    SECTIONS,
    Resource,
    Section,
)
from app.adapters.views import ViewPage
from app.adapters.words import worded_titles
from app.core.translation import N_, say

CLUSTER = "cluster"
NAMESPACES = "namespaces"
SCOPED = "scoped"
EVERY = "*"
CORE = "core"

View = Literal["events", "pods", "logs"]
_VIEWS: tuple[View, ...] = ("events", "pods", "logs")
_VIEW_TITLES: dict[View, tuple[str, str]] = {
    "events": (N_("Events"), N_("What the cluster recorded about it, newest first")),
    "pods": (N_("Pods"), N_("The pods its selector picks")),
    "logs": (N_("Logs"), N_("What the container printed, newest first")),
}
_VIEW_ICONS: dict[View, str] = {"events": "event_note", "pods": "deployed_code", "logs": "receipt_long"}
# The kinds whose selector picks pods, by `group/resource`.
SELECTS_PODS = {
    "apps/deployments",
    "apps/statefulsets",
    "apps/daemonsets",
    "apps/replicasets",
    "batch/jobs",
    "/services",
}

# A namespace and a container are DNS labels; an object's name a DNS
# subdomain, though some kinds take more (a ConfigMap's key is not a name).
_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
_NAME = re.compile(r"^[A-Za-z0-9]([-A-Za-z0-9_.:@]{0,251}[A-Za-z0-9])?$")
_GROUP = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")
_RESOURCE = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,61}[a-z0-9])?$")

TABLE = NodeRepresentation(kind="table", title=N_("View as table"))
OVERVIEW = NodeRepresentation(kind="view", title=N_("Overview"))
AS_YAML = NodeRepresentation(kind="text", title=N_("As YAML"), icon="description")
AS_JSON = NodeRepresentation(kind="tree", title=N_("As JSON"))
OBJECT_OPENS = [OVERVIEW, AS_YAML, AS_JSON]


@dataclass(frozen=True)
class Named:
    """What a node id names. `namespace` is None for the cluster-scoped side."""

    top: Literal["cluster", "namespaces", "namespace", "scoped"]
    namespace: str | None = None
    section: Section | None = None
    group: str | None = None
    resource: str | None = None
    name: str | None = None
    view: View | None = None
    container: str | None = None
    report: str | None = None


def _refuse() -> ValueError:
    return ValueError(say("Not a node of this connection"))


def _group_of(part: str) -> str:
    if part == CORE:
        return ""
    if not _GROUP.match(part):
        raise _refuse()
    return part


def _group_part(group: str) -> str:
    return group or CORE


def parse(node_id: str) -> Named:
    """The parts of a node id of this source, or a refusal."""
    if node_id == CLUSTER:
        return Named(top="cluster")
    if node_id.startswith(CLUSTER + "/"):
        report = node_id[len(CLUSTER) + 1 :]
        if not _RESOURCE.match(report):
            raise _refuse()
        return Named(top="cluster", report=report)
    if node_id == NAMESPACES:
        return Named(top="namespaces")
    parts = node_id.split("/")
    if parts[0] == "ns" and len(parts) >= 2:
        namespace = parts[1]
        if namespace != EVERY and not _LABEL.match(namespace):
            raise _refuse()
        rest = parts[2:]
        top: Literal["namespace", "scoped"] = "namespace"
    elif parts[0] == SCOPED:
        namespace = None
        rest = parts[1:]
        top = "scoped"
    else:
        raise _refuse()
    if not rest:
        return Named(top=top, namespace=namespace)
    marker = rest[0]
    if marker == "s" and len(rest) == 2 and rest[1] in SECTIONS:
        section = next(one for one in SECTIONS if one == rest[1])
        return Named(top=top, namespace=namespace, section=section)
    if marker == "k" and len(rest) == 3 and _RESOURCE.match(rest[2]):
        return Named(top=top, namespace=namespace, group=_group_of(rest[1]), resource=rest[2])
    if marker == "o" and len(rest) >= 4 and _RESOURCE.match(rest[2]) and _NAME.match(rest[3]):
        if namespace == EVERY:
            raise _refuse()
        named = Named(
            top=top, namespace=namespace, group=_group_of(rest[1]), resource=rest[2], name=rest[3]
        )
        tail = rest[4:]
        if not tail:
            return named
        if tail[0] in ("events", "pods") and len(tail) == 1:
            view: View = tail[0]  # type: ignore[assignment] # one of the two just named
            return replace(named, view=view)
        if tail[0] == "logs" and len(tail) == 2 and _LABEL.match(tail[1]):
            return replace(named, view="logs", container=tail[1])
    raise _refuse()


def _prefix(namespace: str | None) -> str:
    return SCOPED if namespace is None else f"ns/{namespace}"


def namespace_id(namespace: str) -> str:
    return f"ns/{namespace}"


def section_id(namespace: str | None, section: Section) -> str:
    return f"{_prefix(namespace)}/s/{section}"


def kind_id(namespace: str | None, resource: Resource) -> str:
    return f"{_prefix(namespace)}/k/{_group_part(resource.group)}/{resource.resource}"


def object_id(namespace: str | None, group: str, resource: str, name: str) -> str:
    return f"{_prefix(namespace)}/o/{_group_part(group)}/{resource}/{name}"


def page_id(base: str, view: View, container: str | None = None) -> str:
    return f"{base}/{view}" if container is None else f"{base}/{view}/{container}"


def folder(node_id: str, name: str, *, table: bool = False) -> DirectoryNode:
    return DirectoryNode(
        id=node_id,
        name=name,
        has_children=True,
        representations=worded_titles([TABLE]) if table else [],
    )


def cluster_node() -> ReportNode:
    return ReportNode(
        id=CLUSTER,
        name=say("Cluster"),
        description=say("What the cluster says about itself"),
        has_children=True,
        representations=[],
    )


def namespaces_node() -> DirectoryNode:
    return folder(NAMESPACES, say("Namespaces"), table=True)


def scoped_node() -> DirectoryNode:
    return folder(SCOPED, say("Cluster resources"))


def namespace_node(namespace: str) -> DirectoryNode:
    name = say("All namespaces") if namespace == EVERY else namespace
    return folder(namespace_id(namespace), name)


def section_node(namespace: str | None, section: Section) -> DirectoryNode:
    return folder(section_id(namespace, section), say(SECTION_TITLES[section]))


def kind_title(resource: Resource) -> str:
    """A kind's folder is its plural as `kubectl api-resources` names it, with
    its group beside a custom one so two `Cluster` kinds are told apart."""
    if resource.section == "other" and resource.group:
        return f"{resource.resource} ({resource.group})"
    return resource.resource


def kind_node(namespace: str | None, resource: Resource) -> DirectoryNode:
    return folder(kind_id(namespace, resource), kind_title(resource), table=True)


def object_node(
    namespace: str | None,
    resource: Resource,
    name: str,
    *,
    summary: str | None,
    created_at: datetime | None,
    actions: list[str] | None = None,
) -> KubeObjectNode:
    return KubeObjectNode(
        id=object_id(namespace, resource.group, resource.resource, name),
        name=name,
        representations=worded_titles(OBJECT_OPENS),
        object_kind=resource.kind,
        namespace=namespace,
        summary=summary,
        created_at=created_at,
        actions=actions,
    )


def view_pages(named: Named, resource: Resource, containers: list[str]) -> list[ViewPage]:
    """The object's pages beside its view, each opening in a tab of its own (D423)."""
    assert named.name is not None
    base = object_id(named.namespace, resource.group, resource.resource, named.name)
    pages: list[ViewPage] = []

    def add(view: View, container: str | None = None) -> None:
        title, _ = _VIEW_TITLES[view]
        pages.append(
            ViewPage(
                node_id=page_id(base, view, container),
                title=say(title) if container is None else f"{say(title)}: {container}",
                representations=worded_titles([TABLE]),
                icon=_VIEW_ICONS[view],
            )
        )

    if resource.key == "/pods":
        for container in containers:
            add("logs", container)
    if resource.key in SELECTS_PODS:
        add("pods")
    add("events")
    return pages


def page_node(named: Named) -> ReportNode:
    assert named.view is not None
    title, description = _VIEW_TITLES[named.view]
    return ReportNode(
        id=page_id(
            object_id(named.namespace, named.group or "", named.resource or "", named.name or ""),
            named.view,
            named.container,
        ),
        name=say(title) if named.container is None else f"{say(title)}: {named.container}",
        description=say(description),
        has_children=False,
        representations=worded_titles([TABLE]),
    )
