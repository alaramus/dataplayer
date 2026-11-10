"""Planning and creating one designed Cassandra table (D117, D347).

The plan a person reviews and the statements that run come from one composer:
one `CREATE TABLE`, then a `CREATE INDEX` for each secondary index. CQL's key
has two parts the generic designer has not got, so they ride on the one engine
this source offers, "Table": its parameter, the partition key, names the
leading columns of the primary key that form the partition, and the rest of
the primary key are the clustering columns. Left empty, the partition key is
the first column of the primary key, as `PRIMARY KEY (a, b)` means in CQL.

What CQL has not got is a problem beside the object that asks for it: a
unique key, a foreign key, a check, a default, a computed column, a collation,
`NOT NULL` outside the key, a partition by range, list or hash.
"""

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.adapters.cassandra.catalog import CassandraCatalog
from app.adapters.cassandra.inspection import Inspector
from app.adapters.cassandra.session import CassandraSession, quoted_name
from app.adapters.cassandra.vocabulary import index_methods
from app.adapters.catalog import CatalogNode, SchemaNode
from app.adapters.database_ids import parse, relation_id
from app.adapters.table_design import (
    DesignAbilities,
    DesignColumn,
    DesignIndex,
    DesignLimits,
    DesignRefused,
    DesignTypeCategory,
    DesignTypeOption,
    EngineOption,
    EngineParameter,
    HypertableOffer,
    IndexColumnKey,
    NoGeneration,
    PlannedStatement,
    PlanProblem,
    TableDefinition,
    TableDesignOptions,
    TablePlan,
    TablePlanRequest,
)
from app.adapters.words import worded_titles
from app.core.translation import N_, say

# CQL's limit on a table's and an index's name, which are letters, digits and
# underscores; a column's name may be anything, quoted.
NAME_LIMIT = 48
_PLAIN_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")

ENGINE = "table"
PARTITION = "partition"


@dataclass(frozen=True)
class _Type:
    option: DesignTypeOption
    # Whether a column of it may be in the primary key.
    keyed: bool = True


def _type(
    code: str,
    title: str,
    category: DesignTypeCategory,
    *,
    keyed: bool = True,
    array: bool = True,
) -> _Type:
    return _Type(
        DesignTypeOption(
            code=code,
            title=title,
            sql=code,
            array_supported=array,
            identity_supported=False,
            category=category,
        ),
        keyed=keyed,
    )


# Codes are CQL's own type names, and shared with the add-a-column vocabulary.
DESIGN_TYPES: dict[str, _Type] = {
    item.option.code: item
    for item in (
        _type("text", N_("Text"), "text"),
        _type("ascii", N_("ASCII text"), "text"),
        _type("tinyint", N_("Tiny integer"), "number"),
        _type("smallint", N_("Small integer"), "number"),
        _type("int", N_("Integer"), "number"),
        _type("bigint", N_("Big integer"), "number"),
        _type("varint", N_("Integer of any size"), "number"),
        _type("decimal", N_("Decimal"), "number"),
        _type("float", N_("Single precision"), "number"),
        _type("double", N_("Floating point"), "number"),
        _type("boolean", N_("Boolean"), "boolean"),
        _type("date", N_("Date"), "temporal"),
        _type("timestamp", N_("Date and time (UTC)"), "temporal"),
        _type("time", N_("Time of day"), "temporal"),
        _type("uuid", N_("UUID"), "text"),
        _type("timeuuid", N_("Time-based UUID"), "text"),
        _type("inet", N_("IP address"), "other"),
        _type("blob", N_("Bytes"), "other"),
        _type("duration", N_("Duration"), "temporal", keyed=False, array=False),
    )
}


def _engine() -> EngineOption:
    return EngineOption(
        code=ENGINE,
        title=say("Table"),
        description=say(
            "The partition key decides on which node a row is kept; the rest of "
            "the primary key orders the rows inside a partition"
        ),
        sorted=True,
        parameters=[
            EngineParameter(
                code=PARTITION,
                title=say("Partition key"),
                many=True,
                required=False,
                type_codes=[code for code, item in DESIGN_TYPES.items() if item.keyed],
            )
        ],
    )


