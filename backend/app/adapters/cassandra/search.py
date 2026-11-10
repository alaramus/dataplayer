"""Finding keyspaces and relations by name, and relations by their columns (D202, D350).

CQL finds no part of a text without an index, and `system_schema` is small, so
the names are read whole — under a ceiling — and the shared word rule
(`class_of_name`) classes and keeps the best here, as SQLite's search does.
Nothing typed reaches a statement.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.adapters.cassandra.catalog import keyspace_node, relation_node, report_node
from app.adapters.cassandra.inspection import (
    Inspector,
    RelationFacts,
    is_system_keyspace,
)
from app.adapters.cassandra.reports import (
    REPORTS,
    SECTION_ID,
    SECTION_TITLE,
    in_section,
    is_section,
)
from app.adapters.cassandra.session import CassandraSession
from app.adapters.catalog import CatalogNode
from app.adapters.database_ids import database_id, parse
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.search import (
    MAX_EXCERPT_CHARACTERS,
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

# What a search is given when its caller gives it no clock.
OWN_SECONDS = 5.0
# Names read for one search, at most.
CANDIDATES = 50_000
_BATCH = 1000

_TABLES = "SELECT keyspace_name, table_name, comment FROM system_schema.tables"
_VIEWS = (
    "SELECT keyspace_name, view_name, base_table_name, comment FROM system_schema.views"
)
_COLUMNS = "SELECT keyspace_name, table_name, column_name FROM system_schema.columns"


def _words(request: NodeSearchRequest) -> tuple[str, ...]:
    words = words_of(request.query)
    if not words:
        raise ValueError(say("A search needs something to look for"))
    return words


def _keyspace(node_id: str | None) -> str | None:
    """The keyspace a search starts in, or None for the top; a refusal for a leaf."""
    if node_id is None:
        return None
    refused = say("A search starts at the top, in a keyspace or among the reports")
    if in_section(node_id):
        raise ValueError(refused)
    keyspace, relation = parse(node_id)
    if relation is not None:
        raise ValueError(refused)
    return keyspace


class CassandraSearch:
    def __init__(self, session: CassandraSession, inspector: Inspector) -> None:
        self._session = session
        self._inspector = inspector

    async def _bounded[T](
        self, read: Callable[[], Awaitable[T]], bounds: SearchBounds | None
    ) -> T | None:
        """What `read` answers, or None when there was no time left to ask."""
        seconds = OWN_SECONDS if bounds is None else bounds.left()
        if seconds <= 0 or (bounds is not None and bounds.stopped()):
            return None
        try:
            async with asyncio.timeout(seconds):
                return await read()
        except TimeoutError:
            raise AdapterError(
                "timeout", say("The server did not answer in time")
            ) from None

    async def _relations(
        self,
    ) -> tuple[list[tuple[str, bool]], list[RelationFacts], bool]:
        """Every keyspace and every table and view, without columns."""
        keyspaces = await self._inspector.keyspaces()
        scylla = await self._inspector.scylla()
        behind = {
            (str(row["keyspace_name"]), f"{row['index_name']}_index")
            for row in await self._session.query(
                "SELECT keyspace_name, index_name FROM system_schema.indexes"
            )
        }
        tables = (await self._session.rows(_TABLES, limit=CANDIDATES + 1)).dicts()
        views = (await self._session.rows(_VIEWS, limit=CANDIDATES + 1)).dicts()
        found = [
            RelationFacts(
                keyspace=str(row["keyspace_name"]),
                name=str(row["table_name"]),
                is_system=is_system_keyspace(str(row["keyspace_name"]), scylla=scylla),
                comment=str(row["comment"]) if row.get("comment") else None,
            )
            for row in tables
        ]
        found += [
            RelationFacts(
                keyspace=str(row["keyspace_name"]),
                name=str(row["view_name"]),
                is_system=is_system_keyspace(str(row["keyspace_name"]), scylla=scylla),
                is_view=True,
                base_table=str(row["base_table_name"]),
                comment=str(row["comment"]) if row.get("comment") else None,
            )
            for row in views
            if (str(row["keyspace_name"]), str(row["view_name"])) not in behind
        ]
        cut = len(tables) > CANDIDATES or len(views) > CANDIDATES
        return keyspaces, found, cut

    async def _checked(self, keyspace: str | None) -> None:
        if keyspace is not None and await self._inspector.keyspace(keyspace) is None:
            raise NodeNotFound(database_id(keyspace))

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = _words(request)
        if request.node_id is not None and is_section(request.node_id):
            return _reports(words, request.limit)
        keyspace = _keyspace(request.node_id)
        read = await self._bounded(self._relations, bounds)
        if read is None:
            return _out_of_time()
        await self._checked(keyspace)
        keyspaces, relations, cut = read
        scylla = await self._inspector.scylla()
        kept: Kept[NodeMatch] = Kept(request.limit)
        if keyspace is None:
            for name, _ in keyspaces:
                match_class = class_of_name(words, name)
                if match_class is not None and kept.wants(match_class):
                    node = keyspace_node(
                        name, [], system=is_system_keyspace(name, scylla=scylla)
                    )
                    kept.add(match_class, NodeMatch(node=node))
        for facts in relations:
            if keyspace is not None and facts.keyspace != keyspace:
                continue
            match_class = class_of_name(words, facts.name)
            if match_class is not None and kept.wants(match_class):
                kept.add(
                    match_class,
                    NodeMatch(
                        node=relation_node(facts),
                        parent_id=database_id(facts.keyspace),
                        location=facts.keyspace,
                    ),
                )
        complete = not kept.dropped and not cut
        return NodeSearchResult(
            matches=kept.items(),
            complete=complete,
            notice=None
            if complete
            else say(
                "The first {limit} matches; there may be more", limit=request.limit
            ),
        )

    async def search_columns(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = _words(request)
        if request.node_id is not None and in_section(request.node_id):
            # A report is a statement: it has no columns of its own.
            return NodeSearchResult()
        keyspace = _keyspace(request.node_id)

        async def read() -> tuple[list[RelationFacts], list[dict[str, Any]], bool]:
            _, relations, cut = await self._relations()
            columns = (await self._session.rows(_COLUMNS, limit=CANDIDATES + 1)).dicts()
            return relations, columns, cut or len(columns) > CANDIDATES

        answer = await self._bounded(read, bounds)
        if answer is None:
            return _out_of_time()
        await self._checked(keyspace)
        relations, columns, cut = answer
        places = {(facts.keyspace, facts.name): facts for facts in relations}
        # The best of what a relation was found by stands for it: a column's
        # name by its class, then its own comment.
        best: dict[tuple[str, str], tuple[int, str]] = {}
        for row in columns[:CANDIDATES]:
            place = (str(row["keyspace_name"]), str(row["table_name"]))
            column = str(row["column_name"])
            if place not in places or (keyspace is not None and place[0] != keyspace):
                continue
            found = class_of_name(words, column)
            if found is not None and (
                place not in best or class_rank(found) < best[place][0]
            ):
                best[place] = (class_rank(found), column[:MAX_EXCERPT_CHARACTERS])
        for place, facts in places.items():
            if keyspace is not None and place[0] != keyspace:
                continue
            comment = facts.comment or ""
            folded = comment.casefold()
            if (
                comment
                and all(word.casefold() in folded for word in words)
                and place not in best
            ):
                best[place] = (5, comment[:MAX_EXCERPT_CHARACTERS])
        ordered = sorted(
            best.items(), key=lambda item: (item[1][0], item[0][1], item[0][0])
        )
        matches = [
            NodeMatch(
                node=relation_node(places[place]),
                parent_id=database_id(place[0]),
                location=place[0],
                excerpt=evidence,
            )
            for place, (_, evidence) in ordered[: request.limit]
        ]
        complete = len(ordered) <= request.limit and not cut
        return NodeSearchResult(
            matches=matches,
            complete=complete,
            notice=None
            if complete
            else say(
                "The first {limit} matches; there may be more", limit=request.limit
            ),
        )

    async def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        """Every keyspace and relation, for a kept list: one scope, the cluster.

        The reports are written here rather than read, and are found live.
        """
        read = await self._bounded(self._relations, bounds)
        if read is None:
            yield NameBatch(notice=say("Time ran out before the server was asked"))
            return
        keyspaces, relations, _ = read
        scylla = await self._inspector.scylla()
        names: list[KeptName] = [
            KeptName(
                node=keyspace_node(
                    name, [], system=is_system_keyspace(name, scylla=scylla)
                )
            )
            for name, _ in sorted(keyspaces)
        ]
        names += [
            KeptName(
                node=relation_node(facts),
                parent_id=database_id(facts.keyspace),
                location=facts.keyspace,
            )
            for facts in sorted(
                relations, key=lambda facts: (facts.keyspace, facts.name)
            )
        ]
        notice = (
            say(
                "More than {limit} names; the first {limit} are kept",
                limit=f"{limit:,}",
            )
            if len(names) > limit
            else None
        )
        names = names[:limit]
        for start in range(0, len(names), _BATCH):
            yield NameBatch(names=names[start : start + _BATCH])
        if notice is not None:
            yield NameBatch(notice=notice)


def _out_of_time() -> NodeSearchResult:
    return NodeSearchResult(
        complete=False, notice=say("Time ran out before the server was asked")
    )


def _reports(words: tuple[str, ...], limit: int) -> NodeSearchResult:
    """The reports by the title a person reads, in the language of the request."""
    found = [
        (class_rank(match_class), title, report)
        for report in REPORTS
        if (match_class := class_of_name(words, title := say(report.title))) is not None
    ]
    found.sort(key=lambda one: (one[0], one[1]))
    nodes: list[CatalogNode] = [report_node(report) for _, _, report in found[:limit]]
    return NodeSearchResult(
        matches=[
            NodeMatch(node=node, parent_id=SECTION_ID, location=say(SECTION_TITLE))
            for node in nodes
        ],
        complete=len(found) <= limit,
    )
