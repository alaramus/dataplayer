"""Describing one relation of a cluster (D75).

The relation model reduced to counts, as PostgreSQL's summary is. The server
keeps no time a table was created or written to that a client can read.
"""

from app.adapters.cassandra.catalog import DDL_REPRESENTATION, TABLE_REPRESENTATION
from app.adapters.cassandra.relation import CassandraRelation, model_of
from app.adapters.summary import NodeSummary, RelationContents
from app.adapters.words import worded_titles


class CassandraSummaries:
    def __init__(self, relation: CassandraRelation) -> None:
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
                schema_name=facts.keyspace,
                persistence=model.persistence,
                comment=model.comment,
                columns=len(model.columns),
                indexes=len(model.indexes),
                constraints=len(model.constraints),
                partitioned_by=", ".join(column.name for column in facts.partition_key)
                or None,
            ),
        )