_TAKEN = "SELECT table_name FROM system_schema.tables WHERE keyspace_name = ?"
_TAKEN_VIEWS = "SELECT view_name FROM system_schema.views WHERE keyspace_name = ?"
_TAKEN_INDEXES = "SELECT index_name FROM system_schema.indexes WHERE keyspace_name = ?"


@dataclass
class _Draft:
    keyspace: str
    definition: TableDefinition
    columns: dict[str, DesignColumn]
    taken: set[str]
    taken_indexes: set[str]
    methods: dict[str, str]
    used: set[str] = field(default_factory=set)
    problems: list[PlanProblem] = field(default_factory=list)

    def problem(
        self, message: str, *, object_id: str | None = None, at: str | None = None
    ) -> None:
        self.problems.append(
            PlanProblem(object_id=object_id, field=at, message=message)
        )


def _text_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class CassandraTableDesign:
    """The three questions a designed table asks of one Cassandra connection."""

    def __init__(
        self, session: CassandraSession, catalog: CassandraCatalog, inspector: Inspector
    ) -> None:
        self._session = session
        self._catalog = catalog
        self._inspector = inspector

    async def _destination(self, node_id: str) -> tuple[SchemaNode | None, str | None]:
        node = (await self._catalog.path_to(node_id))[-1]
        if not isinstance(node, SchemaNode):
            return None, say("A table is created in a keyspace")
        if node.is_system:
            return None, say('"{keyspace}" belongs to the server', keyspace=node.name)
        return node, None

    async def table_design_options(self, node_id: str) -> TableDesignOptions:
        node, reason = await self._destination(node_id)
        if node is None:
            return TableDesignOptions(supported=False, reason=reason)
        profile = await self._inspector.profile()
        return TableDesignOptions(
            supported=True,
            schema_label=node.name,
            types=worded_titles(item.option for item in DESIGN_TYPES.values()),
            index_methods=worded_titles(index_methods(profile.scylla, profile.version)),
            hypertable=HypertableOffer(offered=False),
            engines=[_engine()],
            abilities=DesignAbilities(comments=True),
            limits=DesignLimits(name_bytes=NAME_LIMIT),
        )

    async def plan_table(self, request: TablePlanRequest) -> TablePlan:
        draft = await self._draft(request.node_id, request.definition)
        statements = _statements(draft)
        if draft.problems:
            return TablePlan(revision=request.revision, problems=draft.problems)
        return TablePlan(
            revision=request.revision,
            fingerprint=_fingerprint(request.node_id, statements),
            statements=statements,
        )

    async def create_table(
        self, node_id: str, definition: TableDefinition, fingerprint: str
    ) -> CatalogNode:
        """Create the reviewed table, composed again rather than taken from the client."""
        plan = await self.plan_table(
            TablePlanRequest(node_id=node_id, definition=definition)
        )
        if plan.problems:
            raise DesignRefused(plan.problems[0])
        if plan.fingerprint != fingerprint:
            raise DesignRefused(
                PlanProblem(
                    kind="conflict",
                    message=say(
                        "The plan changed since it was reviewed; look at it again"
                    ),
                )
            )
        for statement in plan.statements:
            await self._session.page(statement.sql, wait_seconds=120)
        keyspace, _ = parse(node_id)
        return (await self._catalog.path_to(relation_id(keyspace, definition.name)))[-1]

    async def _draft(self, node_id: str, definition: TableDefinition) -> _Draft:
        node, reason = await self._destination(node_id)
        if node is None:
            raise ValueError(reason)
        taken = {
            str(row["table_name"])
            for row in await self._session.query(_TAKEN, [node.name])
        }
        taken |= {
            str(row["view_name"])
            for row in await self._session.query(_TAKEN_VIEWS, [node.name])
        }
        indexes = {
            str(row["index_name"])
            for row in await self._session.query(_TAKEN_INDEXES, [node.name])
        }
        profile = await self._inspector.profile()
        return _Draft(
            keyspace=node.name,
            definition=definition,
            columns={column.id: column for column in definition.columns},
            taken=taken,
            taken_indexes=indexes,
            methods={
                option.code: option.sql
                for option in index_methods(profile.scylla, profile.version)
            },
        )


