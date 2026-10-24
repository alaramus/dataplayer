"""A SQLite relation described in the adapter-neutral model."""

from app.adapters.protocol import NodeNotFound
from app.adapters.relation import (
    CandidateKey,
    CheckConstraint,
    Column,
    Constraint,
    ForeignKey,
    Index,
    PrimaryKey,
    RelationModel,
    UniqueConstraint,
)
from app.adapters.sqlite import ids
from app.adapters.sqlite.inspection import SCHEMA, RelationFacts, read_relation
from app.adapters.sqlite.session import Reading, SqliteSession
from app.core.translation import say


def relation_name(node_id: str) -> str:
    schema, relation = ids.parse(node_id)
    if schema != SCHEMA or not relation:
        raise ValueError(
            say('"{node_id}" is not a relation: expected main.table', node_id=node_id)
        )
    return relation


def _constraints(facts: RelationFacts) -> list[Constraint]:
    constraints: list[Constraint] = []
    for key in facts.keys:
        if key.kind == "PRIMARY KEY":
            constraints.append(PrimaryKey(name=key.name, columns=key.columns))
        elif key.kind == "UNIQUE":
            constraints.append(UniqueConstraint(name=key.name, columns=key.columns))
        elif key.target_table is not None and key.target_columns:
            constraints.append(
                ForeignKey(
                    name=key.name,
                    columns=key.columns,
                    target_node_id=ids.relation_id(key.target_table),
                    target_columns=key.target_columns,
                    on_update=key.on_update,
                    on_delete=key.on_delete,
                )
            )
    constraints.extend(
        CheckConstraint(name=check.name, expression=check.expression) for check in facts.checks
    )
    return constraints


def _indexes(facts: RelationFacts) -> list[Index]:
    return [
        Index(
            name=index.name,
            method="btree",
            unique=index.unique,
            primary=index.origin == "pk",
            columns=index.columns,
            predicate=index.predicate,
            definition=index.definition,
        )
        for index in facts.indexes
    ]


def model_of(node_id: str, facts: RelationFacts) -> RelationModel:
    # Structure is changed in a later slice; until then nothing claims it.
    return RelationModel(
        node_id=node_id,
        schema_name=SCHEMA,
        name=facts.name,
        kind="view" if facts.is_view else "table",
        persistence="permanent",
        row_estimate=facts.row_estimate,
        columns=[
            Column(
                position=column.position,
                name=column.name,
                type=column.type,
                nullable=column.nullable,
                default=column.default,
                identity="by_default" if column.rowid_alias else None,
                generated=column.generated,
                collation=column.collation,
            )
            for column in facts.columns
        ],
        constraints=_constraints(facts),
        indexes=_indexes(facts),
        candidate_keys=[
            CandidateKey(name=key.name, columns=key.columns)
            for key in facts.keys
            if key.kind in ("PRIMARY KEY", "UNIQUE")
        ],
    )


class SqliteRelation:
    def __init__(self, session: SqliteSession) -> None:
        self._session = session

    async def facts(self, node_id: str, *, structure: bool = True) -> RelationFacts:
        name = relation_name(node_id)
        facts = await self._session.inspection(
            lambda reading: read_relation(reading, name, structure=structure)
        )
        if facts is None:
            raise NodeNotFound(node_id)
        return facts

    async def relation_model(self, node_id: str) -> RelationModel:
        return model_of(node_id, await self.facts(node_id))

    async def relation_models_for_nodes(self, node_ids: list[str]) -> list[RelationModel]:
        """Selected relations on one connection, under one clock (D246).

        An id that names no relation is left out; the caller says so.
        """
        wanted: dict[str, str] = {}
        for node_id in node_ids:
            schema, relation = ids.parse(node_id)
            if schema == SCHEMA and relation:
                wanted[relation] = node_id

        def read(reading: Reading) -> list[RelationModel]:
            models: list[RelationModel] = []
            for name, node_id in wanted.items():
                facts = read_relation(reading, name)
                if facts is not None:
                    models.append(model_of(node_id, facts))
            return models

        return await self._session.inspection(read) if wanted else []
