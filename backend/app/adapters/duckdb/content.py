"""A relation's DDL, as the file keeps it: its statement, then its indexes' (D389)."""

from app.adapters.content import ContentRequest, ContentResult, SqlContent
from app.adapters.duckdb.relation import DuckdbRelation
from app.core.translation import say

MAX_DDL_BYTES = 256 * 1024


class DuckdbContent:
    def __init__(self, relation: DuckdbRelation) -> None:
        self._relation = relation

    async def read_content(self, request: ContentRequest) -> ContentResult:
        if request.representation != "sql":
            raise ValueError(
                say(
                    'This DuckDB source does not offer the "{representation}" content representation',
                    representation=request.representation,
                )
            )
        facts = await self._relation.facts(request.node_id)
        statements = [facts.text or "", *(index.definition or "" for index in facts.indexes)]
        ddl = "\n\n".join(statement.strip() for statement in statements if statement.strip())
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
