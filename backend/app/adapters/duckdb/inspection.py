"""What a DuckDB file's catalog says, read through DuckDB's own catalog functions (D389).

Every read is limited to the file's own database: `system` and `temp` are the
engine's, and `information_schema` and `pg_catalog` live in `system`.
"""

from dataclasses import dataclass
from typing import Any

from app.adapters.duckdb.session import Reading
from app.adapters.duckdb.types import build_column_type
from app.adapters.relation import ColumnType

_SCHEMAS = """
SELECT schema_name FROM duckdb_schemas()
WHERE database_name = current_database()
ORDER BY schema_name
"""

# One listing of every relation, and the same filtered to a schema or a name:
# the conditions are fixed text, the values placeholders.
_RELATIONS = """
SELECT * FROM (
  SELECT schema_name, table_name AS name, 'table' AS type, estimated_size, comment, sql
  FROM duckdb_tables()
  WHERE database_name = current_database() AND NOT internal AND NOT temporary
  UNION ALL
  SELECT schema_name, view_name AS name, 'view' AS type, NULL, comment, sql
  FROM duckdb_views()
  WHERE database_name = current_database() AND NOT internal AND NOT temporary
)
"""

_COLUMNS = """
SELECT column_name, column_index, data_type, is_nullable, column_default,
       is_generated, generation_expression, comment
FROM duckdb_columns()
WHERE database_name = current_database() AND schema_name = ? AND table_name = ?
ORDER BY column_index
"""

_CONSTRAINTS = """
SELECT constraint_type, constraint_name, expression, constraint_column_names,
       referenced_table, referenced_column_names
FROM duckdb_constraints()
WHERE database_name = current_database() AND schema_name = ? AND table_name = ?
  AND constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY', 'CHECK')
ORDER BY constraint_index
"""

_INDEXES = """
SELECT index_name, is_unique, is_primary, expressions, sql
FROM duckdb_indexes()
WHERE database_name = current_database() AND schema_name = ? AND table_name = ?
ORDER BY index_name
"""


@dataclass(frozen=True)
class ColumnFacts:
    position: int
    name: str
    type: ColumnType
    nullable: bool
    default: str | None
    generated: str | None
    comment: str | None


@dataclass(frozen=True)
class KeyFacts:
    kind: str
    name: str
    columns: list[str]
    target_table: str | None = None
    target_columns: list[str] | None = None


@dataclass(frozen=True)
class CheckFacts:
    name: str
    expression: str


@dataclass(frozen=True)
class IndexFacts:
    name: str
    unique: bool
    primary: bool
    expressions: str | None
    definition: str | None


@dataclass(frozen=True)
class RelationFacts:
    schema: str
    name: str
    is_view: bool
    row_estimate: int | None
    comment: str | None
    text: str | None
    columns: list[ColumnFacts]
    keys: list[KeyFacts]
    checks: list[CheckFacts]
    indexes: list[IndexFacts]

    @property
    def primary_key(self) -> list[str]:
        for key in self.keys:
            if key.kind == "PRIMARY KEY":
                return key.columns
        return []

    @property
    def foreign_keys(self) -> list[KeyFacts]:
        return [key for key in self.keys if key.kind == "FOREIGN KEY"]

    @property
    def has_rowid(self) -> bool:
        """Whether `rowid` names DuckDB's row number here: a view has none,
        and a column of that name hides it."""
        return not self.is_view and all(column.name.lower() != "rowid" for column in self.columns)


def list_schemas(reading: Reading) -> list[str]:
    return [str(row["schema_name"]) for row in reading.rows(_SCHEMAS)]


def list_relations(reading: Reading, schema: str | None = None) -> list[dict[str, Any]]:
    """Tables and views of one schema, or of every schema."""
    if schema is None:
        return reading.rows(_RELATIONS + " ORDER BY schema_name, name")
    return reading.rows(_RELATIONS + " WHERE schema_name = ? ORDER BY name", [schema])


def find_relation(reading: Reading, schema: str, name: str) -> dict[str, Any] | None:
    found = reading.rows(_RELATIONS + " WHERE schema_name = ? AND name = ?", [schema, name])
    return found[0] if found else None


def _columns(reading: Reading, schema: str, name: str) -> list[ColumnFacts]:
    return [
        ColumnFacts(
            position=int(row["column_index"]),
            name=str(row["column_name"]),
            type=build_column_type(str(row["data_type"])),
            nullable=bool(row["is_nullable"]),
            default=None if row["column_default"] is None else str(row["column_default"]),
            generated=(
                str(row["generation_expression"])
                if row["is_generated"] and row["generation_expression"] is not None
                else None
            ),
            comment=None if row["comment"] is None else str(row["comment"]),
        )
        for row in reading.rows(_COLUMNS, [schema, name])
    ]


def read_relation(
    reading: Reading, schema: str, name: str, *, structure: bool = True
) -> RelationFacts | None:
    """One relation's facts; checks and indexes only when asked for.

    A page needs the columns and the keys; DuckDB names constraints it
    was not told the name of, and drops the name it was told (checked on 2.0.0).
    """
    found = find_relation(reading, schema, name)
    if found is None:
        return None
    is_view = found["type"] == "view"
    keys: list[KeyFacts] = []
    checks: list[CheckFacts] = []
    indexes: list[IndexFacts] = []
    if not is_view:
        for row in reading.rows(_CONSTRAINTS, [schema, name]):
            kind = str(row["constraint_type"])
            constraint = str(row["constraint_name"])
            if kind == "CHECK":
                if structure and row["expression"] is not None:
                    checks.append(CheckFacts(name=constraint, expression=str(row["expression"])))
                continue
            keys.append(
                KeyFacts(
                    kind=kind,
                    name=constraint,
                    columns=[str(column) for column in row["constraint_column_names"]],
                    target_table=(
                        None if row["referenced_table"] is None else str(row["referenced_table"])
                    ),
                    target_columns=[str(column) for column in row["referenced_column_names"] or []]
                    or None,
                )
            )
        if structure:
            indexes = [
                IndexFacts(
                    name=str(row["index_name"]),
                    unique=bool(row["is_unique"]),
                    primary=bool(row["is_primary"]),
                    expressions=None if row["expressions"] is None else str(row["expressions"]),
                    definition=None if row["sql"] is None else str(row["sql"]),
                )
                for row in reading.rows(_INDEXES, [schema, name])
            ]
    estimate = found["estimated_size"]
    return RelationFacts(
        schema=schema,
        name=name,
        is_view=is_view,
        row_estimate=None if estimate is None else int(estimate),
        comment=None if found["comment"] is None else str(found["comment"]),
        text=None if found["sql"] is None else str(found["sql"]),
        columns=_columns(reading, schema, name),
        keys=keys,
        checks=checks,
        indexes=indexes,
    )
