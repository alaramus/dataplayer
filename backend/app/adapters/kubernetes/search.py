"""Finding namespaces and objects by name, and every name for a kept list (D476).

The API keeps no index a search could ask, so a search reads the lists of the
kinds a person looks for most — namespaces, pods, Deployments, StatefulSets,
Services, ConfigMaps, Secrets (their names: a list of metadata never carries
a value) and nodes — as metadata alone, and keeps the best-classed matches
(D202, D213). Each is placed under its kind in its own namespace, as the
catalog lists it. A list past `MOST` items says the search stopped short.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.adapters.catalog import CatalogNode
from app.adapters.kubernetes.catalog import (
    EVERY,
    kind_node,
    namespace_node,
    namespaces_node,
    object_node,
    parse,
    scoped_node,
    section_node,
)
from app.adapters.kubernetes.discovery import Discovery, Resource, Section
from app.adapters.kubernetes.session import METADATA, Forbidden, KubernetesSession
from app.adapters.kubernetes.tables import MOST, PAGE, instant
from app.adapters.protocol import AdapterError
from app.adapters.search import (
    Ancestor,
    Kept,
    KeptName,
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

# By `group/resource`, as a person looks for them.
SEARCHED: tuple[tuple[str, str], ...] = (
    ("", "pods"),
    ("apps", "deployments"),
    ("apps", "statefulsets"),
    ("", "services"),
    ("", "configmaps"),
    ("", "secrets"),
    ("", "nodes"),
)


@dataclass(frozen=True)
class Found:
    node: CatalogNode
    # The level it is listed on, and the levels from the root to it.
    above: tuple[CatalogNode, ...]
    section: Section | None = None

    @property
    def parent_id(self) -> str:
        return self.above[-1].id

    @property
    def location(self) -> str:
        return " · ".join(level.name for level in self.above)

    @property
    def ancestors(self) -> list[Ancestor]:
        return [Ancestor(node_id=level.id, name=level.name) for level in self.above]


async def _metadata(session: KubernetesSession, path: str, asked: Forbidden) -> tuple[list[dict[str, Any]], bool]:
    """Every item's metadata, page by page up to `MOST`, and whether it was cut."""
    items: list[dict[str, Any]] = []
    token = ""
    while True:
        params: dict[str, str | int] = {"limit": PAGE}
        if token:
            params["continue"] = token
        answer = await session.get(path, params, asked=asked, accept=METADATA)
        page = answer.get("items") if isinstance(answer, dict) else None
        items += [one.get("metadata") or {} for one in page or [] if isinstance(one, dict)]
        token = str(((answer or {}).get("metadata") or {}).get("continue") or "")
        if not token:
            return items, False
        if len(items) >= MOST:
            return items[:MOST], True


def _above(namespace: str | None, resource: Resource) -> tuple[CatalogNode, ...]:
    top: tuple[CatalogNode, ...] = (
        (namespaces_node(), namespace_node(namespace)) if namespace is not None else (scoped_node(),)
    )
    return (*top, section_node(namespace, resource.section), kind_node(namespace, resource))


async def everything(
    session: KubernetesSession,
    discovery: Discovery,
    held_to: str | None,
    *,
    namespace: str | None = None,
    only: Resource | None = None,
) -> tuple[list[Found], bool]:
    """Every searched name of the cluster, or of one namespace or one kind,
    and whether a list was cut. A kind this connection may not list is left
    out rather than failing the search."""
    scope = held_to or namespace
    found: list[Found] = []
    cut = False
    if only is None and namespace is None and held_to is None:
        try:
            listed, short = await _metadata(session, "/api/v1/namespaces", Forbidden("list", "namespaces"))
        except AdapterError as failure:
            if failure.error_kind != "auth":
                raise
            listed, short = [], False
        cut |= short
        top = namespaces_node()
        found += [Found(namespace_node(str(one.get("name"))), (top,)) for one in listed if one.get("name")]
    for group, name in SEARCHED:
        resource = await discovery.find(group, name)
        if resource is None or (only is not None and resource.key != only.key):
            continue
        if not resource.namespaced and scope is not None:
            continue
        try:
            listed, short = await _metadata(session, resource.base(scope), resource.asked("list"))
        except AdapterError as failure:
            if failure.error_kind != "auth":
                raise
            continue
        cut |= short
        for metadata in listed:
            object_name = str(metadata.get("name") or "")
            if not object_name:
                continue
            own = str(metadata.get("namespace") or "") if resource.namespaced else None
            node = object_node(
                own,
                resource,
                object_name,
                summary=None,
                created_at=instant(metadata.get("creationTimestamp")),
            )
            found.append(Found(node, _above(own, resource), resource.section))
    return found, cut


