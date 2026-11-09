"""Finding queues, streams and exchanges by name, and every name for a kept
list (D331).

The management API lists them across virtual hosts a page at a time and keeps
no index a search could ask, so a search reads the names and keeps the
best-classed matches (D202, D213), each scoped to its level.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.adapters.catalog import CatalogNode
from app.adapters.rabbitmq.catalog import (
    FOLDERS,
    Folder,
    exchange_node,
    folder_id,
    folder_node,
    queue_node,
    vhost_id,
)
from app.adapters.rabbitmq.session import RabbitmqSession, segment
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

PAGE = 500
# Pages a search reads of each listing before it stops and says so.
PAGES = 20

_QUEUE_COLUMNS = (
    "name,vhost,type,state,messages,messages_ready,messages_unacknowledged,consumers"
)
_EXCHANGE_COLUMNS = "name,vhost,type,durable,internal"


@dataclass(frozen=True)
class Found:
    folder: Folder
    vhost: str
    node: CatalogNode


async def _pages(
    session: RabbitmqSession, path: str, columns: str
) -> tuple[list[dict[str, Any]], bool]:
    """Every item of a listing up to the ceiling, and whether it stopped short."""
    items: list[dict[str, Any]] = []
    for number in range(1, PAGES + 1):
        answer = await session.api(
            path,
            {
                "page": str(number),
                "page_size": str(PAGE),
                "sort": "name",
                "columns": columns,
            },
        )
        if not isinstance(answer, dict):
            break
        items += [one for one in answer.get("items", []) if isinstance(one, dict)]
        if number >= int(answer.get("page_count", 0) or 0):
            return items, False
    return items, True


async def everything(
    session: RabbitmqSession, folders: set[Folder] | None = None
) -> tuple[list[Found], bool]:
    """Every queue, stream and exchange the connection sees, by level."""
    own = session.options.vhost
    scope = f"/{segment(own)}" if own else ""
    wanted = folders or {"queues", "streams", "exchanges"}
    found: list[Found] = []
    stopped = False
    if wanted & {"queues", "streams"}:
        queues, cut = await _pages(session, f"/queues{scope}", _QUEUE_COLUMNS)
        stopped |= cut
        for row in queues:
            vhost = str(row.get("vhost", ""))
            folder: Folder = "streams" if row.get("type") == "stream" else "queues"
            if folder in wanted:
                found.append(Found(folder, vhost, queue_node(vhost, row)))
    if "exchanges" in wanted:
        exchanges, cut = await _pages(session, f"/exchanges{scope}", _EXCHANGE_COLUMNS)
        stopped |= cut
        for row in exchanges:
            vhost = str(row.get("vhost", ""))
            found.append(Found("exchanges", vhost, exchange_node(vhost, row)))
    return found, stopped


def _ancestors(one: Found, several: bool) -> list[Ancestor]:
    folder = folder_node(one.folder, one.vhost)
    path = [Ancestor(node_id=folder.id, name=folder.name)]
    if several:
        path.insert(0, Ancestor(node_id=vhost_id(one.vhost), name=one.vhost))
    return path


def _location(one: Found, several: bool) -> str:
    name = folder_node(one.folder, one.vhost).name
    return f"{one.vhost} · {name}" if several else name


async def _several(session: RabbitmqSession) -> bool:
    """Whether the top lists virtual hosts, so a path starts with one."""
    if session.options.vhost:
        return False
    answer = await session.api("/vhosts", {"columns": "name"})
    return len(answer or []) > 1


class RabbitmqSearch:
    def __init__(self, session: RabbitmqSession) -> None:
        self._session = session

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        del bounds
        words = words_of(request.query)
        if not words:
            raise ValueError(say("A search needs something to look for"))
        folders: set[Folder] | None = None
        within: str | None = None
        if request.node_id:
            prefix, _, _ = request.node_id.partition(":")
            for folder in FOLDERS:
                if prefix == folder:
                    folders = {folder}
                    within = request.node_id
        found, stopped = await everything(self._session, folders)
        if within is not None:
            found = [one for one in found if folder_id(one.folder, one.vhost) == within]
        several = await _several(self._session)
        kept: Kept[tuple[int, int, Found]] = Kept(request.limit)
        for order, one in enumerate(found):
            match_class = class_of_name(words, one.node.name)
            if match_class is not None and kept.wants(match_class):
                kept.add(match_class, (class_rank(match_class), order, one))
        matches = [
            NodeMatch(
                node=one.node,
                parent_id=folder_id(one.folder, one.vhost),
                location=_location(one, several),
                ancestors=_ancestors(one, several),
            )
            for _, _, one in sorted(kept.items(), key=lambda item: item[:2])
        ]
        notice = None
        if kept.dropped:
            notice = say(
                "More than {limit} matched; the best {limit} are shown",
                limit=request.limit,
            )
        elif stopped:
            notice = say(
                "Only the first {count} of each list were searched", count=PAGE * PAGES
            )
        return NodeSearchResult(
            matches=matches, complete=notice is None, notice=notice, extent=len(found)
        )

    async def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        """Every queue, stream and exchange, at most `limit`, each scoped to its
        level (D213)."""
        del bounds
        found, _ = await everything(self._session)
        several = await _several(self._session)
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
                    node=one.node,
                    parent_id=folder_id(one.folder, one.vhost),
                    location=_location(one, several),
                    ancestors=_ancestors(one, several),
                    scope=folder_id(one.folder, one.vhost),
                )
                for one in found
            ],
            notice=notice,
        )
