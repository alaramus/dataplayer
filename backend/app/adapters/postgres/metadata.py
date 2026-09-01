"""What an editor may complete to, asked of the server progressively.

D65: the current search path's relations first, a relation's columns when one
appears or completion asks, and another schema only when something is qualified
with it. Nothing here reads a whole database to fill a dropdown.

Everything is bounded, and the answer says whether it was cut short: a console
that has not been told about a relation must not underline it in red.
"""

from psycopg import sql

from app.adapters.postgres.session import PostgresSession
from app.adapters.query import (
    ColumnSummary,
    GeneratedQuery,
    GenerateQueryRequest,
    QueryMetadata,
    QueryMetadataRequest,
    RelationSummary,
)

# How much one answer may carry. A schema with more relations than this is
# answered with what fits and `complete=False`, which the editor shows as a
# status rather than as a claim about what exists.
MAX_SCHEMAS = 200
MAX_RELATIONS = 2000
MAX_COLUMNS = 5000

_KINDS: dict[str, str] = {
    "r": "table",
    "p": "table",
    "v": "view",
    "m": "materialized_view",
    "f": "foreign_table",
}

# Schemas nobody completes against. `pg_catalog` is deliberately not hidden:
# somebody writing SQL against PostgreSQL does read it.
_HIDDEN = ("pg_toast", "pg_temp_%", "pg_toast_temp_%", "information_schema")


class PostgresMetadata:
    """The source's own answer to "what is there to write about"."""

    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    async def metadata(self, request: QueryMetadataRequest) -> QueryMetadata:
        schemas = await self._schemas()
        known = set(schemas)
        asked = [name for name in request.search_path if name in known]
        # A document that has not chosen a context gets the connection's own:
        # what an unqualified name would mean if it were run right now (D63).
        wanted = asked or [
            name for name in await self._effective_search_path() if name in known
        ]
        relations, complete = await self._relations(wanted)
        columns = await self._columns(request.relations)
        return QueryMetadata(
            schemas=schemas,
            relations=relations,
            columns=columns,
            complete=complete,
        )

    async def _effective_search_path(self) -> list[str]:
        """What this connection resolves an unqualified name against."""
        rows = await self._session.query(
            "SELECT current_schemas(false) AS schemas"
        )
        found = rows[0]["schemas"] if rows else None
        return [str(name) for name in found] if isinstance(found, list) else []

    async def _schemas(self) -> list[str]:
        rows = await self._session.query(
            """
            SELECT nspname
            FROM pg_namespace
            WHERE nspname NOT LIKE ALL (%s)
            ORDER BY nspname
            LIMIT %s
            """,
            (list(_HIDDEN), MAX_SCHEMAS),
        )
        return [str(row["nspname"]) for row in rows]

    async def _relations(self, schemas: list[str]) -> tuple[list[RelationSummary], bool]:
        """Every relation of these schemas, up to the ceiling, and whether that was all."""
        if not schemas:
            return [], True
        rows = await self._session.query(
            """
            SELECT n.nspname AS schema_name, c.relname AS name, c.relkind AS kind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = ANY(%s) AND c.relkind = ANY(%s)
            ORDER BY n.nspname, c.relname
            LIMIT %s
            """,
            (schemas, list(_KINDS), MAX_RELATIONS + 1),
        )
        complete = len(rows) <= MAX_RELATIONS
        return (
            [
                RelationSummary(
                    schema_name=str(row["schema_name"]),
                    name=str(row["name"]),
                    kind=_KINDS.get(str(row["kind"]), "other"),  # type: ignore[arg-type]
                )
                for row in rows[:MAX_RELATIONS]
            ],
            complete,
        )

    async def _columns(self, relations: list[str]) -> dict[str, list[ColumnSummary]]:
        """The columns of the relations that were asked for, by qualified name.

        The names are bound as values and matched against the catalog, never
        composed into the statement: a name typed into an editor is a client
        string like any other (D2c).
        """
        wanted = [_split(name) for name in relations]
        pairs = [pair for pair in wanted if pair is not None]
        if not pairs:
            return {}
        # Two parallel arrays rather than an array of records: a pair is bound
        # as two values, and `unnest` puts them back together on the server.
        rows = await self._session.query(
            """
            SELECT n.nspname AS schema_name,
                   c.relname AS relation,
                   a.attname AS name,
                   format_type(a.atttypid, a.atttypmod) AS type_sql,
                   a.attnum AS position
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN unnest(%s::text[], %s::text[]) AS asked(schema_name, relation)
              ON asked.schema_name = n.nspname AND asked.relation = c.relname
            WHERE a.attnum > 0 AND NOT a.attisdropped
            ORDER BY n.nspname, c.relname, a.attnum
            LIMIT %s
            """,
            (
                [pair[0] for pair in pairs],
                [pair[1] for pair in pairs],
                MAX_COLUMNS,
            ),
        )
        found: dict[str, list[ColumnSummary]] = {}
        for row in rows:
            key = f"{row['schema_name']}.{row['relation']}"
            found.setdefault(key, []).append(
                ColumnSummary(name=str(row["name"]), type_sql=str(row["type_sql"]))
            )
        return found


# What a generated statement puts between its clauses.
LINE = chr(10)

# How many rows a statement written by the source asks for. A generated query
# is a starting point, not a way to read a table whole (D65).
GENERATED_LIMIT = 100


class PostgresGeneration:
    """Statements the source writes about its own nodes.

    Here rather than in a browser because quoting a name is a property of the
    dialect: `sql.Identifier` decides what needs quotes, and a client that
    assembled the text itself would be one apostrophe away from composing SQL
    (D2c, D65).
    """

    def __init__(self, session: PostgresSession, metadata: PostgresMetadata) -> None:
        self._session = session
        self._metadata = metadata

    async def generate(self, request: GenerateQueryRequest) -> GeneratedQuery:
        parts = _split(request.node_id)
        if parts is None:
            raise ValueError(f'"{request.node_id}" is not a relation of this source')
        schema, relation = parts
        columns = (await self._metadata.metadata(
            QueryMetadataRequest(relations=[request.node_id])
        )).columns.get(request.node_id, [])
        if not columns:
            raise ValueError(f'"{request.node_id}" is not a relation of this source')
        qualified = sql.Identifier(schema, relation)
        names = sql.SQL(", ").join(sql.Identifier(column.name) for column in columns)
        if request.kind == "name":
            return GeneratedQuery(text=qualified.as_string())
        if request.kind == "columns":
            return GeneratedQuery(text=names.as_string())
        statement = sql.SQL("SELECT {columns}" + LINE + "FROM {relation}" + LINE + "LIMIT {limit}").format(
            columns=names, relation=qualified, limit=sql.Literal(GENERATED_LIMIT)
        )
        return GeneratedQuery(text=statement.as_string())


def _split(qualified: str) -> tuple[str, str] | None:
    """A `schema.relation` as its two parts, or nothing when it is neither."""
    schema, separator, relation = qualified.partition(".")
    if not separator or not schema or not relation or "." in relation:
        return None
    return schema, relation

