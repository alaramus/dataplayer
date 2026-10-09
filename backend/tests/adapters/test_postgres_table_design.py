"""Planning and creating a designed table, against a real server."""

from collections.abc import AsyncGenerator
from typing import Any

import pytest

from app.adapters.actions import ActionRefused, ActionResult
from app.adapters.hypertable_design import DesignDuration
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.relation import ForeignKey, PrimaryKey, RelationModel
from app.adapters.table_design import (
    DesignCheck,
    DesignColumn,
    DesignColumnType,
    DesignForeignKey,
    DesignIndex,
    DesignPartition,
    DesignPrimaryKey,
    DesignUnique,
    ExpressionDefault,
    IdentityGeneration,
    IndexColumnKey,
    LiteralDefault,
    TableDefinition,
    TableHypertable,
    TablePlanRequest,
)
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


def _column(
    column_id: str, name: str, code: str, **rest: Any
) -> DesignColumn:
    return DesignColumn(id=column_id, name=name, type=DesignColumnType(code=code), **rest)


def _literal(value_kind: str, text: str) -> dict[str, str]:
    return {"kind": "literal", "value_kind": value_kind, "text": text}


def _orders() -> TableDefinition:
    """The reference table of the design: keys, checks, defaults and indexes."""
    return TableDefinition.model_validate(
        {
            "name": "orders",
            "comment": "Customer orders",
            "columns": [
                {
                    "id": "c1",
                    "name": "id",
                    "type": {"code": "bigint"},
                    "not_null": True,
                    "generation": {"kind": "identity", "generated": "always"},
                },
                {
                    "id": "c2",
                    "name": "order_number",
                    "type": {"code": "varchar", "length": 40},
                    "not_null": True,
                },
                {"id": "c3", "name": "customer_id", "type": {"code": "integer"}},
                {
                    "id": "c4",
                    "name": "status",
                    "type": {"code": "text"},
                    "not_null": True,
                    "generation": {"kind": "literal", "value": "new"},
                },
                {
                    "id": "c5",
                    "name": "total",
                    "type": {"code": "numeric", "precision": 10, "scale": 2},
                    "not_null": True,
                },
                {
                    "id": "c6",
                    "name": "payload",
                    "type": {"code": "jsonb"},
                    "comment": "Whatever the shop sent",
                },
                {
                    "id": "c7",
                    "name": "created",
                    "type": {"code": "timestamp_tz"},
                    "not_null": True,
                    "generation": {
                        "kind": "expression",
                        "expression": {"kind": "call", "function": "now"},
                    },
                },
            ],
            "primary_key": {"column_ids": ["c1"]},
            "unique_constraints": [{"id": "u1", "column_ids": ["c2"]}],
            "checks": [
                {
                    "id": "k1",
                    "expression": {
                        "kind": "in",
                        "operand": {"kind": "column", "column_id": "c4"},
                        "values": [
                            _literal("text", "new"),
                            _literal("text", "paid"),
                            _literal("text", "shipped"),
                        ],
                    },
                },
                {
                    "id": "k2",
                    "expression": {
                        "kind": "compare",
                        "operator": "gte",
                        "left": {"kind": "column", "column_id": "c5"},
                        "right": _literal("number", "0"),
                    },
                },
            ],
            "indexes": [
                {
                    "id": "i1",
                    "method": "btree",
                    "keys": [
                        {"kind": "column", "column_id": "c4"},
                        {"kind": "column", "column_id": "c7", "direction": "desc"},
                    ],
                    "include_column_ids": ["c5"],
                    "predicate": {
                        "kind": "compare",
                        "operator": "ne",
                        "left": {"kind": "column", "column_id": "c4"},
                        "right": _literal("text", "shipped"),
                    },
                },
                {
                    "id": "i2",
                    "name": "orders_lower_number_idx",
                    "method": "btree",
                    "keys": [
                        {
                            "kind": "expression",
                            "expression": {
                                "kind": "call",
                                "function": "lower",
                                "arguments": [{"kind": "column", "column_id": "c2"}],
                            },
                        }
                    ],
                },
            ],
        }
    )


