"""Bounded conservative dependency scope before Timescale cascades (D122)."""

from dataclasses import dataclass

from app.adapters.postgres.session import PostgresSession

MAX_DEPENDENCY_OBJECTS = 1000

# Ignore subobject numbers deliberately: a column dependency protects the
# whole relation. Ownership edges also lead back to their owning objects.
_SCOPE_SQL = """
WITH RECURSIVE target AS (
  SELECT 'pg_catalog.pg_namespace'::regclass::oid AS classid, n.oid AS objid
  FROM pg_catalog.pg_namespace n
  WHERE n.nspname = %s AND %s::text IS NULL
  UNION ALL
  SELECT 'pg_catalog.pg_class'::regclass::oid, c.oid
  FROM pg_catalog.pg_class c
  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = %s AND c.relname = %s
), edges AS (
  SELECT refclassid AS from_class, refobjid AS from_object,
         classid AS to_class, objid AS to_object
  FROM pg_catalog.pg_depend
  UNION ALL
  SELECT classid, objid, refclassid, refobjid
  FROM pg_catalog.pg_depend
  WHERE deptype IN ('a', 'i', 'P', 'S')
), affected(classid, objid) AS (
  SELECT classid, objid FROM target
  UNION
  SELECT edge.to_class, edge.to_object
  FROM affected
  JOIN edges edge
    ON edge.from_class = affected.classid AND edge.from_object = affected.objid
)
SELECT namespace.nspname AS schema_name, relation.relname AS relation_name,
       EXISTS (
         SELECT 1 FROM pg_catalog.pg_depend d
         JOIN pg_catalog.pg_extension e ON e.oid = d.refobjid
         WHERE d.classid = affected.classid AND d.objid = affected.objid
           AND d.refclassid = 'pg_catalog.pg_extension'::regclass
           AND d.deptype = 'e' AND e.extname = 'timescaledb'
       ) AS extension_owned
FROM affected
LEFT JOIN pg_catalog.pg_class relation
  ON affected.classid = 'pg_catalog.pg_class'::regclass
 AND affected.objid = relation.oid
LEFT JOIN pg_catalog.pg_namespace namespace
  ON namespace.oid = relation.relnamespace
  OR (affected.classid = 'pg_catalog.pg_namespace'::regclass
      AND namespace.oid = affected.objid)
LIMIT %s
"""


@dataclass(frozen=True)
class DependencyScope:
    relations: tuple[tuple[str, str], ...]
    extension_owned: bool
    complete: bool


async def dependency_scope(
    session: PostgresSession, schema: str, relation: str | None
) -> DependencyScope:
    rows = await session.query(
        _SCOPE_SQL,
        (schema, relation, schema, relation, MAX_DEPENDENCY_OBJECTS + 1),
        inspection=True,
    )
    relations: list[tuple[str, str]] = []
    owned = False
    for row in rows:
        namespace, name = row.get("schema_name"), row.get("relation_name")
        if not isinstance(row.get("extension_owned"), bool):
            return DependencyScope((), False, False)
        owned = owned or row["extension_owned"]
        if isinstance(namespace, str) and isinstance(name, str):
            relations.append((namespace, name))
    return DependencyScope(
        tuple(relations), owned, bool(rows) and len(rows) <= MAX_DEPENDENCY_OBJECTS
    )
