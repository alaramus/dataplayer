"""Finding databases and relations by name, and relations by their columns (D202).

One bounded query of `information_schema` per search. Every word is looked
for with INSTR on a bound value, so `%` and `_` are characters and nothing a
person types is compiled (D2c). Names are compared folded and under
utf8mb4_bin: the server's own collations ignore accents and trailing spaces,
which would find names the word rule does not hold, and the catalog's columns
are in another character set, which INSTR would refuse as a mix of
collations. Each word is bound twice, as the rule folds it and as typed for
the server to fold, as PostgreSQL's search does. The best names are ordered
inside the query, before its LIMIT.
"""

import asyncio
from collections.abc import AsyncIterator, Mapping
from typing import Any

from app.adapters.catalog import CatalogNode
from app.adapters.mysql import ids
from app.adapters.mysql.catalog import database_node, relation_node, report_node
from app.adapters.mysql.reports import (
    REPORTS,
    SECTION_ID,
    SECTION_TITLE,
    in_section,
    is_section,
)
from app.adapters.mysql.session import MysqlSession
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.search import (
    MAX_EXCERPT_CHARACTERS,
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
_BATCH = 1000

# What separates the words of a name, as the word rule has them (D202).
_SEPARATORS = ("_", "-", ".", "/", ":", " ")


def _folded(column: str) -> str:
    return f"LOWER(CONVERT({column} USING utf8mb4)) COLLATE utf8mb4_bin"


def _forms(index: int) -> tuple[str, str]:
    """One word as the word rule folds it, and as the server folds what was typed."""
    return (
        f"CONVERT(%(w{index})s USING utf8mb4) COLLATE utf8mb4_bin",
        f"LOWER(CONVERT(%(r{index})s USING utf8mb4)) COLLATE utf8mb4_bin",
    )


def _holds_every_word(folded: str, count: int) -> str:
    return " AND ".join(
        f"(INSTR({folded}, {rule}) > 0 OR INSTR({folded}, {server}) > 0)"
        for rule, server in map(_forms, range(count))
    )


def _begins_every_word(folded: str, count: int) -> str:
    """Every word at the start of the name or right after a separator."""
    return " AND ".join(
        "("
        + " OR ".join(
            [f"INSTR({folded}, {form}) = 1" for form in forms]
            + [
                f"INSTR({folded}, CONCAT('{separator}', {form})) > 0"
                for separator in _SEPARATORS
                for form in forms
            ]
        )
        + ")"
        for forms in map(_forms, range(count))
    )


def _rank(folded: str, count: int) -> str:
    """Exact, prefix, word, substring, as numbers: the classes of the word rule."""
    rule, server = _forms(0)
    typed = "LOWER(CONVERT(%(typed)s USING utf8mb4)) COLLATE utf8mb4_bin"
    return (
        f"CASE WHEN {folded} = CONVERT(%(exact)s USING utf8mb4) COLLATE utf8mb4_bin "
        f"OR {folded} = {typed} THEN 0 "
        f"WHEN INSTR({folded}, {rule}) = 1 OR INSTR({folded}, {server}) = 1 THEN 1 "
        f"WHEN {_begins_every_word(folded, count)} THEN 2 ELSE 3 END"
    )


def _names_statement(count: int) -> str:
    schema = _folded("SCHEMA_NAME")
    table = _folded("TABLE_NAME")
    return f"""
        SELECT * FROM (
            SELECT CONVERT(SCHEMA_NAME USING utf8mb4) AS schema_name, NULL AS name,
                   NULL AS table_type, NULL AS table_rows, NULL AS size_bytes,
                   {_rank(schema, count)} AS `rank`, {schema} AS folded
            FROM information_schema.SCHEMATA
            WHERE %(schema)s IS NULL AND {_holds_every_word(schema, count)}
            UNION ALL
            SELECT CONVERT(TABLE_SCHEMA USING utf8mb4), CONVERT(TABLE_NAME USING utf8mb4),
                   TABLE_TYPE, TABLE_ROWS, DATA_LENGTH + INDEX_LENGTH,
                   {_rank(table, count)}, {table}
            FROM information_schema.TABLES
            WHERE (%(schema)s IS NULL OR TABLE_SCHEMA = %(schema)s)
              AND {_holds_every_word(table, count)}
        ) AS found
        ORDER BY `rank`, folded, schema_name, name
        LIMIT %(limit)s
    """  # noqa: S608  # every fragment above is written in this module; words and names are bound


def _columns_statement(count: int) -> str:
    """Relations by a column's name, a column's comment or their own comment.

    One row per relation, carrying the best of what it was found by: a
    column's name by its class, then a column's comment, then its own.
    """
    column = _folded("c.COLUMN_NAME")
    column_comment = _folded("c.COLUMN_COMMENT")
    table_comment = _folded("t.TABLE_COMMENT")
    relation = """CONVERT(t.TABLE_SCHEMA USING utf8mb4) AS schema_name,
                  CONVERT(t.TABLE_NAME USING utf8mb4) AS name,
                  t.TABLE_TYPE AS table_type, t.TABLE_ROWS AS table_rows,
                  t.DATA_LENGTH + t.INDEX_LENGTH AS size_bytes"""
    joined = """information_schema.COLUMNS c
                JOIN information_schema.TABLES t
                  ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME"""
    within = "(%(schema)s IS NULL OR t.TABLE_SCHEMA = %(schema)s)"
    return f"""
        SELECT schema_name, name, table_type, table_rows, size_bytes, evidence FROM (
            SELECT best.*, ROW_NUMBER() OVER (
                       PARTITION BY best.schema_name, best.name
                       ORDER BY best.`rank`, best.evidence
                   ) AS place
            FROM (
                SELECT {relation}, CONVERT(c.COLUMN_NAME USING utf8mb4) AS evidence,
                       {_rank(column, count)} AS `rank`
                FROM {joined}
                WHERE {within} AND {_holds_every_word(column, count)}
                UNION ALL
                SELECT {relation},
                       CONCAT(CONVERT(c.COLUMN_NAME USING utf8mb4), ': ',
                              LEFT(CONVERT(c.COLUMN_COMMENT USING utf8mb4), %(cut)s)), 4
                FROM {joined}
                WHERE {within} AND {_holds_every_word(column_comment, count)}
                UNION ALL
                SELECT {relation}, LEFT(CONVERT(t.TABLE_COMMENT USING utf8mb4), %(cut)s), 5
                FROM information_schema.TABLES t
                WHERE {within} AND t.TABLE_TYPE <> 'VIEW'
                  AND {_holds_every_word(table_comment, count)}
            ) AS best
        ) AS ranked
        WHERE place = 1
        ORDER BY `rank`, name, schema_name
        LIMIT %(limit)s
    """  # noqa: S608  # every fragment above is written in this module; words and names are bound


_ALL_NAMES = """
    SELECT * FROM (
        SELECT CONVERT(SCHEMA_NAME USING utf8mb4) AS schema_name, NULL AS name,
               NULL AS table_type, NULL AS table_rows, NULL AS size_bytes
        FROM information_schema.SCHEMATA
        UNION ALL
        SELECT CONVERT(TABLE_SCHEMA USING utf8mb4), CONVERT(TABLE_NAME USING utf8mb4),
               TABLE_TYPE, TABLE_ROWS, NULL
        FROM information_schema.TABLES
    ) AS every_name
    ORDER BY schema_name, name
    LIMIT %s
"""

_TABLES_OF = """
    SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS name
    FROM information_schema.TABLES
    WHERE TABLE_TYPE = 'BASE TABLE'
"""


class MysqlSearch:
    def __init__(self, session: MysqlSession) -> None:
        self._session = session

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = _words_of(request)
        if request.node_id is not None and is_section(request.node_id):
            return _reports(words, request.limit)
        schema = _database(request.node_id)
        rows = await self._bounded(
            _names_statement(len(words)), _parameters(request, words, schema), bounds
        )
        return await self._result(rows, request.limit, schema, evidence=False)

    async def search_columns(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = _words_of(request)
        if request.node_id is not None and in_section(request.node_id):
            # A report is a statement: it has no comments, and no columns of its own.
            return NodeSearchResult()
        schema = _database(request.node_id)
        parameters = {**_parameters(request, words, schema), "cut": MAX_EXCERPT_CHARACTERS * 5}
        rows = await self._bounded(_columns_statement(len(words)), parameters, bounds)
        return await self._result(rows, request.limit, schema, evidence=True)

    async def enumerate_names(self, limit: int, bounds: SearchBounds) -> AsyncIterator[NameBatch]:
        """Every database and relation, for a kept list: one scope, the server.

        The reports are written here rather than read, and are found live.
        """
        rows = await self._bounded(_ALL_NAMES, (limit + 1,), bounds)
        if rows is None:
            yield NameBatch(notice=say("Time ran out before the server was asked"))
            return
        notice = (
            say("More than {limit} names; the first {limit} are kept", limit=f"{limit:,}")
            if len(rows) > limit
            else None
        )
        rows = rows[:limit]
        tables = await self._tables()
        for start in range(0, len(rows), _BATCH):
            names = []
            for row in rows[start : start + _BATCH]:
                match = _match(row, tables, evidence=False)
                names.append(
                    KeptName(node=match.node, parent_id=match.parent_id, location=match.location)
                )
            yield NameBatch(names=names)
        if notice is not None:
            yield NameBatch(notice=notice)

    async def _bounded(
        self,
        statement: str,
        params: tuple[object, ...] | Mapping[str, object],
        bounds: SearchBounds | None,
    ) -> list[dict[str, Any]] | None:
        """The rows, or None when there was no time left to ask.

        A cancelled read closes its connection rather than returning it to the
        pool with half an answer in it.
        """
        seconds = OWN_SECONDS if bounds is None else bounds.left()
        if seconds <= 0 or (bounds is not None and bounds.stopped()):
            return None
        try:
            async with asyncio.timeout(seconds):
                return await self._session.query(statement, params)
        except TimeoutError:
            raise AdapterError("timeout", say("The server did not answer in time")) from None

    async def _tables(self) -> dict[str, list[str]]:
        tables: dict[str, list[str]] = {}
        for row in await self._session.query(_TABLES_OF):
            tables.setdefault(str(row["schema_name"]), []).append(str(row["name"]))
        return tables

    async def _result(
        self, rows: list[dict[str, Any]] | None, limit: int, schema: str | None, *, evidence: bool
    ) -> NodeSearchResult:
        if rows is None:
            return NodeSearchResult(
                complete=False, notice=say("Time ran out before the server was asked")
            )
        if not rows and schema is not None:
            found = await self._session.query(
                "SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s", (schema,)
            )
            if not found:
                raise NodeNotFound(ids.database_id(schema))
        complete = len(rows) <= limit
        rows = rows[:limit]
        tables = await self._tables() if any(row["name"] is None for row in rows) else {}
        return NodeSearchResult(
            matches=[_match(row, tables, evidence=evidence) for row in rows],
            complete=complete,
            notice=None
            if complete
            else say("The first {limit} matches; there may be more", limit=limit),
        )


def _words_of(request: NodeSearchRequest) -> tuple[str, ...]:
    words = words_of(request.query)
    if not words:
        raise ValueError(say("A search needs something to look for"))
    return words


def _parameters(
    request: NodeSearchRequest, words: tuple[str, ...], schema: str | None
) -> dict[str, object]:
    """Each word as the rule folds it and as it was first typed; one row more
    than the limit, which says whether there were more."""
    typed = tuple(
        next(one for one in request.query.split() if one.casefold() == word) for word in words
    )
    return {
        **{f"w{index}": word for index, word in enumerate(words)},
        **{f"r{index}": word for index, word in enumerate(typed)},
        "exact": " ".join(words),
        "typed": " ".join(typed),
        "schema": schema,
        "limit": request.limit + 1,
    }


def _database(node_id: str | None) -> str | None:
    """The database a search starts in, or None for the top; a refusal for a leaf."""
    if node_id is None:
        return None
    refused = say("A search starts at the top, in a database or among the reports")
    if in_section(node_id):
        raise ValueError(refused)
    schema, relation = ids.parse(node_id)
    if relation is not None:
        raise ValueError(refused)
    return schema


def _match(row: Mapping[str, Any], tables: Mapping[str, list[str]], *, evidence: bool) -> NodeMatch:
    schema = str(row["schema_name"])
    if row["name"] is None:
        node: CatalogNode = database_node(schema, tables.get(schema, []))
        return NodeMatch(node=node, parent_id=None, location="")
    found = row.get("evidence") if evidence else None
    return NodeMatch(
        node=relation_node(schema, row),
        parent_id=ids.database_id(schema),
        location=schema,
        excerpt=None if found is None else str(found),
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