def _with_customer_key(schema: str) -> TableDefinition:
    definition = _orders()
    definition.foreign_keys = [
        DesignForeignKey(
            id="f1",
            column_ids=["c3"],
            target_node_id=f"{schema}.customers",
            target_columns=["id"],
            on_delete="restrict",
        )
    ]
    return definition


async def _exists(schema: str, name: str) -> bool:
    adapter = _adapter()
    children = await adapter.list_children(schema)
    return any(node.name == name for node in children)


async def _plan(schema: str, definition: TableDefinition) -> Any:
    return await _adapter().plan_table(
        TablePlanRequest(node_id=schema, definition=definition)
    )


async def _run(
    adapter: PostgresAdapter,
    schema: str,
    definition: TableDefinition,
    fingerprint: str,
) -> ActionResult:
    """Create it the way a client does: through the registered action."""
    action = adapter.action("create_table")
    return await action.perform(
        schema,
        {
            "definition": definition.model_dump(mode="json"),
            "fingerprint": fingerprint,
        },
    )


async def _create(schema: str, definition: TableDefinition) -> RelationModel:
    adapter = _adapter()
    plan = await adapter.plan_table(
        TablePlanRequest(node_id=schema, definition=definition)
    )
    assert plan.problems == [], plan.problems
    result = await _run(adapter, schema, definition, plan.fingerprint)
    assert result.created_node_id is not None
    assert result.reload_node_ids == [schema]
    return await adapter.relation_model(result.created_node_id)


async def test_a_schema_publishes_the_vocabulary_this_server_has(
    schema: str,
) -> None:
    options = await _adapter().table_design_options(schema)

    assert options.supported is True
    assert options.schema_label == schema
    types = {option.code: option for option in options.types}
    assert types["varchar"].parameters == ["length"]
    assert types["bigint"].identity_supported is True
    assert types["text"].identity_supported is False
    assert {method.code for method in options.index_methods} >= {"btree", "gin"}
    functions = {option.code: option for option in options.functions}
    # `now()` fills a column and cannot index one: an index expression must be
    # immutable, and the server is what says so.
    assert functions["now"].contexts == ["default"]
    assert "index" in functions["lower"].contexts
    assert any(
        option.code == "jsonb_path_ops" and option.method == "gin"
        for option in options.operator_classes
    )


async def test_a_system_schema_says_why_it_will_take_nothing() -> None:
    options = await _adapter().table_design_options("pg_catalog")

    assert options.supported is False
    assert options.reason == '"pg_catalog" belongs to the server'
    assert options.types == []


async def test_planning_composes_the_statements_and_creates_nothing(
    schema: str,
) -> None:
    plan = await _plan(schema, _with_customer_key(schema))

    assert plan.problems == []
    assert plan.fingerprint != ""
    create = plan.statements[0]
    assert create.object_id is None
    assert f'CREATE TABLE "{schema}"."orders"' in create.sql
    assert '"id" bigint GENERATED ALWAYS AS IDENTITY' in create.sql
    assert '"order_number" varchar(40) NOT NULL' in create.sql
    assert "CONSTRAINT \"orders_pkey\" PRIMARY KEY (\"id\")" in create.sql
    assert '"status" text DEFAULT \'new\' NOT NULL' in create.sql
    assert '"created" timestamp with time zone DEFAULT now() NOT NULL' in create.sql
    assert "CHECK ((\"status\" IN ('new', 'paid', 'shipped')))" in create.sql
    assert (
        f'REFERENCES "{schema}"."customers" ("id") MATCH SIMPLE ON DELETE RESTRICT'
        in create.sql
    )
    index = next(item for item in plan.statements if item.object_id == "i1")
    assert 'CREATE INDEX "orders_status_created_idx"' in index.sql
    assert '("status", "created" DESC) INCLUDE ("total")' in index.sql
    assert "WHERE (\"status\" <> 'shipped')" in index.sql
    # Nothing ran: a plan is not a rehearsal.
    assert await _exists(schema, "orders") is False


