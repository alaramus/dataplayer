"""Planning and creating one designed PostgreSQL table.

One composer, used twice. The plan a person reviews and the statements that run
are produced by the same code from the same definition, so "this is what will
happen" is a fact rather than a claim: a second composer for the preview would
be a second thing to keep in step, and the first time they drifted the review
would be a lie.

Nothing here executes anything to find out whether it would work. Rolled-back
DDL still takes locks and still fires whatever the server hangs off it, which
is not a thing to do while somebody is typing, so D46's rehearsal stays what it
is and this is a plan instead.
"""

import hashlib
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

from psycopg import sql

from app.adapters.catalog import CatalogNode, SchemaNode
from app.adapters.expressions import (
    Arithmetic,
    BooleanGroup,
    Cast,
    ColumnReference,
    Comparison,
    Expression,
    ExpressionContext,
    FunctionCall,
    LiteralValue,
    Membership,
    Negation,
    NullTest,
    referenced_columns,
    too_large,
)
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.design_vocabulary import (
    ARITHMETIC_SQL,
    BARE_FUNCTIONS,
    COLLATIONS,
    COMPARE_SQL,
    DIRECTION_SQL,
    INCLUDE_METHODS,
    MATCH_CHOICES,
    MATCH_SQL,
    NULLS_SQL,
    OPERATOR_CLASSES,
    PARTITION_CHOICES,
    PARTITION_SQL,
    PERSISTENCE_CHOICES,
    POSTGRES_DESIGN_FUNCTIONS,
    POSTGRES_DESIGN_TYPES,
    REFERENCE_ACTION_CHOICES,
    operator_class_options,
    type_sql,
)
from app.adapters.postgres.index_methods import (
    INDEX_METHOD_PROPERTIES,
    POSTGRES_INDEX_METHOD_SQL,
    index_method_options,
)
from app.adapters.postgres.names import NAME_LIMIT_BYTES, name_check
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.timescale.design_create import (
    CreationProblem,
    DraftColumn,
    creation_statements,
    hypertable_offer,
)
from app.adapters.postgres.timescale.design_state import UniqueKey
from app.adapters.relation import IndexMethodOption, RefAction, RelationModel
from app.adapters.specializations import TimescaleHypertable
from app.adapters.table_design import (
    DesignAbilities,
    DesignCheck,
    DesignColumn,
    DesignForeignKey,
    DesignIndex,
    DesignLimits,
    DesignRefused,
    DesignTypeOption,
    DesignUnique,
    ExpressionDefault,
    IdentityGeneration,
    IndexColumnKey,
    IndexExpressionKey,
    LiteralDefault,
    NoGeneration,
    PlannedStatement,
    PlanProblem,
    StoredGeneration,
    TableDefinition,
    TableDesignOptions,
    TablePlan,
    TablePlanRequest,
)
from app.adapters.words import worded_titles
from app.core.translation import N_, say

_relation_name = name_check("relation")
_object_name = name_check("object")
_column_name_rule = name_check("column")

# What a refused creation means, by SQLSTATE. The driver's own text carries the
# statement and the connection string, so none of it is passed on.
CREATE_TABLE_REFUSALS = {
    # duplicate_table: the name is taken by a table, view, index or sequence.
    "42P07": N_("Something with that name is already there"),
    # duplicate_object: an index or a constraint name is taken.
    "42710": N_("Something with that name is already there"),
    # duplicate_column.
    "42701": N_("Two columns cannot have the same name"),
    # insufficient_privilege.
    "42501": N_("This connection may not create a table in that schema"),
    # invalid_schema_name: the schema went away between the plan and the DDL.
    "3F000": N_("That schema is no longer there"),
    # undefined_object: no default operator class for a type and method.
    "42704": N_("That index method does not fit the type of these columns"),
    # invalid_foreign_key: the target has no unique key over those columns.
    "42830": N_("The target relation has no unique key over those columns"),
    # datatype_mismatch: a default, a check or a key that does not fit.
    "42804": N_("A value or a key does not fit the type of its column"),
    # invalid_object_definition, and feature_not_supported, which is where a
    # partitioned table refuses a key that leaves out its partition columns.
    "42P17": N_("The server refused that definition"),
    "0A000": N_("The server does not support that combination"),
    # too_many_columns.
    "54011": N_("That is more columns than the source accepts"),
    # syntax_error is never expected: every fragment is composed here. Named so
    # that a mistake in this module reads as one rather than as a source
    # failure.
    "42601": N_("The composed statement was refused by the server"),
}

# PostgreSQL 15 is where a unique constraint learned to treat nulls as equal.
NULLS_NOT_DISTINCT_SINCE = 150000

# Which of the names a definition wants are taken, asked about the candidates
# rather than by listing the schema: a schema of ten thousand objects is
# ordinary and the question is only ever about one draft's handful.
NAME_LOOKUP = """
SELECT relname AS name
FROM pg_catalog.pg_class
WHERE relnamespace = to_regnamespace(%s) AND relname = ANY(%s)
"""

# Whether two types can be compared at all, asked of the server rather than
# decided from a table of type names kept here. `to_regtype` answers with null
# for a name it does not know instead of failing the whole query, so an
# unfamiliar target type leaves the judgement to the creation itself.
#
# The implicit casts are not a refinement: `=` for varchar is text's operator,
# reached because varchar is implicitly cast to text, and a lookup without them
# refuses a foreign key between two varchar columns. Which is exactly what the
# first version of this query did.
COMPARABLE_TYPES = """
SELECT t.at - 1 AS at,
       to_regtype(t.l) IS NOT NULL AND to_regtype(t.r) IS NOT NULL AS known,
       EXISTS (
           SELECT 1
           FROM pg_catalog.pg_operator o
           WHERE o.oprname = '='
             AND o.oprleft IN (
                 SELECT to_regtype(t.l)::oid
                 UNION ALL
                 SELECT castc.casttarget
                 FROM pg_catalog.pg_cast castc
                 WHERE castc.castsource = to_regtype(t.l)
                   AND castc.castcontext = 'i'
             )
             AND o.oprright IN (
                 SELECT to_regtype(t.r)::oid
                 UNION ALL
                 SELECT castc.casttarget
                 FROM pg_catalog.pg_cast castc
                 WHERE castc.castsource = to_regtype(t.r)
                   AND castc.castcontext = 'i'
             )
       ) AS comparable
FROM unnest(%s::text[], %s::text[]) WITH ORDINALITY AS t(l, r, at)
"""

