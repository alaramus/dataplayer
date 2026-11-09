"""A Cassandra table or materialized view in the adapter-neutral model (D341)."""

from app.adapters.cassandra.inspection import (
    ColumnFacts,
    IndexFacts,
    Inspector,
    RelationFacts,
)
from app.adapters.cassandra.session import ServerProfile, quoted_name
from app.adapters.cassandra.vocabulary import (
    CASSANDRA_COLUMN_TYPE_OPTIONS,
    index_methods,
)
from app.adapters.database_ids import parse
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import Column, Constraint, Index, PrimaryKey, RelationModel
from app.adapters.words import worded_titles
from app.core.translation import say


def relation_parts(node_id: str) -> tuple[str, str]:
    keyspace, relation = parse(node_id)
    if relation is None:
        raise ValueError(
            say(
                '"{node_id}" is not a relation: expected keyspace.table',
                node_id=node_id,
            )
        )
    return keyspace, relation


def key_text(facts: RelationFacts) -> str:
    """`PRIMARY KEY ((a, b), c)` as CQL writes the key of this relation."""
    partition = [quoted_name(column.name) for column in facts.partition_key]
    clustering = [quoted_name(column.name) for column in facts.clustering]
    first = partition[0] if len(partition) == 1 else f"({', '.join(partition)})"
    return f"PRIMARY KEY ({', '.join([first, *clustering])})"


def _comment(column: ColumnFacts) -> str | None:
    if column.kind == "partition_key":
        return say("Partition key")
    if column.kind == "clustering":
        order = "DESC" if column.descending else "ASC"
        return say("Clustering column, {order}", order=order)
    if column.kind == "static":
        return say("Static: one value for the whole partition")
    return None


def _index(index: IndexFacts) -> Index:
    method = (
        index.using.rsplit(".", 1)[-1] if index.kind == "CUSTOM" else index.kind.lower()
    )
    target = index.target
    using = f" USING '{index.using}'" if index.kind == "CUSTOM" and index.using else ""
    return Index(
        name=index.name,
        method=method or "secondary",
        columns=[target] if target and "(" not in target else [],
        definition=f"CREATE INDEX {quoted_name(index.name)} ON ({target}){using}",
    )


def model_of(
    node_id: str, facts: RelationFacts, profile: ServerProfile | None = None
) -> RelationModel:
    """The model; with the server's profile, also what its structure may become (D346)."""
    refused = structure_reason(facts)
    changeable = refused is None and profile is not None
    constraints: list[Constraint] = []
    if facts.primary_key:
        constraints.append(
            PrimaryKey(
                name="PRIMARY KEY",
                columns=[column.name for column in facts.primary_key],
            )
        )
    return RelationModel(
        node_id=node_id,
        schema_name=facts.keyspace,
        name=facts.name,
        kind="materialized_view" if facts.is_view else "table",
        persistence="permanent",
        comment=facts.comment,
        columns=[
            Column(
                position=position,
                name=column.name,
                type=column.type,
                # A key column always has a value; any other may be left out.
                nullable=not column.in_key,
                comment=_comment(column),
            )
            for position, column in enumerate(facts.columns, start=1)
        ],
        constraints=constraints,
        indexes=[_index(index) for index in facts.indexes],
        column_changes_supported=changeable,
        column_changes_reason=refused,
        # No default, no NOT NULL and no change of type in CQL; only a key
        # column is renamed, which the change itself checks.
        column_operations=["add", "drop", "rename"] if changeable else [],
        column_type_options=worded_titles(CASSANDRA_COLUMN_TYPE_OPTIONS)
        if changeable
        else [],
        index_changes_supported=changeable,
        index_changes_reason=refused,
        index_methods=(
            worded_titles(index_methods(profile.scylla, profile.version))
            if changeable and profile is not None
            else []
        ),
        constraint_changes_reason=say(
            "Cassandra has no unique keys and no foreign keys"
        ),
    )


def structure_reason(facts: RelationFacts) -> str | None:
    """Why this relation's structure cannot be changed, or nothing."""
    if facts.is_system:
        return say('"{keyspace}" belongs to the server', keyspace=facts.keyspace)
    if facts.is_virtual:
        return say("A virtual table is the server's own")
    if facts.is_view:
        return say("Only a table's structure can be changed")
    return None


class CassandraRelation:
    def __init__(self, inspector: Inspector) -> None:
        self._inspector = inspector

    async def facts(self, node_id: str) -> RelationFacts:
        keyspace, relation = relation_parts(node_id)
        facts = await self._inspector.relation(keyspace, relation)
        if facts is None:
            raise NodeNotFound(node_id)
        return facts

    async def relation_model(self, node_id: str) -> RelationModel:
        facts = await self.facts(node_id)
        return model_of(node_id, facts, await self._inspector.profile())

    async def relation_models_for_nodes(
        self, node_ids: list[str]
    ) -> list[RelationModel]:
        """Selected relations, a few reads a keyspace (D246).

        An id that names no relation is left out; the caller says so.
        """
        selected: dict[str, dict[str, str]] = {}
        for node_id in node_ids:
            keyspace, relation = parse(node_id)
            if relation:
                selected.setdefault(keyspace, {})[relation] = node_id
        models: list[RelationModel] = []
        for keyspace, wanted in selected.items():
            place = await self._inspector.keyspace(keyspace)
            if place is None:
                continue
            found = await self._inspector.relations(
                keyspace, place[1], names=list(wanted)
            )
            profile = await self._inspector.profile()
            models.extend(
                model_of(wanted[name], facts, profile) for name, facts in found.items()
            )
        return models