async def test_the_reviewed_plan_is_what_the_server_ends_up_holding(
    schema: str,
) -> None:
    model = await _create(schema, _with_customer_key(schema))

    assert model.comment == "Customer orders"
    columns = {column.name: column for column in model.columns}
    assert columns["id"].identity == "always"
    assert columns["id"].nullable is False
    assert columns["order_number"].type.sql == "character varying(40)"
    assert columns["total"].type.sql == "numeric(10,2)"
    assert columns["created"].default == "now()"
    assert columns["payload"].comment == "Whatever the shop sent"
    key = next(item for item in model.constraints if isinstance(item, PrimaryKey))
    assert key.columns == ["id"]
    foreign = next(item for item in model.constraints if isinstance(item, ForeignKey))
    assert foreign.target_columns == ["id"]
    assert foreign.on_delete == "restrict"
    checks = sorted(
        item.expression for item in model.constraints if item.kind == "check"
    )
    assert any("total" in expression for expression in checks)
    indexes = {index.name: index for index in model.indexes}
    assert indexes["orders_status_created_idx"].predicate is not None
    assert "lower" in indexes["orders_lower_number_idx"].definition


async def test_the_same_plan_cannot_be_created_twice(schema: str) -> None:
    definition = _with_customer_key(schema)
    await _create(schema, definition)
    adapter = _adapter()
    plan = await adapter.plan_table(
        TablePlanRequest(node_id=schema, definition=definition)
    )

    assert [problem.kind for problem in plan.problems] == ["conflict"]
    assert plan.fingerprint == ""
    with pytest.raises(ActionRefused) as refused:
        await _run(adapter, schema, definition, "anything")
    assert refused.value.reason == "conflict"


async def test_a_plan_that_moved_on_is_refused_rather_than_run(
    schema: str,
) -> None:
    """What was reviewed is what runs, or nothing does."""
    definition = _orders()
    adapter = _adapter()
    plan = await adapter.plan_table(
        TablePlanRequest(node_id=schema, definition=definition)
    )
    definition.columns[3].name = "state"

    with pytest.raises(ActionRefused) as refused:
        await _run(adapter, schema, definition, plan.fingerprint)
    assert refused.value.reason == "conflict"
    assert await _exists(schema, "orders") is False


async def test_a_key_column_that_may_be_empty_is_named(schema: str) -> None:
    definition = _orders()
    definition.columns[0].generation = LiteralDefault(value="1")
    definition.columns[0].not_null = False

    plan = await _plan(schema, definition)

    assert [problem.message for problem in plan.problems] == [
        '"id" is part of the primary key, so it must have a value'
    ]


async def test_a_default_cannot_read_the_row_it_is_writing(schema: str) -> None:
    definition = _orders()
    definition.columns[3].generation = ExpressionDefault.model_validate(
        {
            "kind": "expression",
            "expression": {"kind": "column", "column_id": "c2"},
        }
    )

    plan = await _plan(schema, definition)

    assert plan.problems[0].object_id == "c4"
    assert plan.problems[0].field == "expression"


async def test_a_function_nobody_published_never_reaches_a_statement(
    schema: str,
) -> None:
    definition = _orders()
    definition.checks = [
        DesignCheck.model_validate(
            {
                "id": "k9",
                "expression": {
                    "kind": "call",
                    "function": "pg_sleep",
                    "arguments": [],
                },
            }
        )
    ]

    plan = await _plan(schema, definition)

    assert plan.problems[0].message == 'Unknown function "pg_sleep"'
    assert plan.statements == []


async def test_a_function_is_refused_where_the_server_would_refuse_it(
    schema: str,
) -> None:
    """`now()` is a default and not an index key, and the vocabulary says so."""
    definition = _orders()
    definition.indexes = [
        DesignIndex.model_validate(
            {
                "id": "i9",
                "keys": [
                    {
                        "kind": "expression",
                        "expression": {"kind": "call", "function": "now"},
                    }
                ],
            }
        )
    ]

    plan = await _plan(schema, definition)

    assert plan.problems[0].object_id == "i9"
    assert plan.problems[0].message == "Now cannot be used there"


async def test_setting_a_required_column_to_null_is_explained(schema: str) -> None:
    definition = _with_customer_key(schema)
    definition.columns[2].not_null = True
    definition.foreign_keys[0].on_delete = "set_null"

    plan = await _plan(schema, definition)

    assert plan.problems[0].object_id == "f1"
    assert plan.problems[0].field == "on_delete"


