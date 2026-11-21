"""Finding schemas and relations by name, and relations by their columns (D202, D398).

A file's catalog is read whole in one inspection — every relation, and for a
column search every column of each — and matched here by the shared word rule
(`class_of_name`), since it is on this server's disk and small next to a
server's. Nothing typed reaches a statement.
"""

from collections.abc import AsyncIterator
from typing import Any

from app.adapters import database_ids as ids
from app.adapters.catalog import CatalogNode
from app.adapters.duckdb.catalog import relation_node, report_node, schema_node
from app.adapters.duckdb.inspection import list_relations, list_schemas
from app.adapters.duckdb.reports import (
    REPORTS,
    SECTION_ID,
    SECTION_TITLE,
    in_section,
    is_section,
)
from app.adapters.duckdb.session import DuckdbSession, Reading
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

_COLUMNS = """
SELECT schema_name, table_name, column_name FROM duckdb_columns()
WHERE database_name = current_database() AND NOT internal
ORDER BY schema_name, table_name, column_index
"""

type Catalog = tuple[list[str], list[dict[str, Any]]]


def _words(request: NodeSearchRequest) -> tuple[str, ...]:
    words = words_of(request.query)
    if not words:
        raise ValueError(say("A search needs something to look for"))
    return words


def _scope(node_id: str | None, schemas: list[str]) -> str | None:
    """The schema a search is held to, or none for the whole file."""
    if node_id is None:
        return None
    schema, relation = ids.parse(node_id)
    if relation is None and schema in schemas:
        return schema
    raise ValueError(say("A search starts at the top, in a schema or among the reports"))


def _catalog(reading: Reading) -> Catalog:
    return list_schemas(reading), list_relations(reading)


def _tables_of(relations: list[dict[str, Any]], schema: str) -> list[str]:
    return [
        str(row["name"])
        for row in relations
        if row["type"] == "table" and str(row["schema_name"]) == schema
    ]


def _found(node: CatalogNode, schema: str, *, excerpt: str | None = None) -> NodeMatch:
    return NodeMatch(node=node, parent_id=ids.database_id(schema), location=schema, excerpt=excerpt)


class DuckdbSearch:
    def __init__(self, session: DuckdbSession) -> None:
        self._session = session

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = _words(request)
        if request.node_id is not None and is_section(request.node_id):
            return _reports(words, request.limit)
        schemas, relations = await self._session.inspection(_catalog)
        held = _scope(request.node_id, schemas)
        kept: Kept[NodeMatch] = Kept(request.limit)
        if held is None:
            for schema in schemas:
                if (found := class_of_name(words, schema)) is not None and kept.wants(found):
                    node = schema_node(schema, _tables_of(relations, schema))
                    kept.add(found, NodeMatch(node=node, parent_id=None, location=""))
        for row in relations:
            schema = str(row["schema_name"])
            if held is not None and schema != held:
                continue
            match_class = class_of_name(words, str(row["name"]))
            if match_class is not None and kept.wants(match_class):
                kept.add(match_class, _found(relation_node(row), schema))
        return _result(kept, request.limit)

    async def search_columns(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = _words(request)
        if request.node_id is not None and (
            is_section(request.node_id) or in_section(request.node_id)
        ):
            # A report is a statement: it has no columns of its own.
            return NodeSearchResult()

        def read(reading: Reading) -> tuple[Catalog, list[tuple[Any, ...]]]:
            return _catalog(reading), reading.tuples(_COLUMNS)

        (schemas, relations), columns = await self._session.inspection(read)
        held = _scope(request.node_id, schemas)
        by_relation: dict[tuple[str, str], list[str]] = {}
        for schema, table, column in columns:
            by_relation.setdefault((str(schema), str(table)), []).append(str(column))
        kept: Kept[NodeMatch] = Kept(request.limit)
        for row in relations:
            schema = str(row["schema_name"])
            if held is not None and schema != held:
                continue
            # The best match among a relation's columns stands for the relation.
            matched = [
                (found, column)
                for column in by_relation.get((schema, str(row["name"])), [])
                if (found := class_of_name(words, column)) is not None
            ]
            if not matched:
                continue
            match_class, column = min(matched, key=lambda one: class_rank(one[0]))
            if kept.wants(match_class):
                kept.add(
                    match_class,
                    _found(relation_node(row), schema, excerpt=column[:MAX_EXCERPT_CHARACTERS]),
                )
        return _result(kept, request.limit)

    async def enumerate_names(self, limit: int, bounds: SearchBounds) -> AsyncIterator[NameBatch]:
        """Every schema and relation, for a kept list: one scope, the file.

        The reports are written here rather than read, and are found live.
        """
        schemas, relations = await self._session.inspection(_catalog)
        names = [
            KeptName(node=schema_node(schema, _tables_of(relations, schema)), parent_id=None, location="")
            for schema in schemas
        ]
        names += [
            KeptName(
                node=relation_node(row),
                parent_id=ids.database_id(str(row["schema_name"])),
                location=str(row["schema_name"]),
            )
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
