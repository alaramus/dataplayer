"""Describing one relation of a MySQL server (D75).

The relation model reduced to counts, as PostgreSQL's summary is, with the two
times MySQL records and PostgreSQL does not: when the table was created and
when it was last written to.
"""

from datetime import UTC, datetime
from typing import Any

from app.adapters.mysql.catalog import DDL_REPRESENTATION, TABLE_REPRESENTATION
from app.adapters.mysql.relation import MysqlRelation, model_of
from app.adapters.mysql.session import MysqlSession
from app.adapters.summary import NodeSummary, RelationContents
from app.adapters.words import worded_titles

_TIMES = """
SELECT CREATE_TIME AS created_at, UPDATE_TIME AS updated_at
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
"""


def _moment(value: Any) -> datetime | None:
    # Written in the session's time zone, which this source keeps in UTC.
    return value.replace(tzinfo=UTC) if isinstance(value, datetime) else None


class MysqlSummaries:
    def __init__(self, session: MysqlSession, relation: MysqlRelation) -> None:
        self._session = session
        self._relation = relation

    async def node_summary(self, node_id: str) -> NodeSummary:
        facts = await self._relation.facts(node_id)
        model = model_of(node_id, facts)
        times: dict[str, Any] = {}
        if not facts.is_view:
            rows = await self._session.query(_TIMES, (facts.schema, facts.name))
            times = rows[0] if rows else {}
        return NodeSummary(
            node_id=node_id,
            name=model.name,
            kind="view" if facts.is_view else "table",
            representations=worded_titles([TABLE_REPRESENTATION, DDL_REPRESENTATION]),
            size_bytes=model.size_bytes,
            created_at=_moment(times.get("created_at")),
            modified_at=_moment(times.get("updated_at")),
            contents=RelationContents(
                relation_kind=model.kind,
                schema_name=facts.schema,
                persistence=model.persistence,
                comment=model.comment,
                columns=len(model.columns),
                indexes=len(model.indexes),
                constraints=len(model.constraints),
                row_estimate=model.row_estimate,
            ),
        )
