"""A Docker daemon on another machine as a source (D405–D409).

Its containers, images, volumes and networks, a container's logs and
processes, and the daemon's own reports, read through one of the owner's SSH
connections. No driver of its own: the Engine API client is the one the
services use (D406), and `asyncssh` stays in the SSH adapter.
"""

import httpx

from app.adapters import jsontext
from app.adapters.catalog import CatalogNode
from app.adapters.content import ContentRequest, ContentResult, JsonContent, json_tree
from app.adapters.docker.catalog import (
    GROUPS,
    Group,
    Named,
    container_node,
    group_node,
    image_node,
    network_node,
    parse,
    project_node,
    project_of,
    views_of,
    volume_node,
)
from app.adapters.docker.inventory import (
    read_containers,
    read_images,
    read_networks,
    read_volumes,
)
from app.adapters.docker.options import DEFAULT_SOCKET, PODMAN_SOCKET, DockerOptions
from app.adapters.docker.reports import (
    REPORTS,
    in_section,
    is_section,
    read_report,
    report_for,
    report_node,
    section_node,
)
from app.adapters.docker.session import DockerSession, segment
from app.adapters.docker.tables import DockerTables
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import ConnectionCheckResult, NodeNotFound
from app.adapters.registry import AdapterContext, CatalogFace, register
from app.adapters.tunnels import TunnelAccess
from app.core.schemas import get_datetime_utc
from app.core.translation import N_, say

_INSPECT_PATHS = {
    "container": "/containers/{}/json",
    "image": "/images/{}/json",
    "volume": "/volumes/{}",
    "network": "/networks/{}",
}


