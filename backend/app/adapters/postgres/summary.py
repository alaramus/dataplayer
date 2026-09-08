"""Describing one relation of a PostgreSQL server (D75).

Nothing here reads a row of anybody's data. The shape of the relation is the
model the structure screen already asks for, reduced to counts and to the facts
about storage that the model states but no column of it carries; the only query
written for this capability is the one that asks the server when it last looked
at the relation, which nothing else needed.

The two questions are deliberately different. The relation model says what the
table is made of, column by column and constraint by constraint, and has a
screen of its own. This says what the thing is: who owns it, how it is stored,
how much of it there is, and how recently the server measured it.
"""

from collections.abc import Mapping
from typing import Any

from app.adapters.catalog import NodeKind
from app.adapters.postgres.catalog import DDL_REPRESENTATION, TABLE_REPRESENTATION
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.summary import related_views
from app.adapters.relation import RelationKind, RelationModel
from app.adapters.summary import NodeSummary, RelationContents

# When the planner's statistics were last brought up to date, and when the dead
# rows were last cleared, whether a person asked or the server decided to. Both
# are read as one because both answer the same question: how recently was this
# relation looked at. `GREATEST` skips nulls, so a table only ever vacuumed by
# autovacuum states that time rather than nothing.
_STATISTICS = """
SELECT GREATEST(s.last_analyze, s.last_autoanalyze) AS analyzed_at,
       GREATEST(s.last_vacuum, s.last_autovacuum) AS vacuumed_at
FROM pg_stat_all_tables s
JOIN pg_class c ON c.oid = s.relid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %s AND c.relname = %s
"""


def _node_kind(kind: RelationKind) -> NodeKind:
    """What the catalog calls this relation.

    Narrower there than here: a materialized view is a view to somebody
    walking the catalog and a stored table to somebody asking how it works,
    and `relation_kind` in the contents keeps the second answer.
    """
    return "view" if kind in ("view", "materialized_view") else "table"


class PostgresSummaries:
    """The `node-summary` capability of a PostgreSQL source."""

    def __init__(self, session: PostgresSession, relation: PostgresRelation) -> None:
        self._session = session
        self._relation = relation

    async def node_summary(self, node_id: str) -> NodeSummary:
        # Raises `NodeNotFound` for a relation that is gone and `ValueError`
        # for an id that names no relation at all, which is the answer a
        # schema gets: a schema is not marked summarizable, so nothing asks.
        model = await self._relation.relation_model(node_id)
        statistics = await self._statistics(model)
        representations = [TABLE_REPRESENTATION]
        if model.specialization is None:
            representations.append(DDL_REPRESENTATION)
        return NodeSummary(
            node_id=node_id,
            name=model.name,
            kind=_node_kind(model.kind),
            # The same pair the catalog gives this node, so "what can this be
            # opened as" is answered once and in one place (D47).
            representations=representations,
            size_bytes=model.size_bytes,
            related_views=related_views(model),
            contents=RelationContents(
                relation_kind=model.kind,
                specialization=model.specialization,
                schema_name=model.schema_name or "",
                owner=model.owner,
                persistence=model.persistence,
                comment=model.comment,
                columns=len(model.columns),
                indexes=len(model.indexes),
                constraints=len(model.constraints),
                row_estimate=model.row_estimate,
                analyzed_at=statistics.get("analyzed_at"),
                vacuumed_at=statistics.get("vacuumed_at"),
                partitioned_by=(
                    None
                    if model.partitioning is None
                    else f"{model.partitioning.strategy} ({model.partitioning.key})"
                ),
                partition_of=(
                    None if model.partition_of is None else model.partition_of.parent_node_id
                ),
            ),
        )

    async def _statistics(self, model: RelationModel) -> Mapping[str, Any]:
        """When the server last measured this relation, where it measures it.

        A plain view has no entry in the statistics at all, and neither has a
        materialized view that was never refreshed. Both leave the two times
        absent rather than filled with a zero that would read as a date.
        """
        rows = await self._session.query(
            _STATISTICS, (model.schema_name or "", model.name)
        )
        return rows[0] if rows else {}
