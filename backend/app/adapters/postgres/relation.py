"""Read complete relation models from PostgreSQL system catalogs."""

from typing import Any, Literal, cast

from app.adapters.postgres.column_type import build_column_type
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import (
    CheckConstraint,
    Column,
    Constraint,
    ExclusionConstraint,
    ForeignKey,
    Index,
    Partitioning,
    PartitionOf,
    Persistence,
    PrimaryKey,
    RefAction,
    RelationKind,
    RelationModel,
    Storage,
    UniqueConstraint,
)

_KINDS: dict[str, RelationKind] = {
    "r": "table",
    "p": "partitioned_table",
    "v": "view",
    "m": "materialized_view",
    "f": "foreign_table",
}
_PERSISTENCE: dict[str, Persistence] = {
    "p": "permanent",
    "u": "unlogged",
    "t": "temporary",
}
_STORAGE: dict[str, Storage] = {
    "p": "plain",
    "m": "main",
    "e": "external",
    "x": "extended",
}
_REF_ACTIONS: dict[str, RefAction] = {
    "a": "no_action",
    "r": "restrict",
    "c": "cascade",
    "n": "set_null",
    "d": "set_default",
}
MatchType = Literal["full", "partial", "simple"]
_MATCH: dict[str, MatchType] = {"f": "full", "p": "partial", "s": "simple"}

_RELATIONS = """
SELECT c.relname AS name,
       c.relkind AS relkind,
       c.relpersistence AS persistence,
       c.reltuples AS row_estimate,
       pg_total_relation_size(c.oid) AS size_bytes,
       pg_get_userbyid(c.relowner) AS owner,
       obj_description(c.oid, 'pg_class') AS comment,
       pt.partstrat AS partition_strategy,
       pg_get_partkeydef(c.oid) AS partition_key,
       parent.relname AS parent_relation,
       pg_get_expr(c.relpartbound, c.oid) AS partition_bounds
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_partitioned_table pt ON pt.partrelid = c.oid
LEFT JOIN pg_inherits inh ON inh.inhrelid = c.oid
LEFT JOIN pg_class parent ON parent.oid = inh.inhparent
WHERE n.nspname = %s
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
"""

_COLUMNS = """
SELECT c.relname AS relation,
       a.attnum AS position,
       a.attname AS name,
       format_type(a.atttypid, a.atttypmod) AS sql_type,
       a.atttypmod AS type_mod,
       t.typcategory AS type_category,
       t.typname AS type_name,
       format_type(t.typelem, a.atttypmod) AS element_sql,
       et.typcategory AS element_category,
       et.typname AS element_name,
       NOT a.attnotnull AS nullable,
       a.attstorage AS storage,
       a.attidentity AS identity,
       a.attgenerated AS generated,
       pg_get_expr(ad.adbin, ad.adrelid) AS default_expression,
       col_description(a.attrelid, a.attnum) AS comment,
       co.collname AS collation,
       (SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder)
          FROM pg_enum e WHERE e.enumtypid = t.oid) AS enum_values,
       (SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder)
          FROM pg_enum e WHERE e.enumtypid = et.oid) AS element_enum_values
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_type t ON t.oid = a.atttypid
LEFT JOIN pg_type et ON et.oid = t.typelem
LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
LEFT JOIN pg_collation co ON co.oid = a.attcollation AND co.collname <> 'default'
WHERE n.nspname = %s
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND a.attnum > 0
  AND NOT a.attisdropped
"""

_CONSTRAINTS = """
SELECT c.relname AS relation,
       con.conname AS name,
       con.contype AS contype,
       (SELECT array_agg(att.attname ORDER BY u.ord)
          FROM unnest(con.conkey) WITH ORDINALITY AS u(attnum, ord)
          JOIN pg_attribute att
            ON att.attrelid = con.conrelid AND att.attnum = u.attnum
       ) AS column_names,
       (SELECT array_agg(att.attname ORDER BY u.ord)
          FROM unnest(con.confkey) WITH ORDINALITY AS u(attnum, ord)
          JOIN pg_attribute att
            ON att.attrelid = con.confrelid AND att.attnum = u.attnum
       ) AS target_column_names,
       fn.nspname AS target_schema,
       fc.relname AS target_relation,
       con.confupdtype AS on_update,
       con.confdeltype AS on_delete,
       con.confmatchtype AS match_type,
       pg_get_expr(con.conbin, con.conrelid) AS expression,
       pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_class fc ON fc.oid = con.confrelid
LEFT JOIN pg_namespace fn ON fn.oid = fc.relnamespace
WHERE n.nspname = %s
  AND con.contype IN ('p', 'u', 'f', 'c', 'x')
"""

_INDEXES = """
SELECT c.relname AS relation,
       ic.relname AS name,
       am.amname AS method,
       ix.indisunique AS is_unique,
       ix.indisprimary AS is_primary,
       ix.indisvalid AS is_valid,
       (SELECT array_agg(att.attname ORDER BY u.ord)
          FROM unnest(string_to_array(ix.indkey::text, ' ')::int[])
               WITH ORDINALITY AS u(attnum, ord)
          JOIN pg_attribute att
            ON att.attrelid = ix.indrelid AND att.attnum = u.attnum
       ) AS column_names,
       pg_get_expr(ix.indpred, ix.indrelid) AS predicate,
       pg_get_indexdef(ix.indexrelid) AS definition
FROM pg_index ix
JOIN pg_class ic ON ic.oid = ix.indexrelid
JOIN pg_class c ON c.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_am am ON am.oid = ic.relam
WHERE n.nspname = %s
"""