def _scope_of(node_id: str | None) -> tuple[str | None, tuple[str, str] | None, Section | None]:
    """The namespace and the kind a search starts in: the top, the list of
    namespaces, a namespace, a section or a kind; an object or a Cluster
    report is refused."""
    if not node_id:
        return None, None, None
    named = parse(node_id)
    if named.name is not None or named.top == "cluster":
        raise ValueError(say("A search starts at the top, in a namespace or in a kind"))
    namespace = None if named.namespace in (None, EVERY) else named.namespace
    kind = (named.group or "", named.resource) if named.resource is not None else None
    return namespace, kind, named.section


class KubernetesSearch:
    def __init__(self, session: KubernetesSession, discovery: Discovery, held_to: str | None) -> None:
        self._session = session
        self._discovery = discovery
        self._held_to = held_to

    async def search_nodes(self, request: NodeSearchRequest, bounds: SearchBounds | None = None) -> NodeSearchResult:
        del bounds
        words = words_of(request.query)
        if not words:
            raise ValueError(say("A search needs something to look for"))
        namespace, kind, section = _scope_of(request.node_id)
        only = None
        if kind is not None:
            only = await self._discovery.find(*kind)
            if only is None:
                raise ValueError(say("A search starts at the top, in a namespace or in a kind"))
        found, cut = await everything(
            self._session, self._discovery, self._held_to, namespace=namespace, only=only
        )
        if request.node_id == "namespaces":
            found = [one for one in found if len(one.above) == 1]
        elif section is not None:
            found = [one for one in found if one.section == section]
        kept: Kept[tuple[int, int, Found]] = Kept(request.limit)
        for order, one in enumerate(found):
            match_class = class_of_name(words, one.node.name)
            if match_class is not None and kept.wants(match_class):
                kept.add(match_class, (class_rank(match_class), order, one))
        matches = [
            NodeMatch(node=one.node, parent_id=one.parent_id, location=one.location, ancestors=one.ancestors)
            for _, _, one in sorted(kept.items(), key=lambda item: item[:2])
        ]
        notice = None
        if kept.dropped:
            notice = say("More than {limit} matched; the best {limit} are shown", limit=request.limit)
        elif cut:
            notice = say("Only the first {count} of each list were searched", count=MOST)
        return NodeSearchResult(matches=matches, complete=notice is None, notice=notice, extent=len(found))

    async def enumerate_names(self, limit: int, bounds: SearchBounds) -> AsyncIterator[NameBatch]:
        """Every searched name, at most `limit`, each scoped to its level (D213)."""
        del bounds
        found, cut = await everything(self._session, self._discovery, self._held_to)
        notice = None
        if len(found) > limit:
            found = found[:limit]
            notice = say("More than {limit} names; the first {limit} are kept", limit=f"{limit:,}")
        elif cut:
            notice = say("Only the first {count} of each list were searched", count=MOST)
        yield NameBatch(
            names=[
                KeptName(
                    node=one.node,
                    parent_id=one.parent_id,
                    location=one.location,
                    ancestors=one.ancestors,
                    scope=one.parent_id,
                )
                for one in found
            ],
            notice=notice,
        )

