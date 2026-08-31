"""Validated PostgreSQL constraint DDL."""

from psycopg import sql

from app.adapters.constraints import (
    ConstraintCreated,
    ConstraintDropped,
    CreateConstraintRequest,
    CreateConstraintResult,
    DropConstraintRequest,
    ForeignKeySpec,
    RepeatingValues,
    UniqueConstraintSpec,
    UnmatchedRows,
)
from app.adapters.postgres.counting import repeating_groups, rows_pointing_nowhere
from app.adapters.postgres.relation import PostgresRelation, qualified, schema_of
from app.adapters.postgres.session import PostgresSession
from app.adapters.relation import Constraint, PrimaryKey, RefAction, RelationModel

# The closed vocabulary of what happens to a referencing row. It is the same
# set the relation model already reports, so nothing new is invented; each is
# written out as a literal fragment rather than composed from the value.
REF_ACTION_SQL: dict[RefAction, sql.SQL] = {
    "no_action": sql.SQL("NO ACTION"),
    "restrict": sql.SQL("RESTRICT"),
    "cascade": sql.SQL("CASCADE"),
    "set_null": sql.SQL("SET NULL"),
    "set_default": sql.SQL("SET DEFAULT"),
}

# What a refused constraint command means, by SQLSTATE. The driver's own text
# names the offending row or key value, so it is never passed on.
CONSTRAINT_REFUSALS = {
    # invalid_foreign_key: the target has no key over exactly those columns.
    "42830": "The target relation has no unique key over those columns",
    # unique_violation: values repeat, found by the build rather than the count.
    "23505": "Some values repeat, so this constraint cannot be added",
    # foreign_key_violation: rows point at nothing, found by the scan.
    "23503": "Some rows point at nothing in the target relation",
    # dependent_objects_still_exist.
    "2BP01": "Another object depends on this constraint",
    # feature_not_supported: the partitioned case, as for an index.
    "0A000": "A unique constraint on a partitioned table must include its "
    "partition key",
    # duplicate_object: a name clash the server resolves for us, normally.
    "42710": "A constraint of that name already exists",
    # datatype_mismatch and undefined_function: the two column lists cannot be
    # compared. Which of the two arrives depends on whether the comparison
    # fails at the constraint or at the count that precedes it.
    "42804": "These columns and the ones they point at cannot be compared",
    "42883": "These columns and the ones they point at cannot be compared",
}


class PostgresConstraints:
    def __init__(self, session: PostgresSession, relation: PostgresRelation) -> None:
        self._session = session
        self._relation = relation

    async def create_constraint(
        self, request: CreateConstraintRequest
    ) -> CreateConstraintResult:
        model = await self._relation.relation_model(request.node_id)
        self._check_supported(model)
        spec = request.constraint
        known = {column.name for column in model.columns}
        for column in spec.columns:
            if column not in known:
                raise ValueError(f'Relation has no column "{column}"')

        before = {constraint.name for constraint in model.constraints}
        if isinstance(spec, UniqueConstraintSpec):
            groups, exact = await repeating_groups(
                self._session, schema_of(model), model.name, spec.columns
            )
            if groups > 0:
                # Nothing was added and nothing was locked: the count is the
                # whole answer, and the caller decides what to do about it.
                return RepeatingValues(groups=groups, exact=exact)
            body = sql.SQL("UNIQUE ({})").format(_columns(spec.columns))
        else:
            target = await self._target(spec)
            rows, exact = await rows_pointing_nowhere(
                self._session,
                schema_of(model),
                model.name,
                spec.columns,
                schema_of(target),
                target.name,
                spec.target_columns,
                CONSTRAINT_REFUSALS,
            )
            if rows > 0:
                return UnmatchedRows(rows=rows, exact=exact)
            body = sql.SQL(
                "FOREIGN KEY ({}) REFERENCES {} ({}) ON UPDATE {} ON DELETE {}"
            ).format(
                _columns(spec.columns),
                qualified(target),
                _columns(spec.target_columns),
                REF_ACTION_SQL[spec.on_update],
                REF_ACTION_SQL[spec.on_delete],
            )

        # No name in the statement, for the reason D39 gives: PostgreSQL
        # derives one from the relation and the columns and makes it unique
        # against the schema, which no client could do without reading the
        # catalog.
        statement = sql.SQL("ALTER TABLE {} ADD {}").format(
            qualified(model), body
        )
        await self._session.schema_change(
            statement.as_string(), refusals=CONSTRAINT_REFUSALS
        )
        return ConstraintCreated(
            name=await self._created_name(request.node_id, before)
        )

    async def drop_constraint(
        self, request: DropConstraintRequest
    ) -> ConstraintDropped:
        model = await self._relation.relation_model(request.node_id)
        self._check_supported(model)
        existing = next(
            (item for item in model.constraints if item.name == request.name), None
        )
        if existing is None:
            raise ValueError(f'Relation has no constraint "{request.name}"')
        self._check_droppable(existing)
        # No CASCADE, the rule D27 set for a column: an outside dependency
        # stops the operation instead of disappearing under it. A foreign key
        # standing on this unique constraint is such a dependency, and it is
        # PostgreSQL that knows about the ones in other schemas.
        statement = sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
            qualified(model),
            sql.Identifier(existing.name),
        )
        await self._session.schema_change(
            statement.as_string(), refusals=CONSTRAINT_REFUSALS
        )
        return ConstraintDropped(name=existing.name)

    async def _target(self, spec: ForeignKeySpec) -> RelationModel:
        """The relation being pointed at, and whether it may be pointed at.

        Its own model answers both: the node id is resolved by the source, and
        the candidate keys it publishes say which column sets PostgreSQL will
        accept as a reference. Checking here rather than letting the server
        refuse buys a message that names the target instead of a code.
        """
        target = await self._relation.relation_model(spec.target_node_id)
        if not any(
            key.columns == spec.target_columns for key in target.candidate_keys
        ):
            raise ValueError(
                f'"{schema_of(target)}.{target.name}" has no unique key over '
                f"those columns"
            )
        return target

    async def _created_name(self, node_id: str, before: set[str]) -> str:
        """Which constraint was just added, since ALTER TABLE reports nothing.

        The relation is read again and the answer is the constraint that was
        not there before. Adding one adds exactly one, so the difference is a
        single name unless somebody else added another at the same instant, and
        then the first by name is taken rather than designed for.
        """
        model = await self._relation.relation_model(node_id)
        added = sorted(
            constraint.name
            for constraint in model.constraints
            if constraint.name not in before
        )
        return added[0] if added else ""

    @staticmethod
    def _check_droppable(constraint: Constraint) -> None:
        """A primary key is not dropped in this round.

        Not because PostgreSQL minds, but because a relation without one
        cannot have its rows edited at all (D25): the handle that versions a
        row is built from the key. Losing that as a side effect of tidying up
        a constraint list is a consequence that needs its own round to state.
        """
        if isinstance(constraint, PrimaryKey):
            raise ValueError(
                "A primary key cannot be dropped here: rows can only be edited "
                "while one exists"
            )

    @staticmethod
    def _check_supported(model: RelationModel) -> None:
        if not model.constraint_changes_supported:
            raise ValueError(
                model.constraint_changes_reason
                or "This relation cannot change constraints"
            )


def _columns(names: list[str]) -> sql.Composed:
    return sql.SQL(", ").join(sql.Identifier(name) for name in names)
