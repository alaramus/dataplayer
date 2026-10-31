"""Finding znodes by name, and every name for a kept list (D202, D213, D301).

ZooKeeper has no index over names, so a search walks the tree below where it
starts, a level at a time, bounded by how many znodes it looks at and by the
clock rather than by how many match. A level this connection may not list is
passed over and the answer says it is not complete.

A found znode carries its ancestors, which are its path's parents, so the tree
can show it where it lies (D91).
"""

from collections import deque
from collections.abc import AsyncIterator, Iterable

from kazoo.client import KazooClient
from kazoo.exceptions import NoAuthError, NoNodeError

from app.adapters.protocol import NodeNotFound
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
    out_of_time,
    words_of,
)
from app.adapters.zookeeper.session import ZookeeperSession
from app.adapters.zookeeper.znodes import (
    ancestors_of,
    checked_path,
    child_path,
    name_of,
    stat_of,
    unreadable_node,
    znode_node,
)
from app.core.translation import say

# How many znodes one search looks at. A bound on the walk, not on the
# matches, so a rare word costs what a common one does.
MAX_LOOKED_AT = 50_000

# How many found znodes are described per round of asking.
DESCRIBE_BATCH = 500


def placed(client: KazooClient, paths: Iterable[str]) -> list[NodeMatch]:
    """Found paths as the catalog lists them, asked for together.

    One gone since the walk met it is left out, as the listing leaves it out.
    """
    asked = [(path, client.exists_async(path)) for path in paths]
    matches: list[NodeMatch] = []
    for path, pending in asked:
        try:
            raw = pending.get()
        except NoAuthError:
            node = unreadable_node(path)
        else:
            if raw is None:
                continue
            node = znode_node(path, stat_of(raw), False)
        above = ancestors_of(path)[:-1]
        parent = above[-1] if above else None
        matches.append(
            NodeMatch(
                node=node,
                parent_id=parent,
                location=parent or "/",
                ancestors=[Ancestor(node_id=one, name=name_of(one)) for one in above],
                full_name=path,
            )
        )
    return matches


def walk(
    client: KazooClient, start: str, bounds: SearchBounds | None
) -> tuple[list[str], str | None, bool]:
    """Every path below `start`, breadth first, within the ceilings.

    Returns the paths, the notice of a ceiling that stopped the walk, and
    whether a level could not be listed.
    """
    pending: deque[str] = deque([start])
    found: list[str] = []
    passed_over = False
    while pending:
        if bounds is not None and bounds.over():
            return found, out_of_time(len(found), "entries"), passed_over
        if len(found) >= MAX_LOOKED_AT:
            return (
                found,
                say(
                    "More than {count} znodes were looked at; the search stopped there",
                    count=f"{MAX_LOOKED_AT:,}",
                ),
                passed_over,
            )
        here = pending.popleft()
        try:
            names = sorted(client.get_children(here))
        except NoAuthError:
            passed_over = True
            continue
        except NoNodeError:
            if here == start:
                raise
            continue
        for name in names:
            path = child_path(here, name)
            found.append(path)
            pending.append(path)
    return found, None, passed_over


class ZookeeperSearch:
    def __init__(self, session: ZookeeperSession) -> None:
        self._session = session

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = words_of(request.query)
        if not words:
            raise ValueError(say("A search needs something to look for"))
        start = "/" if request.node_id is None else checked_path(request.node_id)

        def search(client: KazooClient) -> NodeSearchResult:
            paths, notice, passed_over = walk(client, start, bounds)
            kept: Kept[tuple[int, int, str]] = Kept(request.limit)
            for order, path in enumerate(paths):
                match_class = class_of_name(words, name_of(path))
                if match_class is not None and kept.wants(match_class):
                    kept.add(match_class, (class_rank(match_class), order, path))
            matches = placed(client, (path for _, _, path in sorted(kept.items())))
            if notice is None and kept.dropped:
                notice = say(
                    "More than {limit} matched; the best {limit} are shown", limit=request.limit
                )
            if notice is None and passed_over:
                notice = say("Some levels may not be listed by this connection and were not searched")
            return NodeSearchResult(
                matches=matches, complete=notice is None, notice=notice, extent=len(paths)
            )

        try:
            return await self._session.run(search, start)
        except NodeNotFound:
            raise NodeNotFound(request.node_id or "/") from None

    async def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        """Every znode's name, at most `limit`, for a kept list (D213).

        The tree is one scope: a walk that stopped short, or passed over a level
        it may not list, says so, and what was kept before stays.
        """

        def read(client: KazooClient) -> tuple[list[NodeMatch], str | None, bool]:
            paths, notice, passed_over = walk(client, "/", bounds)
            if len(paths) > limit:
                paths = paths[:limit]
                notice = say(
                    "More than {limit} znodes; the first {limit} are kept", limit=f"{limit:,}"
                )
            matches: list[NodeMatch] = []
            for start in range(0, len(paths), DESCRIBE_BATCH):
                matches.extend(placed(client, paths[start : start + DESCRIBE_BATCH]))
            return matches, notice, passed_over

        matches, notice, passed_over = await self._session.run(read)
        for start in range(0, len(matches), DESCRIBE_BATCH):
            yield NameBatch(
                names=[
                    KeptName(
                        node=match.node,
                        parent_id=match.parent_id,
                        location=match.location,
                        ancestors=match.ancestors,
                        full_name=match.full_name,
                        scope="/",
                    )
                    for match in matches[start : start + DESCRIBE_BATCH]
                ]
            )
        if notice is not None or passed_over:
            yield NameBatch(unread=["/"] if passed_over else [], notice=notice)
