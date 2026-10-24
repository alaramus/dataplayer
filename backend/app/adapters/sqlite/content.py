"""A relation's DDL, as the file keeps it.

The text SQLite stores in `sqlite_schema` for the table, and after it the
indexes and triggers written for it: what the library parses each time the
file opens, and what a person pastes into another SQLite.
"""

from app.adapters.content import ContentRequest, ContentResult, SqlContent
from app.adapters.sqlite.relation import SqliteRelation
from app.adapters.sqlite.session import Reading, SqliteSession
from app.core.translation import say

MAX_DDL_BYTES = 256 * 1024

_BESIDE = """
SELECT sql FROM sqlite_schema
WHERE tbl_name = ? AND type IN ('index', 'trigger') AND sql IS NOT NULL
ORDER BY type, name
"""


class SqliteContent:
    def __init__(self, session: SqliteSession, relation: SqliteRelation) -> None:
        self._session = session
        self._relation = relation

    async def read_content(self, request: ContentRequest) -> ContentResult:
        if request.representation != "sql":
            raise ValueError(
                say(
                    'This SQLite source does not offer the "{representation}" content representation',
                    representation=request.representation,
                )
            )
        # Confirms the relation is there, and says so as a missing node.
        facts = await self._relation.facts(request.node_id, structure=False)

        def beside(reading: Reading) -> list[str]:
            return [str(row["sql"]) for row in reading.rows(_BESIDE, (facts.name,))]

        statements = [facts.text or "", *await self._session.read(beside)]
        ddl = ";\n\n".join(statement.strip() for statement in statements if statement) + ";"
        encoded = ddl.encode()
        truncated = len(encoded) > MAX_DDL_BYTES
        return SqlContent(
            text=encoded[:MAX_DDL_BYTES].decode(errors="ignore") if truncated else ddl,
            truncated=truncated,
            notice=(
                say("This DDL is larger than 256 KB; only its beginning is shown.")
                if truncated
                else None
            ),
        )