class PostgresRelation:
    """Describe relations with set-oriented catalog queries."""

    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    async def relation_model(self, node_id: str) -> RelationModel:
        schema, _, relation = node_id.partition(".")
        if not relation:
            raise ValueError(f'"{node_id}" is not a relation: expected schema.relation')
        models = await self._models(schema, relation)
        if not models:
            raise NodeNotFound(node_id)
        return models[0]

    async def _models(
        self, schema: str, relation: str | None
    ) -> list[RelationModel]:
        relations = await self._query(_RELATIONS, schema, relation, "c.relname")
        if not relations:
            return []

        column_rows = await self._query(_COLUMNS, schema, relation, "c.relname")
        columns: dict[str, list[Column]] = {}
        for row in sorted(column_rows, key=lambda item: int(item["position"])):
            columns.setdefault(str(row["relation"]), []).append(_column(row))

        constraint_rows = await self._query(
            _CONSTRAINTS, schema, relation, "c.relname"
        )
        constraints: dict[str, list[Constraint]] = {}
        for row in constraint_rows:
            built = _constraint(row)
            if built is not None:
                constraints.setdefault(str(row["relation"]), []).append(built)

        index_rows = await self._query(_INDEXES, schema, relation, "c.relname")
        indexes: dict[str, list[Index]] = {}
        for row in index_rows:
            indexes.setdefault(str(row["relation"]), []).append(_index(row))

        return [
            _relation_model(
                schema,
                row,
                columns.get(str(row["name"]), []),
                constraints.get(str(row["name"]), []),
                indexes.get(str(row["name"]), []),
            )
            for row in relations
        ]

    async def _query(
        self, statement: str, schema: str, relation: str | None, column: str
    ) -> list[dict[str, Any]]:
        params: list[Any] = [schema]
        text = statement
        if relation is not None:
            text += f" AND {column} = %s"
            params.append(relation)
        return await self._session.query(text, tuple(params))


def _column(row: dict[str, Any]) -> Column:
    generated = row.get("generated")
    identity = row.get("identity")
    expression = row.get("default_expression")
    identities: dict[str, Literal["always", "by_default"]] = {
        "a": "always",
        "d": "by_default",
    }
    return Column(
        position=int(row["position"]),
        name=str(row["name"]),
        type=build_column_type(row),
        nullable=bool(row["nullable"]),
        storage=_STORAGE.get(str(row["storage"]), "plain"),
        comment=row.get("comment"),
        default=None if generated == "s" else expression,
        generated=expression if generated == "s" else None,
        identity=identities.get(str(identity or "")),
        collation=row.get("collation"),
    )


def _names(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _constraint(row: dict[str, Any]) -> Constraint | None:
    contype = str(row["contype"])
    name = str(row["name"])
    columns = _names(row.get("column_names"))
    if contype == "p":
        return PrimaryKey(name=name, columns=columns)
    if contype == "u":
        definition = str(row.get("definition") or "")
        return UniqueConstraint(
            name=name,
            columns=columns,
            nulls_not_distinct="NULLS NOT DISTINCT" in definition,
        )
    if contype == "f":
        return ForeignKey(
            name=name,
            columns=columns,
            target_node_id=f'{row["target_schema"]}.{row["target_relation"]}',
            target_columns=_names(row.get("target_column_names")),
            on_update=_REF_ACTIONS.get(str(row["on_update"]), "no_action"),
            on_delete=_REF_ACTIONS.get(str(row["on_delete"]), "no_action"),
            match=_MATCH.get(str(row["match_type"]), "simple"),
        )
    if contype == "c":
        return CheckConstraint(
            name=name,
            expression=str(row.get("expression") or ""),
            columns=columns,
        )
    if contype == "x":
        return ExclusionConstraint(
            name=name, expression=str(row.get("definition") or "")
        )
    return None


def _index(row: dict[str, Any]) -> Index:
    return Index(
        name=str(row["name"]),
        method=str(row["method"]),
        unique=bool(row["is_unique"]),
        primary=bool(row["is_primary"]),
        valid=bool(row["is_valid"]),
        columns=_names(row.get("column_names")),
        predicate=row.get("predicate"),
        definition=str(row["definition"]),
    )


def _relation_model(
    schema: str,
    row: dict[str, Any],
    columns: list[Column],
    constraints: list[Constraint],
    indexes: list[Index],
) -> RelationModel:
    name = str(row["name"])
    estimate = row.get("row_estimate")
    strategy = row.get("partition_strategy")
    partitioning = (
        Partitioning(
            strategy=cast(
                Literal["range", "list", "hash"],
                {"r": "range", "l": "list", "h": "hash"}[str(strategy)],
            ),
            key=str(row.get("partition_key") or ""),
        )
        if strategy is not None
        else None
    )
    parent = row.get("parent_relation")
    partition_of = (
        PartitionOf(
            parent_node_id=f"{schema}.{parent}",
            bounds=str(row.get("partition_bounds") or ""),
        )
        if parent is not None
        else None
    )
    return RelationModel(
        node_id=f"{schema}.{name}",
        schema_name=schema,
        name=name,
        kind=_KINDS[str(row["relkind"])],
        owner=str(row["owner"]),
        persistence=_PERSISTENCE.get(str(row["persistence"]), "permanent"),
        comment=row.get("comment"),
        row_estimate=None if estimate is None or estimate < 0 else int(estimate),
        size_bytes=row.get("size_bytes"),
        columns=columns,
        constraints=constraints,
        indexes=indexes,
        partitioning=partitioning,
        partition_of=partition_of,
    )
