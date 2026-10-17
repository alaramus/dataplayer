"""Finding schemas and relations by name, and relations by their columns (D202).

One bounded query of the catalog per search. Every word is looked for with
`strpos` on a bound value, so `%` and `_` are characters and nothing a person
types is compiled (D2c); names are ordered by their class inside the query,
before its `LIMIT`, so the best names are never the ones cut. The nodes
are built by the listing's own builders, with one relation context per schema,
so a found table is the row its schema would have listed.

The server is given the time the answer has left as its statement timeout,
and a search whose answer nobody waits for is cancelled on the server (D200).

A name is folded by the server, under the database's own collation: a `name`
column's is C, whose `lower()` folds only ASCII letters. Each word is bound
twice, as the word rule folds it and as typed for the server to fold the same
way as the names, and either one found is enough; the engine classes every hit
again by the rule itself.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any

from psycopg import sql

from app.adapters.catalog import CatalogNode
from app.adapters.postgres.catalog import relation_of, report_node, schema_of
from app.adapters.postgres.relation_context import (
    PostgresRelationContext,
    SchemaRelationContext,
)
from app.adapters.postgres.report_registry import require_timescale
from app.adapters.postgres.session import LockNotGranted, PostgresSession
from app.adapters.postgres.system_reports import (
    REPORTS,
    SECTION_ID,
    SECTION_TITLE,
    SystemReport,
    is_section,
)
from app.adapters.postgres.timescale.reports import REPORTS as TIMESCALE_REPORTS
from app.adapters.postgres.timescale.reports import TIMESCALE_SECTION_ID
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

# What a search is given when its caller gives it no clock: what an inspection
# of the catalog is given.
OWN_SECONDS = 5.0

# How long the size of a found relation may wait for its lock. Reading a size
# opens the relation, which waits behind whoever holds it exclusively — an
# ALTER TABLE, a VACUUM FULL — and a search must not wait for a migration: past
# this, the rows are read again without their sizes.
_SIZE_LOCK_SECONDS = 0.1

# How much of a comment travels as the excerpt. The search cuts it again around
# the words, so it is generous rather than tight.
_COMMENT_CHARACTERS = MAX_EXCERPT_CHARACTERS * 5

# Where the listing does not look: another session's temporary tables, and the
# out-of-line storage of large values.
_LISTED = sql.SQL(
    "left(n.nspname, 8) <> 'pg_toast' AND left(n.nspname, 7) <> 'pg_temp'"
)
_RELATIONS = sql.SQL("c.relkind IN ('r', 'p', 'v', 'm')")

# What separates the words of a name, as the word rule has them (D202).
_SEPARATORS = sql.SQL("ARRAY['_', '-', '.', '/', ':', ' ']")


def _folded(column: str) -> sql.Composable:
    """A name or a comment as the server folds it, under the database's collation."""
    return sql.SQL('lower({}::text COLLATE "default")').format(sql.SQL(column))


def _server_folded(name: str) -> sql.Composable:
    """A bound text folded the way `_folded` folds a name."""
    return sql.SQL('lower({}::text COLLATE "default")').format(sql.Placeholder(name))


def _forms(index: int) -> tuple[sql.Composable, sql.Composable]:
    """One word as the word rule folds it, and as the server folds what was typed."""
    return sql.Placeholder(f"w{index}"), _server_folded(f"r{index}")


def _holds_every_word(folded: sql.Composable, count: int) -> sql.Composable:
    """`strpos` of each bound word in a folded name: matched, never compiled."""
    return sql.SQL(" AND ").join(
        sql.SQL("(strpos({folded}, {rule}) > 0 OR strpos({folded}, {server}) > 0)").format(
            folded=folded, rule=rule, server=server
        )
        for rule, server in map(_forms, range(count))
    )


def _begins_every_word(folded: sql.Composable, count: int) -> sql.Composable:
    """Every bound word at the start of the name or right after a separator."""
    return sql.SQL(" AND ").join(
        sql.SQL(
            "EXISTS (SELECT FROM unnest(ARRAY[{rule}::text, {server}]) AS w(word) "
            "WHERE strpos({folded}, w.word) = 1 OR EXISTS (SELECT FROM "
            "unnest({separators}) AS s WHERE strpos({folded}, s || w.word) > 0))"
        ).format(folded=folded, rule=rule, server=server, separators=_SEPARATORS)
        for rule, server in map(_forms, range(count))
    )


