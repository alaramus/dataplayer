"""Describing one relation of a DuckDB file (D75): the relation model reduced to counts."""

from app.adapters.duckdb.catalog import DDL_REPRESENTATION, TABLE_REPRESENTATION
from app.adapters.duckdb.relation import DuckdbRelation, model_of
from app.adapters.summary import NodeSummary, RelationContents
from app.adapters.words import worded_titles


class DuckdbSummaries:
    def __init__(self, relation: DuckdbRelation) -> None:
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
                schema_name=facts.schema,
                persistence=model.persistence,
                columns=len(model.columns),
                indexes=len(model.indexes),
                constraints=len(model.constraints),
                row_estimate=model.row_estimate,
            ),
        )
