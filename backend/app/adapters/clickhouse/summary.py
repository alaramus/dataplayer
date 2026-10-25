"""Describing one relation of a ClickHouse server (D75).

The relation model reduced to counts, as PostgreSQL's summary is, with the
time the table was last written to: its newest active part. The server keeps
no time a table was created.
"""

from datetime import datetime

from app.adapters.clickhouse.catalog import DDL_REPRESENTATION, TABLE_REPRESENTATION
from app.adapters.clickhouse.relation import ClickhouseRelation, model_of
from app.adapters.clickhouse.session import ClickhouseSession
from app.adapters.summary import NodeSummary, RelationContents
from app.adapters.words import worded_titles

_WRITTEN = """
SELECT max(modification_time) AS written, count() AS parts
FROM system.parts
WHERE database = {database:String} AND table = {table:String} AND active
"""


class ClickhouseSummaries:
    def __init__(self, session: ClickhouseSession, relation: ClickhouseRelation) -> None:
        self._session = session
        self._relation = relation

    async def node_summary(self, node_id: str) -> NodeSummary:
        facts = await self._relation.facts(node_id)
        model = model_of(node_id, facts)
        written: datetime | None = None
        if facts.engine.endswith("MergeTree"):
            rows = await self._session.query(
                _WRITTEN, {"database": facts.schema, "table": facts.name}
            )
            if rows and int(rows[0]["parts"]) > 0:
                # Written in UTC with its `Z` (D268).
                written = datetime.fromisoformat(str(rows[0]["written"]))
        return NodeSummary(
            node_id=node_id,
            name=model.name,
            kind="view" if facts.is_view else "table",
            representations=worded_titles([TABLE_REPRESENTATION, DDL_REPRESENTATION]),
            size_bytes=model.size_bytes,
            modified_at=written,
            contents=RelationContents(
                relation_kind=model.kind,
                schema_name=facts.schema,
                persistence=model.persistence,
                comment=model.comment,
                columns=len(model.columns),
                indexes=len(model.indexes),
                constraints=len(model.constraints),
                row_estimate=model.row_estimate,
                partitioned_by=facts.partition_key,
            ),
        )
