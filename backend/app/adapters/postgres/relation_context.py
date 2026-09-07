"""One Timescale-aware classification shared by PostgreSQL operations (D122)."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.adapters.features import FeatureState, SourceFeature
from app.adapters.postgres.dependencies import dependency_scope
from app.adapters.postgres.features import PostgresFeatures
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.names import DEDICATED_SCHEMAS
from app.adapters.protocol import AdapterError
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
UNION ALL
SELECT chunk.chunk_name, 'internal'
FROM timescaledb_information.chunks AS chunk
CROSS JOIN target
WHERE chunk.chunk_schema = target.schema_name
  AND (target.relation_name IS NULL OR chunk.chunk_name = target.relation_name)
UNION ALL
SELECT aggregate.materialization_hypertable_name, 'internal'
FROM timescaledb_information.continuous_aggregates AS aggregate
CROSS JOIN target
WHERE aggregate.materialization_hypertable_schema = target.schema_name
  AND (target.relation_name IS NULL
       OR aggregate.materialization_hypertable_name = target.relation_name)
UNION ALL
SELECT relation.relname, 'internal'
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
JOIN pg_catalog.pg_depend AS dependency
  ON dependency.classid = 'pg_catalog.pg_class'::pg_catalog.regclass
 AND dependency.objid = relation.oid
 AND dependency.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass
 AND dependency.deptype = 'e'
JOIN pg_catalog.pg_extension AS extension ON extension.oid = dependency.refobjid
CROSS JOIN target
WHERE extension.extname = 'timescaledb'
  AND namespace.nspname = target.schema_name
  AND (target.relation_name IS NULL OR relation.relname = target.relation_name)
"""


@dataclass(frozen=True)
class SchemaRelationContext:
    timescale_state: FeatureState
    specializations: Mapping[str, RelationSpecialization]
    reason: str | None = None
    internal_relations: frozenset[str] = frozenset()
    dedicated_schema: bool = False

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
        return self.structured_operations_reason(relation) is None

    def structured_operations_reason(self, relation: str) -> str | None:
        if self.dedicated_schema or relation in self.internal_relations:
            return "TimescaleDB internal relations are read-only"
        specialization = self.specialization_for(relation)
        if specialization is not None:
            return "TimescaleDB relations are read-only in this version"
        if not self.known:
            return self.reason or "TimescaleDB relation status could not be established"
        return None

    def schema_operations_reason(self, *, include_relations: bool = True) -> str | None:
        if self.dedicated_schema:
            return "This schema belongs to TimescaleDB"
        if not self.known:
            return self.reason or "TimescaleDB schema status could not be established"
        if include_relations and (self.specializations or self.internal_relations):
            return "This schema contains protected TimescaleDB relations"
        return None


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
            return _context(feature, {}, schema=schema)

        try:
            rows = await self._session.query(
                _CLASSIFY_SQL, (schema, relation), inspection=True
            )
        except (ValueError, AdapterError) as exc:
            if isinstance(exc, AdapterError) and exc.error_kind in {"auth", "network"}:
                raise
            return SchemaRelationContext(
                timescale_state="unavailable",
                specializations=MappingProxyType({}),
                reason="TimescaleDB relation metadata could not be inspected",
                dedicated_schema=schema in DEDICATED_SCHEMAS,
            )
        found: dict[str, RelationSpecialization] = {}
        internal: set[str] = set()
        for row in rows:
            name = row.get("relation_name")
            kind = row.get("specialization")
            if not isinstance(name, str) or not name:
                return _invalid_context()
            specialization: RelationSpecialization
            if kind == "timescale_hypertable":
                specialization = TimescaleHypertable()
            elif kind == "timescale_continuous_aggregate":
                specialization = TimescaleContinuousAggregate()
            elif kind == "internal":
                internal.add(name)
                continue
            else:
                return _invalid_context()
            if name in found:
                return SchemaRelationContext(
                    timescale_state="unavailable",
                    specializations=MappingProxyType({}),
                    reason="TimescaleDB returned conflicting relation metadata",
                )
            found[name] = specialization
        # Materialisation hypertables can occur in both public inventories.
        for name in internal:
            found.pop(name, None)
        return _context(feature, found, schema=schema, internal=frozenset(internal))

    async def cascade_reason(self, schema: str, relation: str | None) -> str | None:
        feature = (await self._features.timescale()).feature
        if feature.state == "absent":
            return None
        if feature.state != "available":
            return feature.reason or "TimescaleDB dependency status is unknown"
        try:
            scope = await dependency_scope(self._session, schema, relation)
        except (ValueError, AdapterError):
            return "The cascade dependency scope could not be inspected"
        if not scope.complete:
            return "The cascade dependency scope exceeds the inspection limit or is unknown"
        if scope.extension_owned:
            return "This cascade affects TimescaleDB extension objects"
        by_schema: dict[str, set[str]] = {}
        for namespace, name in scope.relations:
            by_schema.setdefault(namespace, set()).add(name)
        for namespace, names in by_schema.items():
            context = await self.schema(namespace)
            if any(context.structured_operations_reason(name) for name in names):
                return "This cascade affects protected or unclassified TimescaleDB relations"
        return None


def _context(
    feature: SourceFeature,
    specializations: dict[str, RelationSpecialization],
    *,
    schema: str,
    internal: frozenset[str] = frozenset(),
) -> SchemaRelationContext:
    return SchemaRelationContext(
        timescale_state=feature.state,
        specializations=MappingProxyType(specializations),
        reason=feature.reason,
        internal_relations=internal,
        dedicated_schema=schema in DEDICATED_SCHEMAS,
    )


def _invalid_context() -> SchemaRelationContext:
    return SchemaRelationContext(
        timescale_state="unavailable",
        specializations=MappingProxyType({}),
        reason="TimescaleDB returned invalid relation metadata",
    )
