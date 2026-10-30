"""Describing one collection of a MongoDB server (D75).

The relation model reduced to counts, as PostgreSQL's summary is. The server
keeps no time a collection was made or last written to.
"""

from app.adapters.mongodb.catalog import REPRESENTATIONS
from app.adapters.mongodb.relation import MongodbRelation, model_of
from app.adapters.summary import NodeSummary, RelationContents
from app.adapters.words import worded_titles


class MongodbSummaries:
    def __init__(self, relation: MongodbRelation) -> None:
        self._relation = relation

    async def node_summary(self, node_id: str) -> NodeSummary:
        facts = await self._relation.facts(node_id)
        model = model_of(node_id, facts)
        return NodeSummary(
            node_id=node_id,
            name=model.name,
            kind="view" if facts.is_view else "table",
            representations=worded_titles(REPRESENTATIONS),
            size_bytes=model.size_bytes,
            contents=RelationContents(
                relation_kind=model.kind,
                schema_name=facts.database,
                persistence=model.persistence,
                columns=len(model.columns),
                indexes=len(model.indexes),
                constraints=len(model.constraints),
                row_estimate=model.row_estimate,
            ),
        )