async def test_a_foreign_key_needs_a_key_to_point_at(schema: str) -> None:
    definition = _orders()
    definition.foreign_keys = [
        DesignForeignKey(
            id="f2",
            column_ids=["c2"],
            target_node_id=f"{schema}.customers",
            # A column exists under that name, and nothing promises it is
            # unique: the target publishes its candidate keys and this is not
            # one of them.
            target_columns=["balance"],
        )
    ]

    plan = await _plan(schema, definition)

    assert plan.problems[0].message.endswith(
        "has no unique key over exactly those columns"
    )


async def test_a_key_between_two_varchar_columns_is_not_refused(
    schema: str,
) -> None:
    """`=` for varchar is text's operator, reached by an implicit cast.

    A comparability lookup that does not follow those casts refuses this key,
    which is what the first version of the query here did.
    """
    definition = _orders()
    definition.foreign_keys = [
        DesignForeignKey(
            id="f4",
            column_ids=["c2"],
            target_node_id=f"{schema}.customers",
            target_columns=["name"],
        )
    ]

    plan = await _plan(schema, definition)

    assert plan.problems == []


async def test_columns_that_cannot_be_compared_are_caught_before_the_ddl(
    schema: str,
) -> None:
    definition = _orders()
    definition.foreign_keys = [
        DesignForeignKey(
            id="f3",
            column_ids=["c6"],
            target_node_id=f"{schema}.customers",
            target_columns=["id"],
        )
    ]

    plan = await _plan(schema, definition)

    assert plan.problems[0].message == '"payload" and "id" cannot be compared'


async def test_an_index_that_repeats_a_key_is_refused(schema: str) -> None:
    definition = _orders()
    definition.indexes = [
        DesignIndex(id="i8", keys=[IndexColumnKey(column_id="c1")])
    ]

    plan = await _plan(schema, definition)

    assert plan.problems[0].message == "The primary key already indexes those columns"


async def test_a_name_somebody_chose_is_never_quietly_replaced(
    schema: str,
) -> None:
    definition = _orders()
    definition.indexes[1].name = "customers_name_idx"

    plan = await _plan(schema, definition)

    assert plan.problems[0].kind == "conflict"
    assert plan.problems[0].object_id == "i2"


async def test_a_derived_name_steps_around_what_is_there(schema: str) -> None:
    await run(f'CREATE INDEX "orders_status_created_idx" ON {schema}.customers (id)')  # noqa: S608 -- fixture-owned schema.

    plan = await _plan(schema, _orders())

    index = next(item for item in plan.statements if item.object_id == "i1")
    assert '"orders_status_created_idx_2"' in index.sql


async def test_a_failure_after_the_table_leaves_nothing_behind(
    schema: str,
) -> None:
    """The whole creation is one transaction, so a refused index undoes it."""
    definition = _orders()
    definition.indexes = [
        DesignIndex.model_validate(
            {
                "id": "i7",
                # GIN has no default operator class for text, which the server
                # only says when the statement runs.
                "method": "gin",
                "keys": [{"kind": "column", "column_id": "c4"}],
            }
        )
    ]
    adapter = _adapter()
    plan = await adapter.plan_table(
        TablePlanRequest(node_id=schema, definition=definition)
    )
    assert plan.problems == []

    with pytest.raises(ValueError, match="index method"):
        await _run(adapter, schema, definition, plan.fingerprint)

    assert await _exists(schema, "orders") is False


async def test_a_partitioned_parent_must_key_on_what_it_is_split_by(
    schema: str,
) -> None:
    definition = _orders()
    definition.partition = DesignPartition(strategy="range", column_ids=["c7"])

    plan = await _plan(schema, definition)

    assert plan.problems[0].field == "primary_key"

    definition.primary_key = DesignPrimaryKey(column_ids=["c1", "c7"])
    definition.unique_constraints = [DesignUnique(id="u1", column_ids=["c2", "c7"])]
    definition.indexes = []
    model = await _create(schema, definition)

    assert model.partitioning is not None
    assert model.partitioning.strategy == "range"