def _rank(folded: sql.Composable, count: int) -> sql.Composable:
    """The class of a folded name as a number, best first, as the query orders it.

    Exact, prefix, word, substring: ordered inside the query, before its LIMIT,
    so the best names are never the ones a full page cuts (D202).
    """
    rule, server = _forms(0)
    return sql.SQL(
        "CASE WHEN {folded} = %(exact)s OR {folded} = {typed} THEN 0 "
        "WHEN strpos({folded}, {rule}) = 1 OR strpos({folded}, {server}) = 1 THEN 1 "
        "WHEN {words} THEN 2 ELSE 3 END"
    ).format(
        folded=folded,
        typed=_server_folded("typed"),
        rule=rule,
        server=server,
        words=_begins_every_word(folded, count),
    )


def _names_statement(count: int) -> sql.Composed:
    schema_name = _folded("n.nspname")
    relation_name = _folded("c.relname")
    # The tables a found schema holds, which the listing detects frameworks
    # from, are joined after the LIMIT: for the rows kept, not for every
    # schema that matched.
    return sql.SQL(
        """
        SELECT f.schema, f.relation, f.kind, f.row_estimate,
               array_agg(t.relname::text) FILTER (WHERE t.oid IS NOT NULL) AS tables,
               CASE WHEN f.relid IS NULL OR NOT %(sizes)s THEN NULL
                    ELSE pg_total_relation_size(f.relid) END AS size_bytes
        FROM (
            SELECT * FROM (
                SELECT n.oid AS nspid, n.nspname::text AS schema,
                       NULL::text AS relation, NULL::text AS kind,
                       NULL::real AS row_estimate, NULL::oid AS relid,
                       {schema_rank} AS rank, {schema_name} AS folded
                FROM pg_namespace n
                WHERE %(schema)s::text IS NULL AND {listed} AND {schema_words}
                UNION ALL
                SELECT NULL::oid, n.nspname::text, c.relname::text, c.relkind::text,
                       c.reltuples, c.oid, {relation_rank}, {relation_name}
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE {relations} AND {listed}
                  AND (%(schema)s::text IS NULL OR n.nspname = %(schema)s)
                  AND {relation_words}
            ) AS found
            ORDER BY rank, folded, schema, relation NULLS FIRST
            LIMIT %(limit)s
        ) AS f
        LEFT JOIN pg_class t ON t.relnamespace = f.nspid AND t.relkind IN ('r', 'p')
          AND left(f.schema, 3) <> 'pg_' AND f.schema <> 'information_schema'
        GROUP BY f.nspid, f.schema, f.relation, f.kind, f.row_estimate, f.relid,
                 f.rank, f.folded
        ORDER BY f.rank, f.folded, f.schema, f.relation NULLS FIRST
        """
    ).format(
        schema_rank=_rank(schema_name, count),
        schema_name=schema_name,
        relation_rank=_rank(relation_name, count),
        relation_name=relation_name,
        listed=_LISTED,
        relations=_RELATIONS,
        schema_words=_holds_every_word(schema_name, count),
        relation_words=_holds_every_word(relation_name, count),
    )


def _columns_statement(count: int) -> sql.Composed:
    """Relations by a column's name, a column's comment or their own comment.

    One row per relation, carrying the best of what it was found by: a
    column's name by its class, then a column's comment, then its own.
    """
    column = _folded("a.attname")
    comment = _folded("d.description")
    return sql.SQL(
        """
        SELECT f.schema, f.relation, f.kind, f.row_estimate, f.evidence,
               CASE WHEN %(sizes)s THEN pg_total_relation_size(f.relid) END AS size_bytes
        FROM (
          SELECT * FROM (
            SELECT DISTINCT ON (best.relid)
                   n.nspname::text AS schema, c.relname::text AS relation,
                   c.relkind::text AS kind, c.reltuples AS row_estimate,
                   c.oid AS relid, best.evidence, best.rank
            FROM (
                SELECT a.attrelid AS relid, a.attname::text AS evidence,
                       {column_rank} AS rank
                FROM pg_attribute a
                WHERE a.attnum > 0 AND NOT a.attisdropped AND {column_words}
                UNION ALL
                SELECT a.attrelid, a.attname || ': ' || left(d.description, %(cut)s), 4
                FROM pg_description d
                JOIN pg_attribute a ON a.attrelid = d.objoid AND a.attnum = d.objsubid
                WHERE d.classoid = 'pg_catalog.pg_class'::regclass
                  AND d.objsubid > 0 AND NOT a.attisdropped AND {comment_words}
                UNION ALL
                SELECT d.objoid, left(d.description, %(cut)s), 5
                FROM pg_description d
                WHERE d.classoid = 'pg_catalog.pg_class'::regclass
                  AND d.objsubid = 0 AND {comment_words}
            ) AS best
            JOIN pg_class c ON c.oid = best.relid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE {relations} AND {listed}
              AND (%(schema)s::text IS NULL OR n.nspname = %(schema)s)
            ORDER BY best.relid, best.rank, best.evidence
          ) AS found
          ORDER BY rank, relation, schema
          LIMIT %(limit)s
        ) AS f
        ORDER BY f.rank, f.relation, f.schema
        """
    ).format(
        column_rank=_rank(column, count),
        column_words=_holds_every_word(column, count),
        comment_words=_holds_every_word(comment, count),
        relations=_RELATIONS,
        listed=_LISTED,
    )