def _plain_name(name: str) -> bool:
    return len(name) <= NAME_LIMIT and _PLAIN_NAME.fullmatch(name) is not None


def _statements(draft: _Draft) -> list[PlannedStatement]:
    definition = draft.definition
    if not _plain_name(definition.name):
        draft.problem(
            say(
                "A table's name is letters, digits and underscores, starting with a letter, "
                "at most {limit}",
                limit=NAME_LIMIT,
            ),
            at="name",
        )
    elif definition.name in draft.taken:
        draft.problems.append(
            PlanProblem(
                field="name",
                kind="conflict",
                message=say(
                    'Something called "{name}" is already in that keyspace',
                    name=definition.name,
                ),
            )
        )
    for refused, where in (
        (definition.persistence != "permanent", "persistence"),
        (definition.partition is not None, "partition"),
        (definition.hypertable is not None, "hypertable"),
    ):
        if refused:
            draft.problem(say(_OUTSIDE[where]), at=where)
    for unique in definition.unique_constraints:
        draft.problem(say("Cassandra has no unique keys"), object_id=unique.id)
    for foreign in definition.foreign_keys:
        draft.problem(say("Cassandra has no foreign keys"), object_id=foreign.id)
    for check in definition.checks:
        draft.problem(say("Cassandra has no checks"), object_id=check.id)
    key = _key(draft)
    lines = _column_lines(draft, set(key))
    if key:
        lines.append(_key_line(draft, key))
    indexes = [_index_statement(draft, index) for index in definition.indexes]
    if draft.problems:
        return []
    statement = (
        f"CREATE TABLE {quoted_name(draft.keyspace, definition.name)} (\n    "
        + ",\n    ".join(lines)
        + "\n)"
    )
    if definition.comment:
        statement += f" WITH comment = {_text_literal(definition.comment)}"
    planned = [
        PlannedStatement(title=say("Table {name}", name=definition.name), sql=statement)
    ]
    planned += [item for item in indexes if item is not None]
    return planned


_OUTSIDE = {
    "persistence": N_("A Cassandra table is written to disk; there is no unlogged one"),
    "partition": N_(
        "A Cassandra table is partitioned by its partition key, not by range, list or hash"
    ),
    "hypertable": N_("A hypertable is TimescaleDB's, not Cassandra's"),
}


def _key(draft: _Draft) -> list[str]:
    """The primary key's column ids, checked; empty with a problem when there is none."""
    key = draft.definition.primary_key
    if key is None:
        draft.problem(say("A Cassandra table needs a primary key"), at="primary_key")
        return []
    for column_id in key.column_ids:
        column = draft.columns.get(column_id)
        if column is None:
            draft.problem(
                say("That names a column which is not there"), at="primary_key"
            )
            return []
        known = DESIGN_TYPES.get(column.type.code)
        if known is not None and (not known.keyed or column.type.dimensions):
            draft.problem(
                say('"{name}" has a type a primary key cannot hold', name=column.name),
                object_id=column.id,
                at="type",
            )
    return list(key.column_ids)


def _partition(draft: _Draft, key: list[str]) -> list[str]:
    """The partition key: the leading columns of the primary key the engine names."""
    asked = draft.definition.engine
    if asked is not None and asked.code != ENGINE:
        draft.problem(
            say('Cassandra does not offer "{engine}" here', engine=asked.code),
            at="engine",
        )
        return key[:1]
    chosen: list[str] = []
    for argument in asked.arguments if asked is not None else []:
        if argument.code != PARTITION:
            draft.problem(say("That names a column which is not there"), at="engine")
            continue
        chosen = list(argument.column_ids)
    if not chosen:
        return key[:1]
    if set(chosen) != set(key[: len(chosen)]):
        draft.problem(
            say("The partition key is the leading columns of the primary key"),
            at="engine",
        )
        return key[:1]
    return key[: len(chosen)]


