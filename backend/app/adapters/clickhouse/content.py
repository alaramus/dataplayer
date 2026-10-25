"""A relation's DDL, as the server itself writes it.

`SHOW CREATE TABLE` rather than a statement put together from the catalog, for
MySQL's reason: the engine, its settings, codecs and TTLs are in the server's
own text, and it is what a person pastes into another ClickHouse.
"""

import textwrap

from app.adapters.clickhouse.relation import ClickhouseRelation
from app.adapters.clickhouse.reports import report_for
from app.adapters.clickhouse.session import ClickhouseSession
from app.adapters.clickhouse.sql import SQL, Identifier
from app.adapters.content import ContentRequest, ContentResult, SqlContent
from app.core.translation import say

MAX_DDL_BYTES = 256 * 1024


class ClickhouseContent:
    def __init__(self, session: ClickhouseSession, relation: ClickhouseRelation) -> None:
        self._session = session
        self._relation = relation

    async def read_content(self, request: ContentRequest) -> ContentResult:
        if request.representation != "sql":
            raise ValueError(
                say(
                    'This ClickHouse source does not offer the "{representation}" content representation',
                    representation=request.representation,
                )
            )
        report = report_for(request.node_id)
        if report is not None:
            # What the report runs, as it is written here, without the
            # indentation of the Python file it lives in.
            return SqlContent(text=textwrap.dedent(report.statement).strip())
        # Confirms the relation is there, and says so as a missing node.
        facts = await self._relation.facts(request.node_id, structure=False)
        statement = SQL("SHOW CREATE TABLE {}").format(Identifier(facts.schema, facts.name))
        answer = await self._session.answer(statement.text())
        ddl = str(answer.rows[0][0]) if answer.rows else ""
        encoded = ddl.encode()
        truncated = len(encoded) > MAX_DDL_BYTES
        text = encoded[:MAX_DDL_BYTES].decode(errors="ignore") if truncated else ddl + ";"
        return SqlContent(
            text=text,
            truncated=truncated,
            notice=(
                say("This DDL is larger than 256 KB; only its beginning is shown.")
                if truncated
                else None
            ),
        )