# Every schema and relation the listing shows, for a kept list (D213): one
# query, no sizes — a size opens the relation and waits behind its lock.
_ALL_NAMES = sql.SQL(
    """
    SELECT * FROM (
        SELECT n.nspname::text AS schema, NULL::text AS relation, NULL::text AS kind,
               NULL::real AS row_estimate, NULL::bigint AS size_bytes,
               (SELECT array_agg(t.relname::text) FROM pg_class t
                WHERE t.relnamespace = n.oid AND t.relkind IN ('r', 'p')
                  AND left(n.nspname, 3) <> 'pg_'
                  AND n.nspname <> 'information_schema') AS tables
        FROM pg_namespace n
        WHERE {listed}
        UNION ALL
        SELECT n.nspname::text, c.relname::text, c.relkind::text, c.reltuples,
               NULL::bigint, NULL::text[]
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE {relations} AND {listed}
    ) AS every_name
    ORDER BY schema, relation NULLS FIRST
    LIMIT %(limit)s
    """
).format(listed=_LISTED, relations=_RELATIONS)

# How many names one batch of a pass carries.
_BATCH = 1000


class PostgresSearch:
    """`catalog/search` and the columns search of a PostgreSQL server."""

    def __init__(
        self, session: PostgresSession, relation_context: PostgresRelationContext
    ) -> None:
        self._session = session
        self._relation_context = relation_context

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = _words(request)
        node_id = request.node_id
        if node_id == TIMESCALE_SECTION_ID:
            await require_timescale(self._session)
            return _reports(TIMESCALE_REPORTS, words, request.limit, node_id, "TimescaleDB")
        if node_id is not None and is_section(node_id):
            return _reports(REPORTS, words, request.limit, node_id, say(SECTION_TITLE))
        schema = _schema(node_id)

        async def names(ends: float) -> NodeSearchResult:
            rows = await self._sized(
                _names_statement(len(words)), _parameters(request, words, schema), ends
            )
            if not rows and schema is not None:
                await self._require(schema, ends)
            return await self._result(rows, request.limit)

        return await _within(bounds, names)

    async def search_columns(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = _words(request)
        node_id = request.node_id
        if node_id is not None and (node_id == TIMESCALE_SECTION_ID or is_section(node_id)):
            # Reports are statements, not relations: they have no comments,
            # and their columns are what the statement says.
            return NodeSearchResult()
        schema = _schema(node_id)

        async def columns(ends: float) -> NodeSearchResult:
            parameters = {
                **_parameters(request, words, schema),
                "cut": _COMMENT_CHARACTERS,
            }
            rows = await self._sized(_columns_statement(len(words)), parameters, ends)
            if not rows and schema is not None:
                await self._require(schema, ends)
            return await self._result(rows, request.limit, evidence=True)

        return await _within(bounds, columns)

    async def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        """Every schema and relation, for a kept list: one scope, the server.

        The reports are written here rather than read, and are found live.
        """
        seconds = bounds.left()
        if seconds <= 0:
            yield NameBatch(notice=say("Time ran out before the server was asked"))
            return
        rows = await self._session.bounded_query(
            _ALL_NAMES, {"limit": limit + 1}, seconds=seconds
        )
        notice = (
            say("More than {limit} names; the first {limit} are kept", limit=f"{limit:,}")
            if len(rows) > limit
            else None
        )
        rows = rows[:limit]
        contexts: dict[str, SchemaRelationContext] = {}
        for start in range(0, len(rows), _BATCH):
            names: list[KeptName] = []
            for row in rows[start : start + _BATCH]:
                schema = row["schema"]
                if row["relation"] is not None and schema not in contexts:
                    contexts[schema] = await self._relation_context.schema(schema)
                match = _match(row, contexts, evidence=False)
                names.append(
                    KeptName(node=match.node, parent_id=match.parent_id, location=match.location)
                )
            yield NameBatch(names=names)
        if notice is not None:
            yield NameBatch(notice=notice)

    async def _sized(
        self, statement: sql.Composed, parameters: Mapping[str, object], ends: float
    ) -> list[dict[str, Any]]:
        """The rows with the sizes of what they found, or without them when a
        size would wait for somebody's lock."""
        try:
            return await self._session.bounded_query(
                statement,
                {**parameters, "sizes": True},
                seconds=_left(ends),
                lock_seconds=_SIZE_LOCK_SECONDS,
            )
        except LockNotGranted:
            return await self._session.bounded_query(
                statement, {**parameters, "sizes": False}, seconds=_left(ends)
            )

    async def _require(self, schema: str, ends: float) -> None:
        found = await self._session.bounded_query(
            sql.SQL("SELECT 1 FROM pg_namespace WHERE nspname = %s"),
            (schema,),
            seconds=_left(ends),
        )
        if not found:
            raise NodeNotFound(schema)

    async def _result(
        self, rows: list[dict[str, Any]], limit: int, *, evidence: bool = False
    ) -> NodeSearchResult:
        """The rows as the listing builds them, one relation context per schema."""
        complete = len(rows) <= limit
        rows = rows[:limit]
        contexts: dict[str, SchemaRelationContext] = {}
        for row in rows:
            schema = row["schema"]
            if row["relation"] is not None and schema not in contexts:
                contexts[schema] = await self._relation_context.schema(schema)
        return NodeSearchResult(
            matches=[_match(row, contexts, evidence=evidence) for row in rows],
            complete=complete,
            notice=None if complete else say("The first {limit} matches; there may be more", limit=limit),
        )


def _words(request: NodeSearchRequest) -> tuple[str, ...]:
    words = words_of(request.query)
    if not words:
        raise ValueError(say("A search needs something to look for"))
    return words


def _schema(node_id: str | None) -> str | None:
    """The schema a search starts in, or None for the top; a refusal for a leaf."""
    if node_id is None:
        return None
    schema, _, relation = node_id.partition(".")
    if relation or node_id.startswith(f"{SECTION_ID}."):
        raise ValueError(say("A search starts at the top, in a schema or among the reports"))
    return schema


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


def _left(ends: float) -> float:
    return max(0.001, ends - time.monotonic())


def _match(
    row: Mapping[str, Any],
    contexts: Mapping[str, SchemaRelationContext],
    *,
    evidence: bool,
) -> NodeMatch:
    schema = row["schema"]
    relation = row["relation"]
    excerpt = row["evidence"] if evidence else None
    if relation is None:
        node: CatalogNode = schema_of({"name": schema, "tables": row["tables"]})
        return NodeMatch(node=node, parent_id=None, location="")
    return NodeMatch(
        node=relation_of(schema, relation, row, contexts[schema]),
        parent_id=schema,
        location=schema,
        excerpt=excerpt,
    )


def _reports(
    reports: Sequence[SystemReport],
    words: tuple[str, ...],
    limit: int,
    section_id: str,
    section_title: str,
) -> NodeSearchResult:
    """The reports of one section, by title: they are written here, not asked,
    and found by the title a person reads, in the language of the request."""
    found = [
        (class_rank(match_class), title, report)
        for report in reports
        if (match_class := class_of_name(words, title := say(report.title))) is not None
    ]
    found.sort(key=lambda one: (one[0], one[1]))
    return NodeSearchResult(
        matches=[
            NodeMatch(node=report_node(report), parent_id=section_id, location=section_title)
            for _, _, report in found[:limit]
        ],
        complete=len(found) <= limit,
    )


async def _within(
    bounds: SearchBounds | None,
    work: Callable[[float], Awaitable[NodeSearchResult]],
) -> NodeSearchResult:
    """The search under its clock: the server's statement timeout and this task's.

    `work` is handed the moment it must be done by. The relation contexts after
    the query are bounded by the same clock, so a slow inspection cannot
    outlive the answer that asked for it.
    """
    seconds = OWN_SECONDS if bounds is None else bounds.left()
    if seconds <= 0 or (bounds is not None and bounds.stopped()):
        return NodeSearchResult(
            complete=False, notice=say("Time ran out before the server was asked")
        )
    try:
        async with asyncio.timeout(seconds):
            return await work(time.monotonic() + seconds)
    except TimeoutError:
        raise AdapterError("timeout", say("The server did not answer in time")) from None
