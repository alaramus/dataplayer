"""Finding containers, images, volumes, networks and Compose projects by name,
and every name for a kept list (D416).

The API keeps no index a search could ask and pages nothing, so a search reads
the four lists once — what the catalog reads to show them — and keeps the
best-classed matches (D202, D213). An image is found by any of its tags.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.adapters.catalog import CatalogNode
from app.adapters.docker.catalog import (
    GROUPS,
    Group,
    container_node,
    group_node,
    image_node,
    network_node,
    parse,
    project_node,
    project_of,
    tags_of,
    volume_node,
)
from app.adapters.docker.inventory import (
    CEILING,
    read_containers,
    read_images,
    read_networks,
    read_volumes,
)
from app.adapters.docker.reports import in_section, is_section
from app.adapters.docker.session import DockerSession
from app.adapters.search import (
    Ancestor,
    Kept,
    KeptName,
    MatchClass,
    NameBatch,
    NodeMatch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    class_of_name,
    class_rank,
    words_of,
)
from app.core.translation import say


@dataclass(frozen=True)
class Found:
    node: CatalogNode
    # The level it is listed on, and the levels from the root to it.
    parent: CatalogNode
    above: tuple[CatalogNode, ...]
    # What the words are matched against: an image's every tag.
    names: tuple[str, ...]

    @property
    def location(self) -> str:
        return " · ".join(level.name for level in self.above)

    @property
    def ancestors(self) -> list[Ancestor]:
        return [Ancestor(node_id=level.id, name=level.name) for level in self.above]

    @property
    def full_name(self) -> str | None:
        """Every tag of an image with several; the node's own name otherwise."""
        return " ".join(self.names) if self.names != (self.node.name,) else None


async def everything(
    session: DockerSession, groups: set[Group] | None = None, project: str | None = None
) -> tuple[list[Found], bool]:
    """Every named thing of the daemon by level, and whether a list was cut."""
    wanted = groups or set(GROUPS)
    listed = await read_containers(session)
    containers, cut = listed.items, listed.cut
    found: list[Found] = []
    if "containers" in wanted:
        top = group_node("containers")
        names = sorted({project_of(one) for one in containers} - {""})
        if project is None:
            found += [
                Found(project_node(name), top, (top,), (name,)) for name in names
            ]
        for one in containers:
            own = project_of(one)
            if project is not None and own != project:
                continue
            level = project_node(own)
            container = container_node(one)
            found.append(Found(container, level, (top, level), (container.name,)))
    if "images" in wanted:
        top = group_node("images")
        images = await read_images(session)
        cut |= images.cut
        for image in images.items:
            pictured = image_node(image, containers)
            found.append(
                Found(pictured, top, (top,), tuple(tags_of(image)) or (pictured.name,))
            )
    if "volumes" in wanted:
        top = group_node("volumes")
        volumes = await read_volumes(session)
        cut |= volumes.cut
        for volume in volumes.items:
            kept = volume_node(volume, containers)
            found.append(Found(kept, top, (top,), (kept.name,)))
    if "networks" in wanted:
        top = group_node("networks")
        networks = await read_networks(session)
        cut |= networks.cut
        for network in networks.items:
            joined = network_node(network, containers)
            found.append(Found(joined, top, (top,), (joined.name,)))
    return found, cut


def best_class(words: tuple[str, ...], names: tuple[str, ...]) -> MatchClass | None:
    classes: list[MatchClass] = []
    for name in names:
        found = class_of_name(words, name)
        if found is not None:
            classes.append(found)
    if not classes:
        return None
    return min(classes, key=class_rank)


class DockerSearch:
    def __init__(self, session: DockerSession) -> None:
        self._session = session

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        del bounds
        words = words_of(request.query)
        if not words:
            raise ValueError(say("A search needs something to look for"))
        groups: set[Group] | None = None
        project: str | None = None
        if request.node_id:
            named = None if is_section(request.node_id) or in_section(request.node_id) else parse(request.node_id)
            if named is None or named.group is None:
                raise ValueError(say("A search starts at the top or in a list"))
            groups, project = {named.group}, named.project
        found, cut = await everything(self._session, groups, project)
        kept: Kept[tuple[int, int, Found]] = Kept(request.limit)
        for order, one in enumerate(found):
            match_class = best_class(words, one.names)
            if match_class is not None and kept.wants(match_class):
                kept.add(match_class, (class_rank(match_class), order, one))
        matches = [
            NodeMatch(
                node=one.node,
                parent_id=one.parent.id,
                location=one.location,
                ancestors=one.ancestors,
                full_name=one.full_name,
            )
            for _, _, one in sorted(kept.items(), key=lambda item: item[:2])
        ]
        notice = None
        if kept.dropped:
            notice = say(
                "More than {limit} matched; the best {limit} are shown",
                limit=request.limit,
            )
        elif cut:
            notice = say("Only the first {count} of each list were searched", count=CEILING)
        return NodeSearchResult(
            matches=matches, complete=notice is None, notice=notice, extent=len(found)
        )

    async def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        """Every container, image, volume, network and Compose project, at most
        `limit`, each scoped to its level (D213)."""
        del bounds
        found, cut = await everything(self._session)
        notice = None
        if len(found) > limit:
            found = found[:limit]
            notice = say(
                "More than {limit} names; the first {limit} are kept",
                limit=f"{limit:,}",
            )
        elif cut:
            notice = say("Only the first {count} of each list were searched", count=CEILING)
        yield NameBatch(
            names=[
                KeptName(
                    node=one.node,
                    parent_id=one.parent.id,
                    location=one.location,
                    ancestors=one.ancestors,
                    full_name=one.full_name,
                    scope=one.parent.id,
                )
                for one in found
            ],
            notice=notice,
        )

