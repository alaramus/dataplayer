"""Finding databases, collections and reports by name (D202, D289).

MongoDB has no catalog to narrow by a word, so the names are listed — the
databases, then each one's collections by name only — and classed here by the
shared word rule. Listing stops at a ceiling and at the clock, and a search
that stopped says so. Collections are not found by their fields: those are
read from documents (D284), and reading every collection's would be a scan.
"""

from collections.abc import AsyncIterator

from app.adapters.catalog import CatalogNode
from app.adapters.database_ids import database_id, parse
from app.adapters.mongodb.catalog import (
    MongodbCatalog,
    collection_node,
    database_node,
    report_node,
)
from app.adapters.mongodb.reports import (
    REPORTS,
    SECTION_ID,
    SECTION_TITLE,
    in_section,
    is_section,
)
from app.adapters.mongodb.session import MongodbSession
from app.adapters.protocol import NodeNotFound
from app.adapters.search import (
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

OWN_SECONDS = 5.0
# Names looked at for one search or one kept list, at most.
CANDIDATES = 20_000


class MongodbSearch:
    def __init__(self, session: MongodbSession, catalog: MongodbCatalog) -> None:
        self._session = session
        self._catalog = catalog

    async def _names(
        self, database: str | None, bounds: SearchBounds
    ) -> AsyncIterator[tuple[CatalogNode, str | None, str]]:
        """Every database and collection below a level, a node with where it is."""
        names = await self._catalog.database_names()
        if database is not None:
            if database not in names:
                raise NodeNotFound(database_id(database))
            names = [database]
        async with self._session.client() as client:
            for name in names:
                if bounds.over():
                    return
                if database is None:
                    yield database_node(name), None, ""
                with self._session.failures():
                    cursor = await client[name].list_collections()
                    infos = await cursor.to_list()
                for info in infos:
                    yield collection_node(name, info), database_id(name), name

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = words_of(request.query)
        if not words:
            raise ValueError(say("A search needs something to look for"))
        if request.node_id is not None and is_section(request.node_id):
            return _reports(words, request.limit)
        database: str | None = None
        if request.node_id is not None:
            refused = say("A search starts at the top, in a database or among the reports")
            if in_section(request.node_id):
                raise ValueError(refused)
            database, collection = parse(request.node_id)
            if collection is not None:
                raise ValueError(refused)
        clock = bounds or SearchBounds.within(OWN_SECONDS)
        kept: Kept[NodeMatch] = Kept(request.limit)
        looked = 0
        async for node, parent, location in self._names(database, clock):
            looked += 1
            if looked > CANDIDATES:
                break
            match_class = class_of_name(words, node.name)
            if match_class is not None and kept.wants(match_class):
                kept.add(match_class, NodeMatch(node=node, parent_id=parent, location=location))
        stopped = clock.over() or looked > CANDIDATES
        complete = not kept.dropped and not stopped
        return NodeSearchResult(
            matches=kept.items(),
            complete=complete,
            notice=None
            if complete
            else say("The first {limit} matches; there may be more", limit=request.limit),
            extent=looked,
        )

    async def enumerate_names(self, limit: int, bounds: SearchBounds) -> AsyncIterator[NameBatch]:
        """Every database and collection, for a kept list: one scope, the server."""
        batch: list[KeptName] = []
        seen = 0
        async for node, parent, location in self._names(None, bounds):
            if seen == limit:
                yield NameBatch(
                    names=batch,
                    notice=say("More than {limit} names; the first {limit} are kept", limit=f"{limit:,}"),
                )
                return
            seen += 1
            batch.append(KeptName(node=node, parent_id=parent, location=location))
            if len(batch) == 1000:
                yield NameBatch(names=batch)
                batch = []
        notice = say("Time ran out before every name was read") if bounds.over() else None
        yield NameBatch(names=batch, notice=notice)


def _reports(words: tuple[str, ...], limit: int) -> NodeSearchResult:
    """The reports by the title a person reads, in the language of the request."""
    found = [
        (class_rank(match_class), title, report)
        for report in REPORTS
        if (match_class := class_of_name(words, title := say(report.title))) is not None
    ]
    found.sort(key=lambda one: (one[0], one[1]))
    return NodeSearchResult(
        matches=[
            NodeMatch(node=report_node(report), parent_id=SECTION_ID, location=say(SECTION_TITLE))
            for _, _, report in found[:limit]
        ],
        complete=len(found) <= limit,
    )
