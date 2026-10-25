"""Finding databases and relations by name, and relations by their columns (D202, D275).

The server narrows: a name, a column's name or a comment is a candidate when
it holds every word, by `positionCaseInsensitiveUTF8` on a bound value, so `%`
and `_` are characters and nothing typed is compiled (D2c). The shared word
rule (`class_of_name`) then classes and keeps the best here, as SQLite's
search does. The candidates are bounded; a search that reaches the bound says
it may have missed some.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from app.adapters.catalog import CatalogNode
from app.adapters.clickhouse.catalog import (
    database_node,
    is_inner_table,
    relation_node,
    report_node,
)
from app.adapters.clickhouse.reports import (
    REPORTS,
    SECTION_ID,
    SECTION_TITLE,
    in_section,
    is_section,
)
from app.adapters.clickhouse.session import ClickhouseSession
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
# Candidates the server hands over for one search, at most.
CANDIDATES = 5000
_BATCH = 1000


def _holds(column: str, count: int) -> str:
    """Every word somewhere in the column, by the server's own case folding."""
    return " AND ".join(
        f"positionCaseInsensitiveUTF8({column}, {{w{index}:String}}) > 0" for index in range(count)
    )


def _names_statement(count: int) -> str:
    # A LIMIT after UNION ALL would bind to its last SELECT alone, and an
    # alias is the query's, not its SELECT's: `'' AS name` beside `name` would
    # replace the column itself, so the answer's names are none of the sources'.
    return f"""
        SELECT * FROM (
            SELECT name AS db, '' AS relation, '' AS engine, NULL AS total_rows,
                   NULL AS total_bytes
            FROM system.databases
            WHERE {{scoped:UInt8}} = 0 AND {_holds("name", count)}
            UNION ALL
            SELECT database AS db, name AS relation, engine, total_rows, total_bytes
            FROM system.tables
            WHERE NOT is_temporary
              AND ({{scoped:UInt8}} = 0 OR database = {{database:String}})
              AND {_holds("name", count)}
        )
        LIMIT {{limit:UInt32}}
    """  # noqa: S608  # every fragment above is written in this module; words and names are bound


def _columns_statement(count: int) -> str:
    """Relations by a column's name, a column's comment or their own comment."""
    return f"""
        SELECT * FROM (
        SELECT c.database AS db, c.table AS relation, t.engine AS engine,
               t.total_rows AS total_rows, t.total_bytes AS total_bytes,
               c.name AS column_name, c.comment AS remark, 'column' AS kind
        FROM system.columns AS c
        INNER JOIN system.tables AS t ON t.database = c.database AND t.name = c.table
        WHERE ({{scoped:UInt8}} = 0 OR c.database = {{database:String}})
          AND (({_holds("c.name", count)}) OR ({_holds("c.comment", count)}))
        UNION ALL
        SELECT database, name, engine, total_rows, total_bytes, '', comment, 'table'
        FROM system.tables
        WHERE NOT is_temporary
          AND ({{scoped:UInt8}} = 0 OR database = {{database:String}})
          AND {_holds("comment", count)}
        )
        LIMIT {{limit:UInt32}}
    """  # noqa: S608  # every fragment above is written in this module; words and names are bound


_ALL_NAMES = """
    SELECT * FROM (
        SELECT name AS db, '' AS relation, '' AS engine, NULL AS total_rows,
               NULL AS total_bytes
        FROM system.databases
        UNION ALL
        SELECT database AS db, name AS relation, engine, total_rows, total_bytes
        FROM system.tables
        WHERE NOT is_temporary
    )
    ORDER BY db, relation
    LIMIT {limit:UInt32}
"""

_DATABASE = "SELECT 1 FROM system.databases WHERE name = {database:String}"


def _words(request: NodeSearchRequest) -> tuple[str, ...]:
    words = words_of(request.query)
    if not words:
        raise ValueError(say("A search needs something to look for"))
    return words


def _database(node_id: str | None) -> str | None:
    """The database a search starts in, or None for the top; a refusal for a leaf."""
    if node_id is None:
        return None
    refused = say("A search starts at the top, in a database or among the reports")
    if in_section(node_id):
        raise ValueError(refused)
    schema, relation = parse(node_id)
    if relation is not None:
        raise ValueError(refused)
    return schema


def _params(words: tuple[str, ...], schema: str | None, limit: int) -> dict[str, str]:
    return {
        **{f"w{index}": word for index, word in enumerate(words)},
        "scoped": "0" if schema is None else "1",
        "database": schema or "",
        "limit": str(limit),
    }


def _node(row: dict[str, Any]) -> tuple[CatalogNode, str | None, str]:
    """A row as its node, its parent's id and where it sits."""
    schema = str(row["db"])
    if not row["relation"]:
        return database_node(schema, []), None, ""
    return relation_node(schema, {**row, "name": row["relation"]}), database_id(schema), schema


