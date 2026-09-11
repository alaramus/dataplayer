"""Verified extension routines, types and lockable public views (D120, D123).

A routine is used only when the extension owns it, it lives in the extension's
schema with the exact shape declared by its caller and this role may execute
it. The interval strategy verifies its setter with a query of its own, left in
place because its real-source evidence covers that exact query.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.actions import ActionRefused
from app.adapters.postgres.inspection import PostgresReader


@dataclass(frozen=True)
class RoutineShape:
    name: str
    kind: Literal["f", "p"]
    # Type OIDs as pg_proc.proargtypes prints them; built-in ones do not vary by major.
    argument_types: str
    result_type: int
    defaults: int
    returns_set: bool = False
    # A polymorphic routine can lose resolution to a concrete same-named overload, so it must
    # be alone. A caller that casts every argument to a concrete type may set this False.
    exclusive: bool = True


class ExtensionObject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    oid: str = Field(pattern=r"^[1-9][0-9]{0,9}$")


class ExtensionRoutine(ExtensionObject):
    schema_name: str = Field(min_length=1, max_length=63)


_ROUTINE = """
SELECT routine.oid::text AS oid, namespace.nspname AS schema_name
FROM pg_catalog.pg_proc AS routine
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = routine.pronamespace
JOIN pg_catalog.pg_depend AS dependency
  ON dependency.classid = 'pg_catalog.pg_proc'::pg_catalog.regclass
 AND dependency.objid = routine.oid
 AND dependency.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass
 AND dependency.deptype = 'e'
JOIN pg_catalog.pg_extension AS extension ON extension.oid = dependency.refobjid
WHERE extension.extname = 'timescaledb' AND extension.extversion = %s
  AND routine.pronamespace = extension.extnamespace
  AND routine.proname = %s AND routine.prokind = %s::pg_catalog."char"
  AND routine.proretset = %s
  AND routine.prorettype = %s::pg_catalog.oid
  AND routine.proargtypes = %s::pg_catalog.oidvector
  AND routine.pronargdefaults = %s
  AND pg_catalog.has_schema_privilege(namespace.oid, 'USAGE')
  AND pg_catalog.has_function_privilege(routine.oid, 'EXECUTE')
  AND (NOT %s OR NOT EXISTS (
      SELECT 1 FROM pg_catalog.pg_proc AS overload
      WHERE overload.pronamespace = routine.pronamespace
        AND overload.proname = routine.proname AND overload.oid <> routine.oid
  ))
LIMIT 2
"""

_TYPE = """
SELECT data_type.oid::text AS oid
FROM pg_catalog.pg_type AS data_type
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = data_type.typnamespace
JOIN pg_catalog.pg_depend AS dependency
  ON dependency.classid = 'pg_catalog.pg_type'::pg_catalog.regclass
 AND dependency.objid = data_type.oid
 AND dependency.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass
 AND dependency.deptype = 'e'
JOIN pg_catalog.pg_extension AS extension ON extension.oid = dependency.refobjid
WHERE extension.extname = 'timescaledb' AND extension.extversion = %s
  AND namespace.nspname = %s AND data_type.typname = %s
  AND pg_catalog.has_type_privilege(data_type.oid, 'USAGE')
LIMIT 2
"""

_LOCKABLE_VIEW = """
SELECT relation.oid::text AS oid
FROM pg_catalog.pg_class AS relation
JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace
JOIN pg_catalog.pg_depend AS dependency
  ON dependency.classid = 'pg_catalog.pg_class'::pg_catalog.regclass
 AND dependency.objid = relation.oid
 AND dependency.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass
 AND dependency.deptype = 'e'
JOIN pg_catalog.pg_extension AS extension ON extension.oid = dependency.refobjid
WHERE extension.extname = 'timescaledb' AND extension.extversion = %s
  AND namespace.nspname = 'timescaledb_information'
  AND relation.relname = %s AND relation.relkind = 'v'
  AND pg_catalog.has_table_privilege(relation.oid, 'UPDATE,DELETE,TRUNCATE')
LIMIT 2
"""

_SERVER = "SELECT pg_catalog.current_setting('server_version_num')::integer AS version"


async def extension_routine(
    reader: PostgresReader, version: str, shape: RoutineShape,
) -> ExtensionRoutine:
    rows = await reader.query(_ROUTINE, (
        version, shape.name, shape.kind, shape.returns_set, str(shape.result_type),
        shape.argument_types, shape.defaults, shape.exclusive,
    ), inspection=True)
    if len(rows) != 1:
        raise ActionRefused(
            "not_applicable", f"The TimescaleDB {shape.name} API is not usable by this connection",
        )
    return ExtensionRoutine.model_validate(rows[0])


async def extension_type(reader: PostgresReader, version: str, schema_name: str, type_name: str) -> str:
    """The OID of one extension-owned type this role may use."""
    rows = await reader.query(_TYPE, (version, schema_name, type_name), inspection=True)
    if len(rows) != 1:
        raise ActionRefused("not_applicable", f"The TimescaleDB {type_name} type is not usable by this connection")
    return ExtensionObject.model_validate(rows[0]).oid


async def lockable_view(reader: PostgresReader, version: str, view: str) -> str:
    """The OID of a public view this role may lock in any mode (UPDATE, DELETE or TRUNCATE)."""
    rows = await reader.query(_LOCKABLE_VIEW, (version, view), inspection=True)
    if len(rows) != 1:
        raise ActionRefused("not_applicable", "This connection may not lock TimescaleDB public metadata")
    return ExtensionObject.model_validate(rows[0]).oid


async def require_tested_server(reader: PostgresReader) -> None:
    rows = await reader.query(_SERVER, inspection=True)
    version = rows[0].get("version") if len(rows) == 1 else None
    if not isinstance(version, int) or not 160000 <= version < 170000:
        raise ActionRefused(
            "not_applicable", "TimescaleDB metadata changes are tested only on PostgreSQL 16",
        )
