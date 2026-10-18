"""A MySQL relation described in the adapter-neutral model."""

from app.adapters.mysql import ids
from app.adapters.mysql.inspection import RelationFacts, read_relation
from app.adapters.mysql.session import MysqlSession, quoted_name
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
from app.core.translation import say


def relation_parts(node_id: str) -> tuple[str, str]:
    schema, relation = ids.parse(node_id)
    if relation is None:
        raise ValueError(
            say('"{node_id}" is not a relation: expected database.table', node_id=node_id)
        )
    return schema, relation


def _constraints(facts: RelationFacts) -> list[Constraint]:
    constraints: list[Constraint] = []
    for key in facts.keys:
        if key.kind == "PRIMARY KEY":
            constraints.append(PrimaryKey(name=key.name, columns=key.columns))
        elif key.kind == "UNIQUE":
            constraints.append(UniqueConstraint(name=key.name, columns=key.columns))
        elif key.target_table is not None and len(key.columns) == len(key.target_columns):
            constraints.append(
                ForeignKey(
                    name=key.name,
                    columns=key.columns,
                    target_node_id=ids.relation_id(
                        key.target_schema or facts.schema, key.target_table
                    ),
                    target_columns=key.target_columns,
                    on_update=key.on_update,
                    on_delete=key.on_delete,
                )
            )
    for check in facts.checks:
        constraints.append(
            CheckConstraint(
                name=check.name,
                expression=check.expression,
                # A check MySQL was told not to enforce promises nothing.
                validated=check.enforced,
            )
        )
    return constraints


def _indexes(facts: RelationFacts) -> list[Index]:
    table = quoted_name(facts.schema, facts.name)
    indexes: list[Index] = []
    for index in facts.indexes:
        primary = index.name == "PRIMARY"
        if primary:
            head = "PRIMARY KEY"
        else:
            kind = {"fulltext": "FULLTEXT ", "spatial": "SPATIAL "}.get(
                index.method, "UNIQUE " if index.unique else ""
            )
            head = f"CREATE {kind}INDEX {quoted_name(index.name)} ON {table}"
        using = f" USING {index.method.upper()}" if index.method in ("btree", "hash") else ""
        indexes.append(
            Index(
                name=index.name,
                method=index.method,
                unique=index.unique,
                primary=primary,
                columns=index.columns,
                # Written from the catalog in MySQL's own spelling: the server
                # keeps no text of an index the way PostgreSQL does.
                definition=f"{head} ({', '.join(index.parts)}){using}",
            )
        )
    return indexes


def model_of(node_id: str, facts: RelationFacts) -> RelationModel:
    unchangeable = say("Changing the structure of a MySQL relation is not supported yet")
    return RelationModel(
        node_id=node_id,
        schema_name=facts.schema,
        name=facts.name,
        kind="view" if facts.is_view else "table",
        # TEMPORARY tables never appear in information_schema.
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
                # AUTO_INCREMENT takes a value written explicitly as well.
                identity="by_default" if column.auto_increment else None,
                generated=column.generated,
                collation=column.collation,
            )
            for column in facts.columns
        ],
        constraints=_constraints(facts),
        indexes=_indexes(facts),
        column_changes_reason=unchangeable,
        index_changes_reason=unchangeable,
        constraint_changes_reason=unchangeable,
        candidate_keys=[
            CandidateKey(name=key.name, columns=key.columns)
            for key in facts.keys
            if key.kind in ("PRIMARY KEY", "UNIQUE")
        ],
    )


class MysqlRelation:
    def __init__(self, session: MysqlSession) -> None:
        self._session = session

    async def facts(self, node_id: str, *, structure: bool = True) -> RelationFacts:
        schema, relation = relation_parts(node_id)
        facts = await read_relation(self._session, schema, relation, structure=structure)
        if facts is None:
            raise NodeNotFound(node_id)
        return facts

    async def relation_model(self, node_id: str) -> RelationModel:
        return model_of(node_id, await self.facts(node_id))