class DockerAdapter:
    """Facade over a session and the capabilities built on it (D2b)."""

    def __init__(
        self,
        options: DockerOptions,
        tunnels: TunnelAccess | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._session = DockerSession(options, tunnels, transport)
        self._tables = DockerTables(self._session)

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def source_features(self) -> SourceFeatures:
        _, version = await self._session.get("/version")
        number = version.get("Version") if isinstance(version, dict) else None
        product = (version.get("Platform") or {}).get("Name") if isinstance(version, dict) else None
        return SourceFeatures(
            observed_at=get_datetime_utc(),
            server_version=None
            if number is None
            else f"{product or 'Docker'} {number}"[:100],
            features=[],
        )

    # --- the catalog (D407) --------------------------------------------------

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        if node_id is None:
            return [section_node(), *(group_node(group) for group in GROUPS)]
        if is_section(node_id):
            return [report_node(report) for report in REPORTS]
        if in_section(node_id):
            if report_for(node_id) is None:
                raise NodeNotFound(node_id)
            return []
        named = parse(node_id)
        if named.leaf is not None:
            if named.view is not None:
                return []
            await self._inspect(named)
            return views_of(named.leaf, named.key)
        return await self._level(named)

    async def _level(self, named: Named) -> list[CatalogNode]:
        containers = (await read_containers(self._session)).items
        if named.group == "containers":
            if named.project is None:
                projects = sorted({project_of(one) for one in containers})
                # Compose projects first by name, then the containers of none.
                return [
                    project_node(name)
                    for name in sorted(projects, key=lambda name: (name == "", name))
                ]
            chosen = [one for one in containers if project_of(one) == named.project]
            return sorted(
                (container_node(one) for one in chosen), key=lambda node: node.name
            )
        if named.group == "images":
            images = (await read_images(self._session)).items
            return sorted(
                (image_node(one, containers) for one in images),
                key=lambda node: node.name,
            )
        if named.group == "volumes":
            volumes = (await read_volumes(self._session)).items
            return sorted(
                (volume_node(one, containers) for one in volumes),
                key=lambda node: node.name,
            )
        networks = sorted(
            (network_node(one, containers) for one in (await read_networks(self._session)).items),
            key=lambda node: (node.network_kind != "built_in", node.name),
        )
        return list(networks)

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        if is_section(node_id):
            return [section_node()]
        if in_section(node_id):
            report = report_for(node_id)
            if report is None:
                raise NodeNotFound(node_id)
            return [section_node(), report_node(report)]
        named = parse(node_id)
        if named.leaf is None:
            assert named.group is not None
            top: list[CatalogNode] = [group_node(named.group)]
            if named.project is not None:
                top.append(project_node(named.project))
            return top
        found = await self._node(named)
        if found is None:
            raise NodeNotFound(node_id)
        node, project = found
        path: list[CatalogNode] = [group_node(_GROUP_OF[named.leaf])]
        if project is not None:
            path.append(project_node(project))
        path.append(node)
        if named.view is not None:
            path.extend(view for view in views_of(named.leaf, named.key) if view.id == node_id)
        return path

    async def _node(self, named: Named) -> tuple[CatalogNode, str | None] | None:
        """The leaf a node id names, as its level lists it, and its project."""
        containers = (await read_containers(self._session)).items
        if named.leaf == "container":
            for one in containers:
                if one.get("Id") == named.key:
                    return container_node(one), project_of(one)
            return None
        if named.leaf == "image":
            for one in (await read_images(self._session)).items:
                if one.get("Id") == named.key:
                    return image_node(one, containers), None
            return None
        if named.leaf == "volume":
            for one in (await read_volumes(self._session)).items:
                if one.get("Name") == named.key:
                    return volume_node(one, containers), None
            return None
        for one in (await read_networks(self._session)).items:
            if one.get("Id") == named.key:
                return network_node(one, containers), None
        return None

    # --- rows (D407, D408) ---------------------------------------------------

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if in_section(request.node_id):
            return await read_report(self._session, request)
        if is_section(request.node_id):
            raise ValueError(say("Open one of the System reports"))
        named = parse(request.node_id)
        if named.leaf is None:
            return await self._tables.group(request, named)
        if named.view in (None, "inspect"):
            raise ValueError(say("This opens as what the Docker server says about it"))
        return await self._tables.view(request, named)

    # --- what the daemon says about one thing (D408) -------------------------

    async def _inspect(self, named: Named) -> bytes:
        assert named.leaf is not None
        node_id = f"{named.leaf}:{named.key}"
        _, body = await self._session.raw(
            _INSPECT_PATHS[named.leaf].format(segment(named.key)), node_id=node_id
        )
        return body

    async def read_content(self, request: ContentRequest) -> ContentResult:
        if request.representation != "tree":
            raise ValueError(say("This opens as what the Docker server says about it"))
        named = parse(request.node_id)
        # The node itself, or its Inspect view: the same answer (D408).
        if named.leaf is None or named.view not in (None, "inspect"):
            raise ValueError(say("This opens as a table"))
        body = await self._inspect(named)
        try:
            return JsonContent(value=json_tree(jsontext.load(body.decode("utf-8"))))
        except ValueError:
            return JsonContent(
                source_text=body.decode("utf-8", errors="replace"),
                notice=say("The Docker server did not answer with JSON"),
            )


_GROUP_OF: dict[str, Group] = {
    "container": "containers",
    "image": "images",
    "volume": "volumes",
    "network": "networks",
}


@register(
    name="docker",
    title=N_("Docker"),
    category="containers",
    description=N_(
        "A Docker daemon on another machine, reached through one of your SSH "
        "connections. See its containers by Compose project, its images, "
        "volumes and networks, what the daemon says about each, a container's "
        "logs and processes, an image's layers, and the engine's disk usage "
        "and events."
    ),
    options_schema=DockerOptions,
    adapter_class=DockerAdapter,
    faces=(
        CatalogFace(key="docker", title=N_("Docker"), options={"socket": DEFAULT_SOCKET}),
        CatalogFace(
            key="podman",
            title=N_("Podman"),
            options={"socket": PODMAN_SOCKET},
            note=N_(
                "Podman's Docker-compatible API, with its socket switched on "
                "(podman.socket). A rootless Podman keeps it at "
                "/run/user/<uid>/podman/podman.sock."
            ),
        ),
    ),
)
def _build(options: DockerOptions, context: AdapterContext) -> DockerAdapter:
    return DockerAdapter(options, context.tunnels)
