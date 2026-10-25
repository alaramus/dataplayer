"""A ClickHouse relation described in the adapter-neutral model."""

from app.adapters.clickhouse.catalog import is_system_database
from app.adapters.clickhouse.inspection import (
    RelationFacts,
    read_relation,
    read_relations,
)
from app.adapters.clickhouse.session import ClickhouseSession, quoted_name
from app.adapters.clickhouse.vocabulary import (
    CLICKHOUSE_COLUMN_TYPE_OPTIONS,
    CLICKHOUSE_INDEX_METHODS,
)
from app.adapters.database_ids import parse
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import (
    CheckConstraint,
    Column,
    Constraint,
    Index,
    RelationKind,
    RelationModel,
)
from app.adapters.words import worded_titles
from app.core.translation import say


def relation_parts(node_id: str) -> tuple[str, str]:
    schema, relation = parse(node_id)
    if relation is None:
        raise ValueError(
            say('"{node_id}" is not a relation: expected database.table', node_id=node_id)
        )
    return schema, relation


def kind_of(facts: RelationFacts) -> RelationKind:
    if facts.is_materialized:
        return "materialized_view"
    return "view" if facts.is_view else "table"


def _constraints(facts: RelationFacts) -> list[Constraint]:
    # No primary key and no unique one: ClickHouse's PRIMARY KEY orders and
    # finds rows and never refuses one (D269), so it is an index here.
    return [
        CheckConstraint(name=check.name, expression=check.expression, validated=check.enforced)
        for check in facts.checks
    ]


def _indexes(facts: RelationFacts) -> list[Index]:
    indexes: list[Index] = []
    if facts.primary_key:
        indexes.append(
            Index(
                name="PRIMARY KEY",
                method="sparse",
                primary=True,
                columns=facts.key_columns(facts.primary_key),
                definition=f"PRIMARY KEY ({', '.join(facts.primary_key)})",
            )
        )
    for index in facts.indexes:
        indexes.append(
            Index(
                name=index.name,
                method=index.type,
                definition=(
                    f"INDEX {quoted_name(index.name)} {index.expression} "
                    f"TYPE {index.type} GRANULARITY {index.granularity}"
                ),
            )
        )
    return indexes


def structure_reason(facts: RelationFacts) -> str | None:
    """Why this relation's structure cannot be changed, or nothing (D273)."""
    if is_system_database(facts.schema):
        return say('"{schema}" belongs to the server', schema=facts.schema)
    if facts.is_view:
        return say("Only a table's structure can be changed")
    if not facts.engine.endswith("MergeTree"):
        return say(
            "Only a MergeTree table's structure can be changed; this one is {engine}",
            engine=facts.engine,
        )
    return None


def model_of(node_id: str, facts: RelationFacts) -> RelationModel:
    refused = structure_reason(facts)
    changeable = refused is None
    return RelationModel(
        node_id=node_id,
        schema_name=facts.schema,
        name=facts.name,
        kind=kind_of(facts),
        persistence="permanent",
        comment=facts.comment,
        row_estimate=facts.row_estimate,
        size_bytes=facts.size_bytes,
        columns=[
            Column(
                position=column.position,
                name=column.name,
                type=column.type,
                nullable=column.nullable,
                comment=column.comment,
                default=column.default,
                generated=column.generated,
            )
            for column in facts.columns
        ],
        constraints=_constraints(facts),
        indexes=_indexes(facts),
        column_changes_supported=changeable,
        column_changes_reason=refused,
        column_operations=(
            ["add", "drop", "rename", "default", "nullability", "type"] if changeable else []
        ),
        column_type_options=worded_titles(CLICKHOUSE_COLUMN_TYPE_OPTIONS) if changeable else [],
        index_changes_supported=changeable,
        index_changes_reason=refused,
        index_methods=worded_titles(CLICKHOUSE_INDEX_METHODS) if changeable else [],
        # No unique key and no foreign key exist in ClickHouse to be made (D269).
        constraint_changes_reason=say("ClickHouse has no unique keys and no foreign keys"),
    )


class ClickhouseRelation:
    def __init__(self, session: ClickhouseSession) -> None:
        self._session = session

    async def facts(self, node_id: str, *, structure: bool = True) -> RelationFacts:
        schema, relation = relation_parts(node_id)
        facts = await read_relation(self._session, schema, relation, structure=structure)
        if facts is None:
            raise NodeNotFound(node_id)
        return facts

    async def relation_model(self, node_id: str) -> RelationModel:
        return model_of(node_id, await self.facts(node_id))

    async def relation_models_for_nodes(self, node_ids: list[str]) -> list[RelationModel]:
        """Selected relations under one clock, three statements a database (D246).

        An id that names no relation is left out; the caller says so.
        """
        selected: dict[str, dict[str, str]] = {}
        for node_id in node_ids:
            schema, relation = parse(node_id)
            if relation:
                selected.setdefault(schema, {})[relation] = node_id
        models: list[RelationModel] = []
        async with self._session.inspection() as reader:
            for schema, wanted in selected.items():
                found = await read_relations(reader, schema, list(wanted))
                models.extend(model_of(wanted[name], facts) for name, facts in found.items())
        return models
