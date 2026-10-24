"""Finding relations by name, and by their columns (D202, D257).

A file's catalog is read whole in one inspection — every relation, and for a
column search every column of each — and matched here by the shared word rule
(`class_of_name`), since it is on this server's disk and small next to a
server's. Nothing typed reaches a statement.
"""

from collections.abc import AsyncIterator
from typing import Any

from app.adapters.catalog import CatalogNode
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
from app.adapters.sqlite.catalog import relation_node, report_node, schema_node
from app.adapters.sqlite.inspection import SCHEMA, list_relations
from app.adapters.sqlite.reports import (
    REPORTS,
    SECTION_ID,
    SECTION_TITLE,
    in_section,
    is_section,
)
from app.adapters.sqlite.session import Reading, SqliteSession
from app.core.translation import say

_COLUMNS = "SELECT name FROM pragma_table_xinfo(?, 'main') WHERE hidden <> 1 ORDER BY cid"


def _words(request: NodeSearchRequest) -> tuple[str, ...]:
    words = words_of(request.query)
    if not words:
        raise ValueError(say("A search needs something to look for"))
    return words


def _scope(node_id: str | None) -> None:
    """A search starts at the top or in `main`; a refusal for a leaf."""
    if node_id is None or node_id == SCHEMA:
        return
    raise ValueError(say("A search starts at the top, in main or among the reports"))


def _found(node: CatalogNode, *, excerpt: str | None = None) -> NodeMatch:
    return NodeMatch(node=node, parent_id=SCHEMA, location=SCHEMA, excerpt=excerpt)


class SqliteSearch:
    def __init__(self, session: SqliteSession) -> None:
        self._session = session

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = _words(request)
        if request.node_id is not None and is_section(request.node_id):
            return _reports(words, request.limit)
        _scope(request.node_id)
        relations = await self._session.inspection(list_relations)
        kept: Kept[NodeMatch] = Kept(request.limit)
        if request.node_id is None and (found := class_of_name(words, SCHEMA)) is not None:
            kept.add(found, NodeMatch(node=schema_node(relations), parent_id=None, location=""))
        for row in relations:
            match_class = class_of_name(words, str(row["name"]))
            if match_class is not None and kept.wants(match_class):
                kept.add(match_class, _found(relation_node(row)))
        return _result(kept, request.limit)

    async def search_columns(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = _words(request)
        if request.node_id is not None and (is_section(request.node_id) or in_section(request.node_id)):
            # A report is a statement: it has no columns of its own.
            return NodeSearchResult()
        _scope(request.node_id)

        def read(reading: Reading) -> list[tuple[dict[str, Any], list[str]]]:
            return [
                (row, [str(column[0]) for column in reading.tuples(_COLUMNS, (row["name"],))])
                for row in list_relations(reading)
                if row["type"] != "virtual"
            ]

        kept: Kept[NodeMatch] = Kept(request.limit)
        for row, columns in await self._session.inspection(read):
            # The best match among a relation's columns stands for the relation.
            matched = [
                (found, column)
                for column in columns
                if (found := class_of_name(words, column)) is not None
            ]
            if not matched:
                continue
            match_class, column = min(matched, key=lambda one: class_rank(one[0]))
            if kept.wants(match_class):
                kept.add(match_class, _found(relation_node(row), excerpt=column[:MAX_EXCERPT_CHARACTERS]))
        return _result(kept, request.limit)

    async def enumerate_names(self, limit: int, bounds: SearchBounds) -> AsyncIterator[NameBatch]:
        """`main` and every relation, for a kept list: one scope, the file.

        The reports are written here rather than read, and are found live.
        """
        relations = await self._session.inspection(list_relations)
        names = [KeptName(node=schema_node(relations), parent_id=None, location="")]
        names += [
            KeptName(node=relation_node(row), parent_id=SCHEMA, location=SCHEMA)
            for row in relations
        ]
        yield NameBatch(
            names=names[:limit],
            notice=(
                say("More than {limit} names; the first {limit} are kept", limit=f"{limit:,}")
                if len(names) > limit
                else None
            ),
        )


def _result(kept: Kept[NodeMatch], limit: int) -> NodeSearchResult:
    return NodeSearchResult(
        matches=kept.items(),
        complete=not kept.dropped,
        notice=None
        if not kept.dropped
        else say("The first {limit} matches; there may be more", limit=limit),
    )


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
