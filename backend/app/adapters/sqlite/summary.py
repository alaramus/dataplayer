"""Describing one relation of a SQLite file (D75).

The relation model reduced to counts, as PostgreSQL's summary is. SQLite keeps
no times for a table, and the file's own time is the whole database's.
"""

from app.adapters.sqlite.catalog import DDL_REPRESENTATION, TABLE_REPRESENTATION
from app.adapters.sqlite.inspection import SCHEMA
from app.adapters.sqlite.relation import SqliteRelation, model_of
from app.adapters.summary import NodeSummary, RelationContents
from app.adapters.words import worded_titles


class SqliteSummaries:
    def __init__(self, relation: SqliteRelation) -> None:
        self._relation = relation

    async def node_summary(self, node_id: str) -> NodeSummary:
        facts = await self._relation.facts(node_id)
        model = model_of(node_id, facts)
        return NodeSummary(
            node_id=node_id,
            name=model.name,
            kind="view" if facts.is_view else "table",
            representations=worded_titles([TABLE_REPRESENTATION, DDL_REPRESENTATION]),
            contents=RelationContents(
                relation_kind=model.kind,
                schema_name=SCHEMA,
                persistence=model.persistence,
                columns=len(model.columns),
                indexes=len(model.indexes),
                constraints=len(model.constraints),
                row_estimate=model.row_estimate,
            ),
        )
