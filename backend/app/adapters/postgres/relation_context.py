"""One Timescale-aware classification shared by PostgreSQL operations (D122)."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.adapters.features import FeatureState, SourceFeature
from app.adapters.postgres.features import PostgresFeatures
from app.adapters.postgres.session import PostgresSession
from app.adapters.specializations import (
    RelationSpecialization,
    TimescaleContinuousAggregate,
    TimescaleHypertable,
)

_CLASSIFY_SQL = """
WITH target(schema_name, relation_name) AS (
  VALUES (%s::text, %s::text)
)
SELECT hypertable.hypertable_name AS relation_name,
       'timescale_hypertable' AS specialization
FROM timescaledb_information.hypertables AS hypertable
CROSS JOIN target
WHERE hypertable.hypertable_schema = target.schema_name
  AND (target.relation_name IS NULL
       OR hypertable.hypertable_name = target.relation_name)
UNION ALL
SELECT aggregate.view_name AS relation_name,
       'timescale_continuous_aggregate' AS specialization
FROM timescaledb_information.continuous_aggregates AS aggregate
CROSS JOIN target
WHERE aggregate.view_schema = target.schema_name
  AND (target.relation_name IS NULL OR aggregate.view_name = target.relation_name)
"""


@dataclass(frozen=True)
class SchemaRelationContext:
    timescale_state: FeatureState
    specializations: Mapping[str, RelationSpecialization]
    reason: str | None = None

    @property
    def known(self) -> bool:
        return self.timescale_state in {"absent", "available"}

    def specialization_for(self, relation: str) -> RelationSpecialization | None:
        return self.specializations.get(relation)

    def hypertable_for(self, relation: str) -> TimescaleHypertable | None:
        specialization = self.specialization_for(relation)
        return (
            specialization
            if isinstance(specialization, TimescaleHypertable)
            else None
        )

    def continuous_aggregate_for(
        self, relation: str
    ) -> TimescaleContinuousAggregate | None:
        specialization = self.specialization_for(relation)
        return (
            specialization
            if isinstance(specialization, TimescaleContinuousAggregate)
            else None
        )

    def ordinary_statistics_are_valid_for(self, relation: str) -> bool:
        return self.known and self.specialization_for(relation) is None


class PostgresRelationContext:
    def __init__(
        self,
        session: PostgresSession,
        features: PostgresFeatures | None = None,
    ) -> None:
        self._session = session
        self._features = features or PostgresFeatures(session)

    async def schema(
        self, schema: str, relation: str | None = None
    ) -> SchemaRelationContext:
        profile = await self._features.timescale()
        feature = profile.feature
        if feature.state != "available":
            return _context(feature, {})

        rows = await self._session.query(_CLASSIFY_SQL, (schema, relation))
        found: dict[str, RelationSpecialization] = {}
        for row in rows:
            name = row.get("relation_name")
            kind = row.get("specialization")
            if not isinstance(name, str):
                continue
            specialization: RelationSpecialization
            if kind == "timescale_hypertable":
                specialization = TimescaleHypertable()
            elif kind == "timescale_continuous_aggregate":
                specialization = TimescaleContinuousAggregate()
            else:
                continue
            if name in found:
                return SchemaRelationContext(
                    timescale_state="unavailable",
                    specializations=MappingProxyType({}),
                    reason="TimescaleDB returned conflicting relation metadata",
                )
            found[name] = specialization
        return _context(feature, found)


def _context(
    feature: SourceFeature,
    specializations: dict[str, RelationSpecialization],
) -> SchemaRelationContext:
    return SchemaRelationContext(
        timescale_state=feature.state,
        specializations=MappingProxyType(specializations),
        reason=feature.reason,
    )