async def test_a_quoted_name_cannot_carry_a_second_statement(
    schema: str,
) -> None:
    """A hostile name is quoted, not refused, and executes nothing."""
    definition = _orders()
    definition.columns[5].name = 'payload"; DROP TABLE customers; --'
    definition.indexes = []

    model = await _create(schema, definition)

    assert 'payload"; DROP TABLE customers; --' in {
        column.name for column in model.columns
    }
    assert await _exists(schema, "customers") is True


async def test_a_type_that_is_not_in_the_vocabulary_is_not_syntax(
    schema: str,
) -> None:
    definition = _orders()
    definition.columns[1].type = DesignColumnType(code="text); DROP TABLE customers; --")

    plan = await _plan(schema, definition)

    assert plan.problems[0].field == "type"
    assert plan.statements == []


async def test_an_expression_deeper_than_the_limit_is_turned_away(
    schema: str,
) -> None:
    node: dict[str, Any] = {"kind": "column", "column_id": "c5"}
    for _ in range(12):
        node = {
            "kind": "arithmetic",
            "operator": "add",
            "left": node,
            "right": _literal("number", "1"),
        }
    definition = _orders()
    definition.checks = [
        DesignCheck.model_validate(
            {
                "id": "k8",
                "expression": {
                    "kind": "compare",
                    "operator": "gt",
                    "left": node,
                    "right": _literal("number", "0"),
                },
            }
        )
    ]

    plan = await _plan(schema, definition)

    assert "nest at most" in plan.problems[0].message
    assert plan.statements == []


async def test_a_payload_too_nested_to_parse_is_turned_away_before_parsing() -> None:
    """The guard that runs before Pydantic recurses on the way in."""
    node: dict[str, Any] = {"kind": "column", "column_id": "c5"}
    for _ in range(40):
        node = {"kind": "not", "operand": node}
    raw = _orders().model_dump(mode="json")
    raw["checks"] = [{"id": "k7", "expression": node}]

    with pytest.raises(ValueError, match="nest at most"):
        TableDefinition.model_validate(raw)


async def test_an_unlogged_table_says_so_in_the_plan(schema: str) -> None:
    definition = _orders()
    definition.persistence = "unlogged"
    definition.indexes = []

    plan = await _plan(schema, definition)

    assert plan.statements[0].sql.startswith("CREATE UNLOGGED TABLE")


async def test_identity_and_a_default_cannot_arrive_together() -> None:
    """The union has no state that holds both, which is the point of it."""
    column = _column(
        "c1", "id", "bigint", generation=IdentityGeneration(generated="always")
    )

    assert isinstance(column.generation, IdentityGeneration)
    with pytest.raises(ValueError):
        DesignColumn.model_validate(
            {
                "id": "c1",
                "name": "id",
                "type": {"code": "bigint"},
                "generation": {"kind": "identity", "value": "1"},
            }
        )


async def test_a_database_without_timescale_offers_no_hypertable(schema: str) -> None:
    options = await _adapter().table_design_options(schema)

    assert options.hypertable.available is False
    assert options.hypertable.reason == "TimescaleDB is not installed on this database"


async def test_a_hypertable_is_refused_where_timescale_is_not_installed(schema: str) -> None:
    definition = TableDefinition(
        name="readings",
        columns=[_column("c1", "observed_at", "timestamp_tz", not_null=True)],
        hypertable=TableHypertable(time_column_id="c1", chunk_interval=DesignDuration(amount=1, unit="day")),
    )

    plan = await _plan(schema, definition)

    assert plan.fingerprint == ""
    assert [(problem.object_id, problem.message) for problem in plan.problems] == [
        ("hypertable", "TimescaleDB is not installed on this database"),
    ]


async def test_a_hypertable_cannot_also_be_partitioned_or_unlogged(schema: str) -> None:
    definition = TableDefinition(
        name="readings",
        persistence="unlogged",
        columns=[_column("c1", "observed_at", "timestamp_tz", not_null=True)],
        partition=DesignPartition(strategy="range", column_ids=["c1"]),
        hypertable=TableHypertable(time_column_id="c1", chunk_interval=DesignDuration(amount=1, unit="day")),
    )

    plan = await _plan(schema, definition)

    assert {problem.message for problem in plan.problems} >= {
        "A hypertable partitions itself; choose it or declarative partitioning, not both",
        "A hypertable cannot be unlogged",
    }

