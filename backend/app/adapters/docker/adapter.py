"""A Docker daemon on another machine as a source (D405–D417).

Its containers, images, volumes and networks, a container's logs and
processes, and the daemon's own reports, read through one of the owner's SSH
connections. No driver of its own: the Engine API client is the one the
services use (D406), and `asyncssh` stays in the SSH adapter.
"""

import json
from collections.abc import AsyncIterator
from typing import Any, ClassVar

import httpx

from app.adapters import jsontext
from app.adapters.actions import Action, ActionSet, ActionType
from app.adapters.catalog import CatalogNode
from app.adapters.changes import ChangeSink, ChangeWatch
from app.adapters.content import ContentRequest, ContentResult, JsonContent, json_tree
from app.adapters.docker.actions import (
    LEVEL_ACTIONS,
    LIFECYCLE,
    REMOVALS,
    plain_actions,
)
from app.adapters.docker.card import container_view
from app.adapters.docker.cards import image_view, network_view, volume_view
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
    view_pages,
    views_of,
    volume_node,
)
from app.adapters.docker.connect import OpenAsConnection
from app.adapters.docker.inventory import (
    read_containers,
    read_images,
    read_networks,
    read_volumes,
)
from app.adapters.docker.jobs import CommitContainer, PullImage, job_actions
from app.adapters.docker.metrics import PRESETS as METRIC_PRESETS
from app.adapters.docker.metrics import samples
from app.adapters.docker.options import (
    DEFAULT_SOCKET,
    PODMAN_SOCKET,
    DockerConnection,
    DockerOptions,
)
from app.adapters.docker.reports import (
    REPORTS,
    in_section,
    is_section,
    read_report,
    report_for,
    report_node,
    section_node,
)
from app.adapters.docker.search import DockerSearch
from app.adapters.docker.session import DockerSession, segment
from app.adapters.docker.tables import DockerTables
from app.adapters.docker.terminal import ContainerTerminal
from app.adapters.docker.watch import DockerWatch
from app.adapters.features import SourceFeatures
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.metrics import MetricPreset, MetricSample
from app.adapters.protocol import AdapterError, ConnectionCheckResult, NodeNotFound
from app.adapters.registry import AdapterContext, CatalogFace, register
from app.adapters.search import (
    LastSearch,
    NameBatch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    SearchedField,
    SourceCost,
)
from app.adapters.tunnels import TunnelAccess
from app.adapters.views import DocumentView
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

    # A container is not rows: Docker's tables are copied from the grid (D164).
    catalog_clipboard: ClassVar[bool] = False

    def __init__(
        self,
        options: DockerConnection,
        tunnels: TunnelAccess | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._session = DockerSession(options, tunnels, transport)
        self._tables = DockerTables(self._session)
        self._search = DockerSearch(self._session)
        self._connect = OpenAsConnection(self._session)
        self._actions = ActionSet(
            plain_actions(self._session)
            + job_actions(self._session)
            + [ContainerTerminal(self._session), self._connect]
        )

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
            # Keep the missing-node refusal while this node no longer exposes
            # its pages as a catalog level (D423).
            await self._inspect(named)
            return []
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
        if request.representation not in ("tree", "view"):
            raise ValueError(say("This opens as what the Docker server says about it"))
        named = parse(request.node_id)
        # The node itself, or its Inspect view: the same answer (D408).
        if named.leaf is None or named.view not in (None, "inspect"):
            raise ValueError(say("This opens as a table"))
        body = await self._inspect(named)
        if request.representation == "view":
            # The same inspect the tree draws, read as what it means (D422).
            try:
                document = json.loads(body)
            except ValueError:
                document = None
            if not isinstance(document, dict):
                raise AdapterError("unknown", say("The Docker server did not answer with JSON"))
            return await self._view(named, document)
        try:
            return JsonContent(value=json_tree(jsontext.load(body.decode("utf-8"))))
        except ValueError:
            return JsonContent(
                source_text=body.decode("utf-8", errors="replace"),
                notice=say("The Docker server did not answer with JSON"),
            )


    async def _view(self, named: Named, inspect: dict[str, Any]) -> DocumentView:
        assert named.leaf is not None
        if named.leaf == "container":
            document = container_view(inspect)
        elif named.leaf == "network":
            # A network's inspect names its own containers.
            document = network_view(inspect)
        else:
            # Who uses an image or mounts a volume is counted from the containers,
            # which the levels read the same way (D407).
            containers = (await read_containers(self._session)).items
            if named.leaf == "image":
                document = image_view(inspect, containers)
            else:
                document = volume_view(inspect, containers)
        return document.model_copy(update={"pages": view_pages(named.leaf, named.key)})

    # --- metrics and search (D415, D416) ------------------------------------------

    async def metric_samples(self) -> list[MetricSample]:
        return await samples(self._session)

    @classmethod
    def metric_presets(cls) -> tuple[MetricPreset, ...]:
        return METRIC_PRESETS

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        return await self._search.search_nodes(request, bounds)

    def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        return self._search.enumerate_names(limit, bounds)

    @classmethod
    def search_cost(cls, field: SearchedField, last: LastSearch | None) -> SourceCost:
        """Names are four lists read whole, whatever the daemon holds; nothing
        else is searched."""
        del last
        return "cheap" if field == "names" else "costly"

    # --- told when what is on screen changes (D414, D303) -----------------------

    async def watch_changes(self, sink: ChangeSink) -> ChangeWatch:
        return DockerWatch(self._session, sink)

    # --- what may be done (D410–D412) ------------------------------------------

    @classmethod
    def action_types(cls) -> tuple[ActionType, ...]:
        levels = tuple(kind for kinds in LEVEL_ACTIONS.values() for kind in kinds)
        return (
            *LIFECYCLE,
            ContainerTerminal,
            OpenAsConnection,
            CommitContainer,
            *REMOVALS.values(),
            PullImage,
            *levels,
        )

    def action(self, name: str) -> Action[Any]:
        return self._actions.get(name)

    async def all_actions(self) -> list[Action[Any]]:
        return list(self._actions)

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        """What a node or a level admits; state is judged when it runs (D9)."""
        if node_id is None or is_section(node_id) or in_section(node_id):
            return []
        try:
            named = parse(node_id)
        except ValueError:
            return []
        if named.view is not None:
            return []
        wanted: set[str] = set()
        if named.leaf == "container":
            wanted = {kind.name for kind in LIFECYCLE} | {
                REMOVALS["container"].name,
                CommitContainer.name,
                ContainerTerminal.name,
            }
            # Offered only where a type declares the image (D417): one read of
            # the container, the menu's own.
            if await self._connect.offered(node_id):
                wanted.add(OpenAsConnection.name)
        elif named.leaf is not None:
            wanted = {REMOVALS[named.leaf].name}
        elif named.project:
            wanted = {kind.name for kind in LIFECYCLE}
        elif named.group is not None and named.project is None:
            wanted = {kind.name for kind in LEVEL_ACTIONS.get(named.group, ())}
            if named.group == "images":
                wanted.add(PullImage.name)
        return [action for action in self._actions if action.name in wanted]


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
        "connections or over TCP with TLS. See its containers by Compose project, its images, "
        "volumes and networks, what the daemon says about each, a container's "
        "logs and processes, an image's layers, and the engine's disk usage "
        "and events. Running containers are measured for dashboards, and a "
        "database's container opens as a connection of its own."
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
def _build(options: DockerConnection, context: AdapterContext) -> DockerAdapter:
    return DockerAdapter(options, context.tunnels)