def _key_line(draft: _Draft, key: list[str]) -> str:
    partition = _partition(draft, key)
    names = [quoted_name(draft.columns[column_id].name) for column_id in key]
    head = (
        names[0]
        if len(partition) == 1
        else "(" + ", ".join(names[: len(partition)]) + ")"
    )
    return "PRIMARY KEY (" + ", ".join([head, *names[len(partition) :]]) + ")"


def _column_lines(draft: _Draft, keyed: set[str]) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for column in draft.definition.columns:
        if column.name in seen:
            draft.problem(
                say('Two columns cannot both be called "{name}"', name=column.name),
                object_id=column.id,
                at="name",
            )
        seen.add(column.name)
        known = DESIGN_TYPES.get(column.type.code)
        if known is None:
            draft.problem(
                say('Unknown column type "{code}"', code=column.type.code),
                object_id=column.id,
                at="type",
            )
            continue
        if (
            column.type.length is not None
            or column.type.precision is not None
            or column.type.scale is not None
        ):
            draft.problem(
                say(
                    "{title} takes no length, precision or scale",
                    title=say(known.option.title),
                ),
                object_id=column.id,
                at="type",
            )
        if column.type.dimensions > 1 or (
            column.type.dimensions and not known.option.array_supported
        ):
            draft.problem(
                say(
                    "{title} cannot be held in a list here",
                    title=say(known.option.title),
                ),
                object_id=column.id,
                at="type",
            )
        if not isinstance(column.generation, NoGeneration):
            draft.problem(
                say("Cassandra has no defaults and no computed columns"),
                object_id=column.id,
                at="generation",
            )
        if column.collation:
            draft.problem(
                say("Cassandra has no collations"), object_id=column.id, at="collation"
            )
        if column.not_null and column.id not in keyed:
            draft.problem(
                say("Only a column of the primary key always has a value"),
                object_id=column.id,
                at="not_null",
            )
        type_text = (
            f"list<{known.option.sql}>" if column.type.dimensions else known.option.sql
        )
        lines.append(f"{quoted_name(column.name)} {type_text}")
    return lines


def _index_statement(draft: _Draft, index: DesignIndex) -> PlannedStatement | None:
    if index.unique:
        draft.problem(say("A Cassandra index cannot be unique"), object_id=index.id)
        return None
    if index.predicate is not None or index.include_column_ids:
        draft.problem(
            say("A Cassandra index covers one column and nothing else"),
            object_id=index.id,
        )
        return None
    if len(index.keys) != 1 or not isinstance(index.keys[0], IndexColumnKey):
        draft.problem(say("A Cassandra index covers one column"), object_id=index.id)
        return None
    using = draft.methods.get(index.method)
    if using is None:
        draft.problem(
            say("Unknown index method: {method}", method=index.method),
            object_id=index.id,
        )
        return None
    column = draft.columns.get(index.keys[0].column_id)
    if column is None:
        draft.problem(say("That names a column which is not there"), object_id=index.id)
        return None
    name = index.name or _derived(draft, column.name)
    if not _plain_name(name) or name in draft.taken_indexes or name in draft.used:
        draft.problem(
            say('An index cannot be called "{name}" here', name=name),
            object_id=index.id,
            at="name",
        )
        return None
    draft.used.add(name)
    sql = (
        f"CREATE INDEX {quoted_name(name)} ON "
        f"{quoted_name(draft.keyspace, draft.definition.name)} ({quoted_name(column.name)})"
    )
    if using:
        sql += f" USING '{using}'"
    return PlannedStatement(
        object_id=index.id, title=say("Index {name}", name=name), sql=sql
    )


def _derived(draft: _Draft, column: str) -> str:
    plain = "".join(char if char.isalnum() or char == "_" else "_" for char in column)
    stem = f"{draft.definition.name}_{plain}"[: NAME_LIMIT - 8].strip("_")
    candidate = f"{stem}_idx"
    number = 2
    while candidate in draft.taken_indexes or candidate in draft.used:
        candidate = f"{stem}_idx{number}"
        number += 1
    return candidate


def _fingerprint(node_id: str, statements: Sequence[PlannedStatement]) -> str:
    body = json.dumps(
        {"node": node_id, "statements": [item.sql for item in statements]},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