class ClickhouseSearch:
    def __init__(self, session: ClickhouseSession) -> None:
        self._session = session

    async def _bounded(
        self, statement: str, params: dict[str, str], bounds: SearchBounds | None
    ) -> list[dict[str, Any]] | None:
        """The rows, or None when there was no time left to ask."""
        seconds = OWN_SECONDS if bounds is None else bounds.left()
        if seconds <= 0 or (bounds is not None and bounds.stopped()):
            return None
        try:
            async with asyncio.timeout(seconds):
                return await self._session.query(statement, params)
        except TimeoutError:
            raise AdapterError("timeout", say("The server did not answer in time")) from None

    async def _checked(self, schema: str | None) -> None:
        if schema is not None and not await self._session.query(_DATABASE, {"database": schema}):
            raise NodeNotFound(database_id(schema))

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = _words(request)
        if request.node_id is not None and is_section(request.node_id):
            return _reports(words, request.limit)
        schema = _database(request.node_id)
        rows = await self._bounded(
            _names_statement(len(words)), _params(words, schema, CANDIDATES + 1), bounds
        )
        if rows is None:
            return _out_of_time()
        await self._checked(schema)
        kept: Kept[NodeMatch] = Kept(request.limit)
        for row in rows[:CANDIDATES]:
            name = str(row["relation"] or row["db"])
            if row["relation"] and is_inner_table(name):
                continue
            match_class = class_of_name(words, name)
            if match_class is not None and kept.wants(match_class):
                node, parent, location = _node(row)
                kept.add(match_class, NodeMatch(node=node, parent_id=parent, location=location))
        return _result(kept, request.limit, cut=len(rows) > CANDIDATES)

    async def search_columns(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = _words(request)
        if request.node_id is not None and in_section(request.node_id):
            # A report is a statement: it has no columns of its own.
            return NodeSearchResult()
        schema = _database(request.node_id)
        rows = await self._bounded(
            _columns_statement(len(words)), _params(words, schema, CANDIDATES + 1), bounds
        )
        if rows is None:
            return _out_of_time()
        await self._checked(schema)
        # The best of what a relation was found by stands for it: a column's
        # name by its class, then a column's comment, then its own comment.
        best: dict[tuple[str, str], tuple[int, str, dict[str, Any]]] = {}
        for row in rows[:CANDIDATES]:
            if is_inner_table(str(row["relation"])):
                continue
            column = str(row["column_name"])
            if row["kind"] == "column" and (found := class_of_name(words, column)) is not None:
                rank, evidence = class_rank(found), column
            elif row["kind"] == "column":
                rank, evidence = 4, f"{column}: {row['remark']}"
            else:
                rank, evidence = 5, str(row["remark"])
            place = (str(row["db"]), str(row["relation"]))
            if place not in best or rank < best[place][0]:
                best[place] = (rank, evidence[:MAX_EXCERPT_CHARACTERS], row)
        ordered = sorted(best.values(), key=lambda one: (one[0], str(one[2]["relation"]), str(one[2]["db"])))
        matches = []
        for _, evidence, row in ordered[: request.limit]:
            node, parent, location = _node(row)
            matches.append(NodeMatch(node=node, parent_id=parent, location=location, excerpt=evidence))
        complete = len(ordered) <= request.limit and len(rows) <= CANDIDATES
        return NodeSearchResult(
            matches=matches,
            complete=complete,
            notice=None
            if complete
            else say("The first {limit} matches; there may be more", limit=request.limit),
        )

    async def enumerate_names(self, limit: int, bounds: SearchBounds) -> AsyncIterator[NameBatch]:
        """Every database and relation, for a kept list: one scope, the server.

        The reports are written here rather than read, and are found live.
        """
        rows = await self._bounded(_ALL_NAMES, {"limit": str(limit + 1)}, bounds)
        if rows is None:
            yield NameBatch(notice=say("Time ran out before the server was asked"))
            return
        notice = (
            say("More than {limit} names; the first {limit} are kept", limit=f"{limit:,}")
            if len(rows) > limit
            else None
        )
        kept = [
            row for row in rows[:limit] if not (row["relation"] and is_inner_table(str(row["relation"])))
        ]
        for start in range(0, len(kept), _BATCH):
            names = []
            for row in kept[start : start + _BATCH]:
                node, parent, location = _node(row)
                names.append(KeptName(node=node, parent_id=parent, location=location))
            yield NameBatch(names=names)
        if notice is not None:
            yield NameBatch(notice=notice)


def _out_of_time() -> NodeSearchResult:
    return NodeSearchResult(complete=False, notice=say("Time ran out before the server was asked"))


def _result(kept: Kept[NodeMatch], limit: int, *, cut: bool) -> NodeSearchResult:
    complete = not kept.dropped and not cut
    return NodeSearchResult(
        matches=kept.items(),
        complete=complete,
        notice=None if complete else say("The first {limit} matches; there may be more", limit=limit),
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