SERVER_VERSION = "SELECT current_setting('server_version_num') AS version"


ProblemKind = Literal["invalid", "conflict"]


class DesignProblem(Exception):
    """One thing wrong with one object, raised where it is noticed.

    Carried rather than returned so that composing can read as composing: a
    clause is either produced or the reason it cannot be is thrown to whoever
    knows which object is being composed.
    """

    def __init__(
        self,
        message: str,
        *,
        field_name: str | None = None,
        kind: ProblemKind = "invalid",
        object_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.field_name = field_name
        self.kind = kind
        # Which object the editor should select, when it is not the one being
        # composed: a key is composed as part of the table and refused because
        # of one column.
        self.object_id = object_id


@dataclass
class _Draft:
    """What is known about one definition while it is being planned."""

    schema: str
    definition: TableDefinition
    columns: dict[str, DesignColumn]
    methods: dict[str, IndexMethodOption]
    # Operator class names by access method name, empty when no key names one.
    operator_classes: dict[str, set[str]]
    collations: set[str]
    nulls_not_distinct: bool
    # Names the schema already holds, out of the ones this definition wants.
    taken: set[str]
    # Names this definition has claimed so far, so two objects of one draft
    # cannot be given the same one.
    used: set[str] = field(default_factory=set)
    # The name each draft index was given, for a reorder policy that names one.
    index_names: dict[str, str] = field(default_factory=dict)
    problems: list[PlanProblem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def note(
        self,
        message: str,
        *,
        object_id: str | None,
        field_name: str | None = None,
        kind: ProblemKind = "invalid",
    ) -> None:
        self.problems.append(
            PlanProblem(
                object_id=object_id, field=field_name, message=message, kind=kind
            )
        )


class PostgresTableDesign:
    """The three questions a designed table asks of one connection."""

    def __init__(
        self,
        session: PostgresSession,
        catalog: PostgresCatalog,
        relation: PostgresRelation,
    ) -> None:
        self._session = session
        self._catalog = catalog
        self._relation = relation

    async def table_design_options(self, node_id: str) -> TableDesignOptions:
        """What this destination will accept a designed table with."""
        node = await self._destination(node_id)
        if node is None:
            return TableDesignOptions(
                supported=False, reason=say("A table is created in a schema")
            )
        if node.is_system:
            return TableDesignOptions(
                supported=False, reason=say('"{schema}" belongs to the server', schema=node.name)
            )
        reason = await self._catalog.schema_action_reason(
            node.name, include_relations=False
        )
        if reason is not None:
            return TableDesignOptions(supported=False, reason=reason)
        methods = await self._methods()
        classes = await self._session.query(OPERATOR_CLASSES)
        collations = await self._session.query(COLLATIONS)
        return TableDesignOptions(
            supported=True,
            schema_label=node.name,
            types=worded_titles(item.option for item in POSTGRES_DESIGN_TYPES.values()),
            index_methods=methods,
            functions=worded_titles(item.option for item in POSTGRES_DESIGN_FUNCTIONS.values()),
            operator_classes=operator_class_options(
                classes, {method.sql for method in methods}
            ),
            collations=[str(row["name"]) for row in collations],
            reference_actions=worded_titles(REFERENCE_ACTION_CHOICES),
            match_modes=worded_titles(MATCH_CHOICES),
            persistence_options=worded_titles(PERSISTENCE_CHOICES),
            partition_strategies=worded_titles(PARTITION_CHOICES),
            nulls_not_distinct_supported=await self._nulls_not_distinct(),
            hypertable=await hypertable_offer(self._session),
            abilities=DesignAbilities(
                unique_constraints=True,
                foreign_keys=True,
                deferrable_unique=True,
                deferrable_foreign_keys=True,
                index_direction=True,
                index_nulls_order=True,
                index_include=True,
                partial_indexes=True,
                comments=True,
                tablespaces=True,
            ),
            limits=DesignLimits(),
        )

    async def plan_table(self, request: TablePlanRequest) -> TablePlan:
        """What the definition would become, composed and not executed."""
        draft = await self._draft(request.node_id, request.definition)
        statements = await self._statements(draft)
        if draft.problems:
            # No fingerprint over a plan that was never composed: it would be a
            # promise about statements nobody can review.
            return TablePlan(
                revision=request.revision,
                problems=draft.problems,
                warnings=draft.warnings,
            )
        return TablePlan(
            revision=request.revision,
            fingerprint=_fingerprint(request.node_id, statements),
            statements=statements,
            warnings=draft.warnings,
        )

    async def create_table(
        self, node_id: str, definition: TableDefinition, fingerprint: str
    ) -> CatalogNode:
        """Create the reviewed table, or refuse the whole thing.

        Composed again from the definition rather than taken from the plan the
        client holds: statements never travel in a request, so nothing a
        browser sends can become SQL. What the client does carry back is the
        fingerprint of what it reviewed, and a definition that no longer
        composes to those statements — because a target, a name or a server
        setting moved — is refused instead of run.
        """
        plan = await self.plan_table(
            TablePlanRequest(node_id=node_id, definition=definition)
        )
        if plan.problems:
            raise DesignRefused(plan.problems[0])
        if plan.fingerprint != fingerprint:
            raise DesignRefused(
                PlanProblem(
                    kind="conflict",
                    message=say("The plan changed since it was reviewed; look at it again"),
                )
            )
        async with self._session.transaction(refusals=CREATE_TABLE_REFUSALS) as work:
            for statement in plan.statements:
                await work.schema_change(statement.sql)
        path = await self._catalog.path_to(f"{node_id}.{definition.name}")
        return path[-1]

    async def _destination(self, node_id: str) -> SchemaNode | None:
        path = await self._catalog.path_to(node_id)
        node = path[-1]
        return node if isinstance(node, SchemaNode) else None

    async def _methods(self) -> list[IndexMethodOption]:
        return index_method_options(await self._session.query(INDEX_METHOD_PROPERTIES))

    async def _nulls_not_distinct(self) -> bool:
        rows = await self._session.query(SERVER_VERSION)
        try:
            return int(rows[0]["version"]) >= NULLS_NOT_DISTINCT_SINCE
        except (IndexError, KeyError, TypeError, ValueError):
            return False

    async def _draft(self, node_id: str, definition: TableDefinition) -> _Draft:
        """Everything the composer will need, read once.

        Only what this definition actually mentions is read: a draft with no
        operator class and no collation asks about neither, because planning
        happens on every pause in the typing and the two lists are the largest
        answers on offer.
        """
        node = await self._destination(node_id)
        if node is None:
            raise ValueError(say("A table is created in a schema"))
        if node.is_system:
            raise ValueError(say('"{schema}" belongs to the server', schema=node.name))
        reason = await self._catalog.schema_action_reason(
            node.name, include_relations=False
        )
        if reason is not None:
            raise ValueError(reason)
        methods = {method.code: method for method in await self._methods()}
        classes: dict[str, set[str]] = {}
        if _names_an_operator_class(definition):
            for option in operator_class_options(
                await self._session.query(OPERATOR_CLASSES),
                {method.sql for method in methods.values()},
            ):
                classes.setdefault(option.method, set()).add(option.code)
        collations: set[str] = set()
        if any(column.collation is not None for column in definition.columns):
            collations = {
                str(row["name"]) for row in await self._session.query(COLLATIONS)
            }
        nulls_not_distinct = False
        if any(item.nulls_not_distinct for item in definition.unique_constraints):
            nulls_not_distinct = await self._nulls_not_distinct()
        return _Draft(
            schema=node.name,
            definition=definition,
            columns={column.id: column for column in definition.columns},
            methods=methods,
            operator_classes=classes,
            collations=collations,
            nulls_not_distinct=nulls_not_distinct,
            taken=await self._taken_names(node.name, definition),
        )

    async def _taken_names(self, schema: str, definition: TableDefinition) -> set[str]:
        wanted = {definition.name, *_named(definition), *_derivable_names(definition)}
        rows = await self._session.query(NAME_LOOKUP, (schema, sorted(wanted)))
        return {str(row["name"]) for row in rows}

    async def _statements(self, draft: _Draft) -> list[PlannedStatement]:
        """Every statement the definition becomes, in the order they run."""
        definition = draft.definition
        table = sql.Identifier(draft.schema, definition.name)
        _check_name(draft, definition.name, _relation_name, object_id=None)
        if definition.name in draft.taken:
            draft.note(
                say('Something called "{name}" is already in that schema', name=definition.name),
                object_id=None,
                field_name="name",
                kind="conflict",
            )
        _check_columns(draft)
        columns = _column_clauses(draft)
        constraints = await self._constraint_clauses(draft)
        if draft.problems:
            return []

        parts: list[sql.Composable] = [
            sql.SQL("CREATE {}TABLE {} (\n    {}\n)").format(
                sql.SQL("UNLOGGED ")
                if definition.persistence == "unlogged"
                else sql.SQL(""),
                table,
                sql.SQL(",\n    ").join([*columns, *constraints]),
            )
        ]
        if definition.partition is not None:
            parts.append(
                sql.SQL(" PARTITION BY {} ({})").format(
                    PARTITION_SQL[definition.partition.strategy],
                    _column_list(draft, definition.partition.column_ids),
                )
            )
        statements = [
            PlannedStatement(
                object_id=None,
                title=say("Table {name}", name=definition.name),
                sql=sql.Composed(parts).as_string(),
            )
        ]
        statements.extend(_index_statements(draft, table))
        statements.extend(_comment_statements(draft, table))
        if definition.hypertable is not None and not draft.problems:
            statements.extend(await self._hypertable_statements(draft))
        return [] if draft.problems else statements

    async def _hypertable_statements(self, draft: _Draft) -> list[PlannedStatement]:
        """The table made a hypertable and set up, after it and its indexes exist (D207)."""
        definition = draft.definition
        hyper = definition.hypertable
        if hyper is None:
            return []
        columns = {
            column.id: DraftColumn(
                name=column.name, type_code=column.type.code,
                array=column.type.dimensions > 0,
                not_null=column.not_null or isinstance(column.generation, IdentityGeneration),
            )
            for column in definition.columns
        }
        keys = [
            UniqueKey(name=name, columns=tuple(_column_name(draft, item) for item in ids))
            for name, ids in _unique_keys(definition)
        ]
        try:
            planned = await creation_statements(
                self._session, draft.schema, definition.name, hyper, columns, keys, draft.index_names,
            )
        except CreationProblem as problem:
            draft.note(problem.message, object_id=problem.object_id or HYPERTABLE_SECTION, field_name=problem.field)
            return []
        return [PlannedStatement(object_id=HYPERTABLE_SECTION, title=item.title, sql=item.sql) for item in planned]

    async def _constraint_clauses(self, draft: _Draft) -> list[sql.Composable]:
        clauses: list[sql.Composable] = []
        definition = draft.definition
        key = definition.primary_key
        if key is not None:
            try:
                columns = _column_list(draft, key.column_ids, unique_in="primary_key")
                _requires_value(draft, key.column_ids)
                clauses.append(
                    sql.SQL("CONSTRAINT {} PRIMARY KEY ({})").format(
                        sql.Identifier(
                            _derive(draft, key.name, definition.name, "pkey")
                        ),
                        columns,
                    )
                )
            except DesignProblem as problem:
                draft.note(
                    problem.message,
                    object_id=problem.object_id,
                    field_name=problem.field_name or "primary_key",
                    kind=problem.kind,
                )
        for unique in definition.unique_constraints:
            clause = _unique_clause(draft, unique)
            if clause is not None:
                clauses.append(clause)
        for check in definition.checks:
            checked = _check_constraint_clause(draft, check)
            if checked is not None:
                clauses.append(checked)
        for foreign in definition.foreign_keys:
            reference = await self._foreign_clause(draft, foreign)
            if reference is not None:
                clauses.append(reference)
        _check_partition_keys(draft)
        return clauses

    async def _foreign_clause(
        self, draft: _Draft, foreign: DesignForeignKey
    ) -> sql.Composable | None:
        try:
            local = _column_list(draft, foreign.column_ids, unique_in="foreign_key")
            target = await self._target(foreign)
            if draft.definition.hypertable is not None and isinstance(target.specialization, TimescaleHypertable):
                raise DesignProblem(
                    say("TimescaleDB does not allow a foreign key between two hypertables"),
                    field_name="target_node_id",
                )
            _check_candidate_key(foreign, target)
            await self._check_comparable(draft, foreign, target)
            _check_ref_actions(draft, foreign)
            name = _derive(
                draft,
                foreign.name,
                draft.definition.name,
                "fkey",
                parts=[_column_name(draft, column) for column in foreign.column_ids],
            )
            return sql.Composed(
                [
                    sql.SQL(
                        "CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {} ({}) {}"
                    ).format(
                        sql.Identifier(name),
                        local,
                        sql.Identifier(
                            target.schema_name or draft.schema, target.name
                        ),
                        sql.SQL(", ").join(
                            sql.Identifier(column)
                            for column in foreign.target_columns
                        ),
                        MATCH_SQL[foreign.match],
                    ),
                    _action_clause(sql.SQL("ON UPDATE"), foreign.on_update),
                    _action_clause(sql.SQL("ON DELETE"), foreign.on_delete),
                    _deferrable(foreign.deferrable, foreign.initially_deferred),
                ]
            )
        except DesignProblem as problem:
            draft.note(
                problem.message,
                object_id=foreign.id,
                field_name=problem.field_name,
                kind=problem.kind,
            )
            return None

    async def _target(self, foreign: DesignForeignKey) -> RelationModel:
        try:
            return await self._relation.relation_model(foreign.target_node_id)
        except ValueError as exc:
            raise DesignProblem(str(exc), field_name="target_node_id") from None

    async def _check_comparable(
        self, draft: _Draft, foreign: DesignForeignKey, target: RelationModel
    ) -> None:
        """Whether each pair of columns can be compared, asked of the server."""
        pairs: list[tuple[str, str]] = []
        for column_id, target_name in zip(
            foreign.column_ids, foreign.target_columns, strict=True
        ):
            column = draft.columns.get(column_id)
            found = next(
                (item for item in target.columns if item.name == target_name), None
            )
            if column is None or found is None:
                continue
            pairs.append((type_sql(column.type).as_string(), found.type.sql))
        if not pairs:
            return
        rows = await self._session.query(
            COMPARABLE_TYPES,
            ([left for left, _ in pairs], [right for _, right in pairs]),
        )
        for row in rows:
            if bool(row["known"]) and not bool(row["comparable"]):
                at = int(row["at"])
                raise DesignProblem(
                    say(
                        '"{column}" and "{target}" cannot be compared',
                        column=_column_name(draft, foreign.column_ids[at]),
                        target=foreign.target_columns[at],
                    ),
                    field_name="target_columns",
                )


def _names_an_operator_class(definition: TableDefinition) -> bool:
    return any(
        key.operator_class is not None
        for index in definition.indexes
        for key in index.keys
    )


def _named(definition: TableDefinition) -> set[str]:
    """Every name this definition states outright."""
    names = {index.name for index in definition.indexes}
    names.update(item.name for item in definition.unique_constraints)
    names.update(item.name for item in definition.checks)
    names.update(item.name for item in definition.foreign_keys)
    if definition.primary_key is not None:
        names.add(definition.primary_key.name)
    return {name for name in names if name}


def _derivable_names(definition: TableDefinition) -> set[str]:
    """Every name the source might invent, so one query asks about them all.

    The same stems `_derive` composes, which is why both go through `_stem`:
    a name asked about here and a different one composed there would be a
    collision check of the wrong names.
    """
    names = {_stem(definition.name, [], "pkey")}
    for index in definition.indexes:
        names.add(
            _stem(
                definition.name,
                _names_of(
                    definition,
                    [
                        key.column_id
                        for key in index.keys
                        if isinstance(key, IndexColumnKey)
                    ],
                ),
                "idx",
            )
        )
    for unique in definition.unique_constraints:
        names.add(
            _stem(
                definition.name, _names_of(definition, unique.column_ids), "key"
            )
        )
    for foreign in definition.foreign_keys:
        names.add(
            _stem(
                definition.name, _names_of(definition, foreign.column_ids), "fkey"
            )
        )
    if definition.checks:
        names.add(_stem(definition.name, [], "check"))
    return names


def _names_of(definition: TableDefinition, column_ids: Sequence[str]) -> list[str]:
    by_id = {column.id: column.name for column in definition.columns}
    return [by_id[column_id] for column_id in column_ids if column_id in by_id]


def _check_candidate_key(foreign: DesignForeignKey, target: RelationModel) -> None:
    if len(foreign.column_ids) != len(foreign.target_columns):
        raise DesignProblem(
            say("A foreign key names as many columns as it points at"),
            field_name="target_columns",
        )
    if len(set(foreign.target_columns)) != len(foreign.target_columns):
        raise DesignProblem(
            say("A column may be pointed at only once"), field_name="target_columns"
        )
    known = {column.name for column in target.columns}
    for name in foreign.target_columns:
        if name not in known:
            raise DesignProblem(
                say('"{table}" has no column "{column}"', table=target.name, column=name),
                field_name="target_columns",
            )
    # The target says which of its columns may be pointed at; a column called
    # `id` is not itself evidence of a key (D22).
    if not any(
        list(key.columns) == list(foreign.target_columns)
        for key in target.candidate_keys
    ):
        raise DesignProblem(
            say('"{name}" has no unique key over exactly those columns', name=target.name),
            field_name="target_columns",
        )


def _check_ref_actions(draft: _Draft, foreign: DesignForeignKey) -> None:
    """What a referential action would do to a column that must have a value.

    PostgreSQL refuses `SET NULL` on a not-null column only when a row is
    actually deleted, which is a long way from the form where it was chosen.
    `SET DEFAULT` is worse: it is accepted, and then fails on the first delete
    because the default points at nothing.
    """
    for action, where in (
        (foreign.on_delete, "on_delete"),
        (foreign.on_update, "on_update"),
    ):
        if action not in ("set_null", "set_default"):
            continue
        for column_id in foreign.column_ids:
            column = draft.columns.get(column_id)
            if column is None:
                continue
            if action == "set_null" and column.not_null:
                raise DesignProblem(
                    say('"{name}" must have a value, so it cannot be set to null', name=column.name),
                    field_name=where,
                )
            if action == "set_default" and isinstance(column.generation, NoGeneration):
                draft.warnings.append(
                    say('"{name}" has no default, so setting it to one leaves null', name=column.name)
                )


def _unique_clause(draft: _Draft, unique: DesignUnique) -> sql.Composable | None:
    try:
        columns = _column_list(draft, unique.column_ids, unique_in="unique")
        if unique.nulls_not_distinct and not draft.nulls_not_distinct:
            raise DesignProblem(
                say("This server cannot treat nulls as equal in a unique constraint"),
                field_name="nulls_not_distinct",
            )
        name = _derive(
            draft,
            unique.name,
            draft.definition.name,
            "key",
            parts=[_column_name(draft, column) for column in unique.column_ids],
        )
        return sql.Composed(
            [
                sql.SQL("CONSTRAINT {} UNIQUE {}({})").format(
                    sql.Identifier(name),
                    sql.SQL("NULLS NOT DISTINCT ")
                    if unique.nulls_not_distinct
                    else sql.SQL(""),
                    columns,
                ),
                _deferrable(unique.deferrable, unique.initially_deferred),
            ]
        )
    except DesignProblem as problem:
        draft.note(
            problem.message,
            object_id=unique.id,
            field_name=problem.field_name,
            kind=problem.kind,
        )
        return None


def _check_constraint_clause(
    draft: _Draft, check: DesignCheck
) -> sql.Composable | None:
    try:
        body = _expression(draft, check.expression, "check")
        name = _derive(draft, check.name, draft.definition.name, "check")
        return sql.SQL("CONSTRAINT {} CHECK ({})").format(sql.Identifier(name), body)
    except DesignProblem as problem:
        draft.note(
            problem.message,
            object_id=check.id,
            field_name=problem.field_name,
            kind=problem.kind,
        )
        return None


def _column_clauses(draft: _Draft) -> list[sql.Composable]:
    clauses: list[sql.Composable] = []
    for column in draft.definition.columns:
        try:
            clauses.append(_column_clause(draft, column))
        except DesignProblem as problem:
            draft.note(
                problem.message,
                object_id=column.id,
                field_name=problem.field_name,
                kind=problem.kind,
            )
    return clauses


def _column_clause(draft: _Draft, column: DesignColumn) -> sql.Composable:
    try:
        declared = type_sql(column.type)
    except ValueError as exc:
        raise DesignProblem(str(exc), field_name="type") from None
    parts: list[sql.Composable] = [
        sql.SQL("{} {}").format(sql.Identifier(column.name), declared)
    ]
    if column.collation is not None:
        if column.collation not in draft.collations:
            raise DesignProblem(
                say('This server has no collation "{collation}"', collation=column.collation),
                field_name="collation",
            )
        parts.append(sql.SQL(" COLLATE {}").format(sql.Identifier(column.collation)))
    parts.append(_generation_clause(draft, column))
    # An identity column is not-null by construction, and saying it twice reads
    # as though one of the two could be turned off.
    if column.not_null and not isinstance(column.generation, IdentityGeneration):
        parts.append(sql.SQL(" NOT NULL"))
    return sql.Composed(parts)


def _generation_clause(draft: _Draft, column: DesignColumn) -> sql.Composable:
    match column.generation:
        case NoGeneration():
            return sql.SQL("")
        case LiteralDefault(value=value):
            # The same crossing D30 makes: text handed to the driver as a
            # literal and coerced by the column's own type.
            return sql.SQL(" DEFAULT {}").format(sql.Literal(value))
        case ExpressionDefault(expression=expression):
            return sql.SQL(" DEFAULT {}").format(
                _expression(draft, expression, "default")
            )
        case IdentityGeneration() as identity:
            return _identity_clause(column, identity)
        case StoredGeneration(expression=expression):
            return _stored_clause(draft, column, expression)


def _identity_clause(
    column: DesignColumn, identity: IdentityGeneration
) -> sql.Composable:
    if not _type_option(column).identity_supported:
        raise DesignProblem(
            say("Only an integer column can be an identity column"), field_name="generation"
        )
    options: list[sql.Composable] = []
    if identity.start is not None:
        options.append(sql.SQL("START WITH {}").format(sql.Literal(identity.start)))
    if identity.increment is not None:
        options.append(
            sql.SQL("INCREMENT BY {}").format(sql.Literal(identity.increment))
        )
    return sql.Composed(
        [
            sql.SQL(" GENERATED {} AS IDENTITY").format(
                sql.SQL("ALWAYS")
                if identity.generated == "always"
                else sql.SQL("BY DEFAULT")
            ),
            sql.SQL(" ({})").format(sql.SQL(" ").join(options))
            if options
            else sql.SQL(""),
        ]
    )


def _stored_clause(
    draft: _Draft, column: DesignColumn, expression: Expression
) -> sql.Composable:
    body = _expression(draft, expression, "generated")
    referenced = referenced_columns(expression)
    if column.id in referenced:
        raise DesignProblem(
            say("A generated column cannot be computed from itself"), field_name="generation"
        )
    for other in draft.definition.columns:
        if other.id in referenced and isinstance(other.generation, StoredGeneration):
            raise DesignProblem(
                say('A generated column cannot read "{name}", which is generated too', name=other.name),
                field_name="generation",
            )
    return sql.SQL(" GENERATED ALWAYS AS ({}) STORED").format(body)


def _type_option(column: DesignColumn) -> DesignTypeOption:
    known = POSTGRES_DESIGN_TYPES.get(column.type.code)
    if known is None:
        raise DesignProblem(
            say('Unknown column type "{code}"', code=column.type.code), field_name="type"
        )
    return known.option


def _index_statements(draft: _Draft, table: sql.Composable) -> list[PlannedStatement]:
    statements: list[PlannedStatement] = []
    for index in draft.definition.indexes:
        try:
            statements.append(_index_statement(draft, index, table))
        except DesignProblem as problem:
            draft.note(
                problem.message,
                object_id=index.id,
                field_name=problem.field_name,
                kind=problem.kind,
            )
    return statements


def _index_statement(
    draft: _Draft, index: DesignIndex, table: sql.Composable
) -> PlannedStatement:
    method = draft.methods.get(index.method)
    method_sql = POSTGRES_INDEX_METHOD_SQL.get(index.method)
    if method is None or method_sql is None:
        raise DesignProblem(
            say('Unknown index method "{method}"', method=index.method), field_name="method"
        )
    if index.unique and not method.unique_supported:
        raise DesignProblem(
            say("{title} cannot build a unique index", title=method.title), field_name="unique"
        )
    if len(index.keys) > 1 and not method.multi_column_supported:
        raise DesignProblem(
            say("{title} cannot index more than one column", title=method.title), field_name="keys"
        )
    _check_index_is_not_a_key(draft, index)

    keys = [_index_key(draft, method, key) for key in index.keys]
    name = _derive(
        draft,
        index.name,
        draft.definition.name,
        "idx",
        parts=[
            _column_name(draft, key.column_id)
            for key in index.keys
            if isinstance(key, IndexColumnKey)
        ],
    )
    parts: list[sql.Composable] = [
        sql.SQL("CREATE {}INDEX {} ON {} USING {} ({})").format(
            sql.SQL("UNIQUE ") if index.unique else sql.SQL(""),
            sql.Identifier(name),
            table,
            method_sql,
            sql.SQL(", ").join(keys),
        )
    ]
    if index.include_column_ids:
        if index.method not in INCLUDE_METHODS:
            raise DesignProblem(
                say("{title} cannot carry extra columns in an index", title=method.title),
                field_name="include_column_ids",
            )
        covered = {
            key.column_id for key in index.keys if isinstance(key, IndexColumnKey)
        }
        if covered & set(index.include_column_ids):
            raise DesignProblem(
                say("A column is either a key of the index or carried by it, not both"),
                field_name="include_column_ids",
            )
        parts.append(
            sql.SQL(" INCLUDE ({})").format(
                _column_list(draft, index.include_column_ids, unique_in="index")
            )
        )
    if index.predicate is not None:
        parts.append(
            sql.SQL(" WHERE {}").format(
                _expression(draft, index.predicate, "predicate")
            )
        )
    draft.index_names[index.id] = name
    return PlannedStatement(
        object_id=index.id, title=say("Index {name}", name=name), sql=sql.Composed(parts).as_string()
    )


def _check_index_is_not_a_key(draft: _Draft, index: DesignIndex) -> None:
    """An index that repeats a key the table already has.

    A primary or unique constraint builds its own index; a second one over the
    same columns is a copy of it that nobody asked for, kept up to date on
    every write.
    """
    if index.predicate is not None or index.method != "btree":
        return
    plain = [key.column_id for key in index.keys if isinstance(key, IndexColumnKey)]
    if len(plain) != len(index.keys):
        return
    key = draft.definition.primary_key
    if key is not None and list(key.column_ids) == plain:
        raise DesignProblem(
            say("The primary key already indexes those columns"), field_name="keys"
        )
    for unique in draft.definition.unique_constraints:
        if list(unique.column_ids) == plain:
            raise DesignProblem(
                say("A unique constraint already indexes those columns"), field_name="keys"
            )


def _index_key(
    draft: _Draft,
    method: IndexMethodOption,
    key: IndexColumnKey | IndexExpressionKey,
) -> sql.Composable:
    parts: list[sql.Composable] = []
    if isinstance(key, IndexColumnKey):
        parts.append(sql.Identifier(_column_name(draft, key.column_id)))
    else:
        parts.append(
            sql.SQL("({})").format(_expression(draft, key.expression, "index"))
        )
    if key.operator_class is not None:
        if key.operator_class not in draft.operator_classes.get(method.sql, set()):
            raise DesignProblem(
                say('"{operator_class}" is not an operator class of {title}', operator_class=key.operator_class, title=method.title),
                field_name="operator_class",
            )
        parts.append(sql.SQL(" {}").format(sql.Identifier(key.operator_class)))
    if key.direction is not None:
        parts.append(sql.SQL(" {}").format(DIRECTION_SQL[key.direction]))
    if key.nulls is not None:
        parts.append(sql.SQL(" {}").format(NULLS_SQL[key.nulls]))
    return sql.Composed(parts)


def _comment_statements(draft: _Draft, table: sql.Composable) -> list[PlannedStatement]:
    statements: list[PlannedStatement] = []
    definition = draft.definition
    if definition.comment:
        statements.append(
            PlannedStatement(
                object_id=None,
                title=say("Table comment"),
                sql=sql.SQL("COMMENT ON TABLE {} IS {}")
                .format(table, sql.Literal(definition.comment))
                .as_string(),
            )
        )
    for column in definition.columns:
        if not column.comment:
            continue
        statements.append(
            PlannedStatement(
                object_id=column.id,
                title=say("Comment on {name}", name=column.name),
                sql=sql.SQL("COMMENT ON COLUMN {}.{} IS {}")
                .format(table, sql.Identifier(column.name), sql.Literal(column.comment))
                .as_string(),
            )
        )
    return statements


def _check_columns(draft: _Draft) -> None:
    names: set[str] = set()
    for column in draft.definition.columns:
        _check_name(draft, column.name, _column_name_rule, object_id=column.id)
        if column.name in names:
            draft.note(
                say('Two columns cannot both be called "{name}"', name=column.name),
                object_id=column.id,
                field_name="name",
            )
        names.add(column.name)


# The editor's row for the hypertable section, which statements and problems of
# it name in place of a draft object (D207).
HYPERTABLE_SECTION = "hypertable"


def _check_hypertable(draft: _Draft) -> None:
    """What a hypertable cannot also be, and the columns its keys must hold (D207).

    TimescaleDB refuses each of these when the table is converted, in a sentence
    that cannot be relayed; here the object at fault is named instead.
    """
    hyper = draft.definition.hypertable
    if hyper is None:
        return
    if draft.definition.partition is not None:
        draft.note(
            say("A hypertable partitions itself; choose it or declarative partitioning, not both"),
            object_id=None, field_name="partition",
        )
    if draft.definition.persistence == "unlogged":
        draft.note(say("A hypertable cannot be unlogged"), object_id=None, field_name="persistence")
    wanted = [hyper.time_column_id, *(item.column_id for item in hyper.hash_dimensions)]
    key = draft.definition.primary_key
    if key is not None and not set(wanted) <= set(key.column_ids):
        draft.note(
            say("The primary key of a hypertable must hold its time column and every hash column"),
            object_id=None, field_name="primary_key",
        )
    for unique in draft.definition.unique_constraints:
        if not set(wanted) <= set(unique.column_ids):
            draft.note(
                say("A unique constraint on a hypertable must hold its time column and every hash column"),
                object_id=unique.id, field_name="column_ids",
            )
    for index in draft.definition.indexes:
        held = {key.column_id for key in index.keys if isinstance(key, IndexColumnKey)}
        if index.unique and not set(wanted) <= held:
            draft.note(
                say("A unique index on a hypertable must hold its time column and every hash column"),
                object_id=index.id, field_name="keys",
            )


def _unique_keys(definition: TableDefinition) -> list[tuple[str, list[str]]]:
    """Every key of the new table by a display name, with its draft column ids."""
    keys: list[tuple[str, list[str]]] = []
    if definition.primary_key is not None:
        keys.append(("primary key", list(definition.primary_key.column_ids)))
    keys.extend((item.name or "unique constraint", list(item.column_ids)) for item in definition.unique_constraints)
    return keys


def _check_partition_keys(draft: _Draft) -> None:
    """A partitioned table's keys must hold every partition column.

    PostgreSQL refuses this outright, and the refusal names a column in a
    sentence that cannot be relayed. The rule is short enough to state here,
    where the object at fault can be named instead.
    """
    _check_hypertable(draft)
    partition = draft.definition.partition
    if partition is None:
        return
    for column_id in partition.column_ids:
        if column_id not in draft.columns:
            draft.note(
                say("The partition key names a column that is not there"),
                object_id=None,
                field_name="partition",
            )
            return
    wanted = set(partition.column_ids)
    key = draft.definition.primary_key
    if key is not None and not wanted <= set(key.column_ids):
        draft.note(
            say("The primary key of a partitioned table must hold every partition column"),
            object_id=None,
            field_name="primary_key",
        )
    for unique in draft.definition.unique_constraints:
        if not wanted <= set(unique.column_ids):
            draft.note(
                say("A unique constraint on a partitioned table must hold every partition column"),
                object_id=unique.id,
                field_name="column_ids",
            )


def _requires_value(draft: _Draft, column_ids: Sequence[str]) -> None:
    """Every column of a primary key must have a value.

    PostgreSQL would add the NOT NULL itself, silently. Saying so is the point:
    a column that is part of the key and shown as optional is a lie the form
    would be telling.
    """
    for column_id in column_ids:
        column = draft.columns.get(column_id)
        if column is None or isinstance(column.generation, IdentityGeneration):
            continue
        if not column.not_null:
            raise DesignProblem(
                say('"{name}" is part of the primary key, so it must have a value', name=column.name),
                field_name="not_null",
                object_id=column.id,
            )


def _check_name(
    draft: _Draft,
    name: str,
    rule: Callable[[str], str],
    *,
    object_id: str | None,
) -> None:
    try:
        rule(name)
    except ValueError as exc:
        draft.note(str(exc), object_id=object_id, field_name="name")


def _column_name(draft: _Draft, column_id: str) -> str:
    column = draft.columns.get(column_id)
    if column is None:
        raise DesignProblem(say("That names a column which is not there"))
    return column.name


def _column_list(
    draft: _Draft,
    column_ids: Sequence[str],
    *,
    unique_in: Literal["primary_key", "foreign_key", "unique", "index"] | None = None,
) -> sql.Composable:
    if unique_in is not None and len(set(column_ids)) != len(column_ids):
        raise DesignProblem(_repeated_column(unique_in))
    return sql.SQL(", ").join(
        sql.Identifier(_column_name(draft, column_id)) for column_id in column_ids
    )


def _repeated_column(within: Literal["primary_key", "foreign_key", "unique", "index"]) -> str:
    if within == "primary_key":
        return say("A column may appear in a primary key only once")
    if within == "foreign_key":
        return say("A column may appear in a foreign key only once")
    if within == "unique":
        return say("A column may appear in a unique constraint only once")
    return say("A column may appear in an index only once")


_REF_ACTION_SQL: dict[RefAction, sql.SQL] = {
    "restrict": sql.SQL("RESTRICT"),
    "cascade": sql.SQL("CASCADE"),
    "set_null": sql.SQL("SET NULL"),
    "set_default": sql.SQL("SET DEFAULT"),
}


def _action_clause(keyword: sql.SQL, action: RefAction) -> sql.Composable:
    if action == "no_action":
        return sql.SQL("")
    return sql.SQL(" {} {}").format(keyword, _REF_ACTION_SQL[action])


def _deferrable(deferrable: bool, initially_deferred: bool) -> sql.Composable:
    if initially_deferred and not deferrable:
        raise DesignProblem(
            say("A constraint can only start deferred if it is deferrable"),
            field_name="initially_deferred",
        )
    if not deferrable:
        return sql.SQL("")
    if initially_deferred:
        return sql.SQL(" DEFERRABLE INITIALLY DEFERRED")
    return sql.SQL(" DEFERRABLE")


def _expression(
    draft: _Draft, node: Expression, context: ExpressionContext
) -> sql.Composable:
    """One expression, composed for the place it sits in.

    Every branch is a shape of the model rather than a piece of text, so what
    comes out is bounded by what the model can hold: there is no path from a
    string in a request to a fragment of syntax.
    """
    oversized = too_large(node)
    if oversized is not None:
        raise DesignProblem(oversized, field_name="expression")
    return _composed(draft, node, context)


def _composed(
    draft: _Draft, node: Expression, context: ExpressionContext
) -> sql.Composable:
    match node:
        case LiteralValue():
            return _literal(node)
        case ColumnReference():
            if context == "default":
                raise DesignProblem(
                    say("A default cannot read a column of the row being written"),
                    field_name="expression",
                )
            return sql.Identifier(_column_name(draft, node.column_id))
        case FunctionCall():
            return _call(draft, node, context)
        case Comparison():
            return sql.SQL("({} {} {})").format(
                _composed(draft, node.left, context),
                COMPARE_SQL[node.operator],
                _composed(draft, node.right, context),
            )
        case Arithmetic():
            return sql.SQL("({} {} {})").format(
                _composed(draft, node.left, context),
                ARITHMETIC_SQL[node.operator],
                _composed(draft, node.right, context),
            )
        case BooleanGroup():
            joiner = sql.SQL(" AND ") if node.operator == "and" else sql.SQL(" OR ")
            return sql.SQL("({})").format(
                joiner.join(_composed(draft, term, context) for term in node.terms)
            )
        case Negation():
            return sql.SQL("(NOT {})").format(_composed(draft, node.operand, context))
        case NullTest():
            return sql.SQL("({} {})").format(
                _composed(draft, node.operand, context),
                sql.SQL("IS NOT NULL") if node.negated else sql.SQL("IS NULL"),
            )
        case Membership():
            return sql.SQL("({} {} ({}))").format(
                _composed(draft, node.operand, context),
                sql.SQL("NOT IN") if node.negated else sql.SQL("IN"),
                sql.SQL(", ").join(_literal(value) for value in node.values),
            )
        case Cast():
            return _cast(draft, node, context)


def _cast(draft: _Draft, node: Cast, context: ExpressionContext) -> sql.Composable:
    known = POSTGRES_DESIGN_TYPES.get(node.type_code)
    if known is None:
        raise DesignProblem(say('Unknown type "{type_code}"', type_code=node.type_code), field_name="expression")
    return sql.SQL("CAST({} AS {})").format(
        _composed(draft, node.operand, context), known.base
    )


def _call(
    draft: _Draft, node: FunctionCall, context: ExpressionContext
) -> sql.Composable:
    known = POSTGRES_DESIGN_FUNCTIONS.get(node.function)
    if known is None:
        raise DesignProblem(
            say('Unknown function "{function}"', function=node.function), field_name="expression"
        )
    if context not in known.option.contexts:
        raise DesignProblem(
            say("{title} cannot be used there", title=say(known.option.title)), field_name="expression"
        )
    if len(node.arguments) != known.option.arity:
        raise DesignProblem(
            say("{signature} takes {arity} arguments", signature=known.option.signature, arity=known.option.arity),
            field_name="expression",
        )
    if node.function in BARE_FUNCTIONS:
        return known.fragment
    return sql.SQL("{}({})").format(
        known.fragment,
        sql.SQL(", ").join(
            _composed(draft, argument, context) for argument in node.arguments
        ),
    )


def _literal(node: LiteralValue) -> sql.Composable:
    """One value, quoted by the driver rather than pasted into the statement."""
    match node.value_kind:
        case "null":
            return sql.SQL("NULL")
        case "boolean":
            if node.text not in ("true", "false"):
                raise DesignProblem(
                    say("A boolean is true or false"), field_name="expression"
                )
            return sql.Literal(node.text == "true")
        case "number":
            try:
                return sql.Literal(Decimal(node.text))
            except (InvalidOperation, ValueError):
                raise DesignProblem(
                    say('"{text}" is not a number', text=node.text), field_name="expression"
                ) from None
        case "json":
            try:
                json.loads(node.text)
            except ValueError:
                raise DesignProblem(
                    say("That is not a JSON document"), field_name="expression"
                ) from None
            return sql.SQL("{}::jsonb").format(sql.Literal(node.text))
        case "text":
            return sql.Literal(node.text)


def _derive(
    draft: _Draft,
    given: str,
    table: str,
    suffix: str,
    *,
    parts: Iterable[str] = (),
) -> str:
    """The name to use: the one that was typed, or one the source composes.

    An explicit name that is taken is a refusal, never a silent replacement:
    somebody chose it, and creating the object under another name would be
    answering a different request. A derived one is nudged until it is free,
    which is what PostgreSQL itself does.
    """
    if given:
        _object_name(given)
        if given in draft.taken:
            raise DesignProblem(
                say('Something called "{given}" is already there', given=given),
                field_name="name",
                kind="conflict",
            )
        if given in draft.used:
            raise DesignProblem(
                say('This definition already calls something "{given}"', given=given), field_name="name"
            )
        draft.used.add(given)
        return given
    candidate = _stem(table, list(parts), suffix)
    at = 1
    while candidate in draft.taken or candidate in draft.used:
        at += 1
        candidate = _stem(table, list(parts), suffix, at)
    draft.used.add(candidate)
    return candidate


def _stem(table: str, parts: Sequence[str], suffix: str, at: int = 1) -> str:
    """The name PostgreSQL itself would compose, and this source does too."""
    return _fit("_".join([table, *parts, suffix]), at)


def _fit(stem: str, at: int = 1) -> str:
    """A name inside PostgreSQL's 63 bytes, numbered when it is not the first.

    Truncating is safe here and only here: the name was composed rather than
    typed, so nothing is being changed out from under anybody.
    """
    tail = "" if at == 1 else f"_{at}"
    room = NAME_LIMIT_BYTES - len(tail.encode("utf-8"))
    body = stem.encode("utf-8")[:room].decode("utf-8", errors="ignore")
    return f"{body}{tail}"


def _fingerprint(node_id: str, statements: Sequence[PlannedStatement]) -> str:
    """What was reviewed, in one line.

    Over the statements rather than over the definition: two definitions that
    compose to the same statements are the same plan, and a definition that
    composes differently — because the server answered differently about a
    target, a method or a collation — is a different one even when the form
    did not change.
    """
    body = json.dumps(
        {"node": node_id, "statements": [item.sql for item in statements]},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
