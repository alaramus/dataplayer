"""Node ids of a Docker source, and the nodes the catalog shows (D407).

A node is named by what the daemon will not reuse: `container:<64 hex>`,
`image:sha256:<64 hex>`, `volume:<name>`, `network:<64 hex>`. A view of one
is its id and `/logs`, `/processes`, `/history` or `/containers`. Every id is
matched against its pattern before a request is built from it.
"""

import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote, unquote

from app.adapters.catalog import (
    CatalogNode,
    ContainerNode,
    DirectoryNode,
    ImageNode,
    NetworkNode,
    ReportNode,
    VolumeNode,
)
from app.adapters.content import NodeRepresentation
from app.adapters.docker.inventory import (
    COMPOSE_PROJECT,
    COMPOSE_SERVICE,
    datetime_of,
    instant,
    labels_of,
    moment,
    name_of,
    network_kind,
    ports_of,
    state_of,
    users_of_image,
    users_of_network,
    users_of_volume,
)
from app.adapters.words import worded_titles
from app.core.translation import N_, say

Group = Literal["containers", "images", "volumes", "networks"]
GROUPS: tuple[Group, ...] = ("containers", "images", "volumes", "networks")
_GROUP_TITLES: dict[Group, str] = {
    "containers": N_("Containers"),
    "images": N_("Images"),
    "volumes": N_("Volumes"),
    "networks": N_("Networks"),
}
STANDALONE = "standalone"
PROJECT = "project:"

Leaf = Literal["container", "image", "volume", "network"]
View = Literal["inspect", "logs", "processes", "history", "containers"]
_VIEWS: dict[Leaf, tuple[View, ...]] = {
    "container": ("inspect", "logs", "processes"),
    "image": ("inspect", "history"),
    "volume": ("inspect", "containers"),
    "network": ("inspect", "containers"),
}
_VIEW_TITLES: dict[View, tuple[str, str]] = {
    "inspect": (N_("Inspect"), N_("What the Docker server says about it")),
    "logs": (N_("Logs"), N_("What it printed, newest first")),
    "processes": (N_("Processes"), N_("What runs inside it now")),
    "history": (N_("History"), N_("Its layers and the instructions that made them")),
    "containers": (N_("Containers"), N_("The containers that use it")),
}

_HEX = re.compile(r"^[0-9a-f]{64}$")
_IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
# Docker's rule for a volume's name.
_VOLUME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
_PATTERNS: dict[Leaf, re.Pattern[str]] = {
    "container": _HEX,
    "image": _IMAGE,
    "volume": _VOLUME,
    "network": _HEX,
}

TABLE = NodeRepresentation(kind="table", title=N_("View as table"))
INSPECT = NodeRepresentation(kind="tree", title=N_("Inspect"))


@dataclass(frozen=True)
class Named:
    """What a node id names."""

    group: Group | None = None
    # A Compose project's name, or "" for the containers of none.
    project: str | None = None
    leaf: Leaf | None = None
    key: str = ""
    view: View | None = None


def parse(node_id: str) -> Named:
    """The parts of a node id of this source, or a refusal."""
    if node_id in GROUPS:
        return Named(group=node_id)
    if node_id == STANDALONE:
        return Named(group="containers", project="")
    if node_id.startswith(PROJECT) and len(node_id) > len(PROJECT):
        return Named(group="containers", project=unquote(node_id[len(PROJECT) :]))
    prefix, colon, rest = node_id.partition(":")
    if not colon or prefix not in _PATTERNS:
        raise ValueError(say("Not a node of this connection"))
    leaf: Leaf = prefix
    key, slash, view = rest.partition("/")
    if not _PATTERNS[leaf].match(key):
        raise ValueError(say("Not a node of this connection"))
    if not slash:
        return Named(leaf=leaf, key=key)
    if view not in _VIEWS[leaf]:
        raise ValueError(say("Not a node of this connection"))
    return Named(leaf=leaf, key=key, view=view)


def leaf_id(leaf: Leaf, key: str) -> str:
    return f"{leaf}:{key}"


def view_id(leaf: Leaf, key: str, view: View) -> str:
    return f"{leaf}:{key}/{view}"


def project_id(project: str) -> str:
    return STANDALONE if project == "" else PROJECT + quote(project, safe="")


def group_node(group: Group) -> DirectoryNode:
    return DirectoryNode(
        id=group,
        name=say(_GROUP_TITLES[group]),
        has_children=True,
        representations=worded_titles([TABLE]),
    )


def project_node(project: str) -> DirectoryNode:
    return DirectoryNode(
        id=project_id(project),
        name=project or say("Standalone"),
        has_children=True,
        representations=worded_titles([TABLE]),
    )


def view_node(leaf: Leaf, key: str, view: View) -> ReportNode:
    title, description = _VIEW_TITLES[view]
    return ReportNode(
        id=view_id(leaf, key, view),
        name=say(title),
        description=say(description),
        has_children=False,
        representations=worded_titles([INSPECT if view == "inspect" else TABLE]),
    )


def views_of(leaf: Leaf, key: str) -> list[CatalogNode]:
    return [view_node(leaf, key, view) for view in _VIEWS[leaf]]


def project_of(container: dict[str, Any]) -> str:
    return labels_of(container).get(COMPOSE_PROJECT, "")


def container_node(container: dict[str, Any]) -> ContainerNode:
    labels = labels_of(container)
    return ContainerNode(
        id=leaf_id("container", str(container.get("Id"))),
        name=name_of(container),
        representations=worded_titles([INSPECT]),
        state=state_of(container),
        status=str(container["Status"]) if container.get("Status") else None,
        image=str(container["Image"]) if container.get("Image") else None,
        project=labels.get(COMPOSE_PROJECT),
        service=labels.get(COMPOSE_SERVICE),
        ports=ports_of(container),
    )


def tags_of(image: dict[str, Any]) -> list[str]:
    return [str(tag) for tag in image.get("RepoTags") or [] if tag and tag != "<none>:<none>"]


def image_title(image: dict[str, Any]) -> str:
    tags = tags_of(image)
    if tags:
        return tags[0]
    return "<none> " + str(image.get("Id", "")).removeprefix("sha256:")[:12]


def image_node(image: dict[str, Any], containers: list[dict[str, Any]]) -> ImageNode:
    image_id = str(image.get("Id"))
    size = image.get("Size")
    return ImageNode(
        id=leaf_id("image", image_id),
        name=image_title(image),
        representations=worded_titles([INSPECT]),
        tags=tags_of(image),
        size_bytes=size if isinstance(size, int) and size >= 0 else None,
        created_at=datetime_of(moment(image.get("Created"))),
        containers=len(users_of_image(containers, image_id)),
    )


def volume_node(volume: dict[str, Any], containers: list[dict[str, Any]]) -> VolumeNode:
    name = str(volume.get("Name"))
    return VolumeNode(
        id=leaf_id("volume", name),
        name=name,
        representations=worded_titles([INSPECT]),
        driver=str(volume.get("Driver") or "local"),
        created_at=datetime_of(instant(volume.get("CreatedAt"))),
        containers=len(users_of_volume(containers, name)),
    )


def network_node(network: dict[str, Any], containers: list[dict[str, Any]]) -> NetworkNode:
    return NetworkNode(
        id=leaf_id("network", str(network.get("Id"))),
        name=str(network.get("Name")),
        representations=worded_titles([INSPECT]),
        driver=str(network.get("Driver") or ""),
        scope=str(network["Scope"]) if network.get("Scope") else None,
        internal=bool(network.get("Internal")),
        network_kind=network_kind(network),
        containers=len(users_of_network(containers, network)),
    )
