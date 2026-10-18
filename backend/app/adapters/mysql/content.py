"""A relation's DDL, as the server itself writes it.

`SHOW CREATE TABLE` rather than a statement put together from the catalog: the
server's own text carries the engine, the character set, the defaults and the
AUTO_INCREMENT that a reconstruction leaves out, and it is what a person
pastes into another MySQL.
"""

from app.adapters.content import ContentRequest, ContentResult, SqlContent
from app.adapters.mysql.relation import MysqlRelation
from app.adapters.mysql.session import MysqlSession
from app.adapters.mysql.sql import SQL, Identifier
from app.core.translation import say

MAX_DDL_BYTES = 256 * 1024


class MysqlContent:
    def __init__(self, session: MysqlSession, relation: MysqlRelation) -> None:
        self._session = session
        self._relation = relation

    async def read_content(self, request: ContentRequest) -> ContentResult:
        if request.representation != "sql":
            raise ValueError(
                say(
                    'This MySQL source does not offer the "{representation}" content representation',
                    representation=request.representation,
                )
            )
        # Confirms the relation is there, and says so as a missing node.
        facts = await self._relation.facts(request.node_id, structure=False)
        statement = SQL("SHOW CREATE TABLE {}").format(Identifier(facts.schema, facts.name))
        rows = await self._session.query(statement.text())
        row = rows[0]
        ddl = str(row.get("Create View") or row.get("Create Table") or "")
        encoded = ddl.encode()
        truncated = len(encoded) > MAX_DDL_BYTES
        text = encoded[:MAX_DDL_BYTES].decode(errors="ignore") if truncated else ddl
        return SqlContent(
            text=text + ";" if not truncated else text,
            truncated=truncated,
            notice=(
                say("This DDL is larger than 256 KB; only its beginning is shown.")
                if truncated
                else None
            ),
        )
