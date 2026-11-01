"""Finding topics and consumer groups by name, and every name for a kept list (D310).

Kafka has no index over names and no tree either: every topic is one metadata
request and every group one listing, so a search reads them all and keeps the
best-classed matches (D202, D213).
"""

from collections.abc import AsyncIterator

from app.adapters.catalog import CatalogNode
from app.adapters.kafka.catalog import (
    GROUPS,
    INTERNAL,
    TOPICS,
    folder_of,
    group_node,
    is_internal,
    partitions_of,
    topic_node,
    watermarks,
)
from app.adapters.kafka.session import TIMEOUT_SECONDS, KafkaClients, KafkaSession
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

LEVELS = (TOPICS, GROUPS, INTERNAL)


def everything(
    clients: KafkaClients, levels: tuple[str, ...]
) -> list[tuple[str, CatalogNode]]:
    """Every topic and group on the levels asked for, with the level it is on.

    Topics are described without their message counts: a search does not ask
    for every partition's offsets.
    """
    found: list[tuple[str, CatalogNode]] = []
    if TOPICS in levels or INTERNAL in levels:
        for name, partitions in sorted(partitions_of(clients).items()):
            level = INTERNAL if is_internal(name) else TOPICS
            if level in levels:
                found.append((level, topic_node(name, partitions, {})))
    if GROUPS in levels:
        listed = (
            clients.admin()
            .list_consumer_groups(request_timeout=TIMEOUT_SECONDS)
            .result()
        )
        for group in sorted(listing.group_id for listing in listed.valid):
            found.append((GROUPS, group_node(group, "unknown", None)))
    return found


def match_of(level: str, node: CatalogNode) -> NodeMatch:
    folder = folder_of(level)
    return NodeMatch(
        node=node,
        parent_id=level,
        location=folder.name,
        ancestors=[Ancestor(node_id=level, name=folder.name)],
    )


def counted(clients: KafkaClients, matches: list[NodeMatch]) -> list[NodeMatch]:
    """The found topics given their message counts, asked for together."""
    topics = {match.node.name for match in matches if match.node.kind == "topic"}
    if not topics:
        return matches
    known = partitions_of(clients)
    wanted = {name: known[name] for name in topics if name in known}
    marks = watermarks(clients, wanted)
    return [
        match.model_copy(
            update={"node": topic_node(match.node.name, wanted[match.node.name], marks)}
        )
        if match.node.kind == "topic" and match.node.name in wanted
        else match
        for match in matches
    ]


class KafkaSearch:
    def __init__(self, session: KafkaSession) -> None:
        self._session = session

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        del bounds
        words = words_of(request.query)
        if not words:
            raise ValueError(say("A search needs something to look for"))
        levels = LEVELS if request.node_id not in LEVELS else (request.node_id,)

        def search(clients: KafkaClients) -> NodeSearchResult:
            found = everything(clients, levels)
            kept: Kept[tuple[int, int, str, CatalogNode]] = Kept(request.limit)
            for order, (level, node) in enumerate(found):
                match_class = class_of_name(words, node.name)
                if match_class is not None and kept.wants(match_class):
                    kept.add(match_class, (class_rank(match_class), order, level, node))
            matches = counted(
                clients,
                [
                    match_of(level, node)
                    for _, _, level, node in sorted(
                        kept.items(), key=lambda item: item[:2]
                    )
                ],
            )
            notice = None
            if kept.dropped:
                notice = say(
                    "More than {limit} matched; the best {limit} are shown",
                    limit=request.limit,
                )
            return NodeSearchResult(
                matches=matches,
                complete=notice is None,
                notice=notice,
                extent=len(found),
            )

        return await self._session.run(search)

    async def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        """Every topic and group, at most `limit`, each scoped to its level (D213)."""
        del bounds
        found = await self._session.run(lambda clients: everything(clients, LEVELS))
        notice = None
        if len(found) > limit:
            found = found[:limit]
            notice = say(
                "More than {limit} names; the first {limit} are kept",
                limit=f"{limit:,}",
            )
        yield NameBatch(
            names=[
                KeptName(
                    node=node,
                    parent_id=level,
                    location=folder_of(level).name,
                    ancestors=[Ancestor(node_id=level, name=folder_of(level).name)],
                    scope=level,
                )
                for level, node in found
            ],
            notice=notice,
        )
