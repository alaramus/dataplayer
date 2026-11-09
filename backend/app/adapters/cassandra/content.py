"""A relation's DDL, as the server itself writes it (D341).

`DESCRIBE` on the server rather than a statement put together from
`system_schema`: the table's options, its clustering order, its indexes and
the views over it are in the server's own text, and it is what a person pastes
into another cluster.
"""

from app.adapters.cassandra.cql import SQL, Identifier
from app.adapters.cassandra.relation import CassandraRelation
from app.adapters.cassandra.session import CassandraSession
from app.adapters.content import ContentRequest, ContentResult, SqlContent
from app.core.translation import say

MAX_DDL_BYTES = 256 * 1024


class CassandraContent:
    def __init__(self, session: CassandraSession, relation: CassandraRelation) -> None:
        self._session = session
        self._relation = relation

    async def read_content(self, request: ContentRequest) -> ContentResult:
        if request.representation != "sql":
            raise ValueError(
                say(
                    'This Cassandra source does not offer the "{representation}" content representation',
                    representation=request.representation,
                )
            )
        # Confirms the relation is there, and says so as a missing node.
        facts = await self._relation.facts(request.node_id)
        describe = SQL(
            "DESCRIBE MATERIALIZED VIEW {}" if facts.is_view else "DESCRIBE TABLE {}"
        )
        answer = await self._session.rows(
            describe.format(Identifier(facts.keyspace, facts.name)).text()
        )
        statements = [str(row["create_statement"]) for row in answer.dicts()]
        ddl = "\n\n".join(statement.rstrip() for statement in statements if statement)
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
