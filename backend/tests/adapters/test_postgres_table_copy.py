"""PostgreSQL tables copied with their structure, at both ends (D182)."""

from collections.abc import AsyncGenerator, AsyncIterator

import pytest

from app.adapters.fetch import FetchRequest
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.protocol import AdapterError
from app.adapters.relation import (
    CheckConstraint,
    ForeignKey,
    PrimaryKey,
    UniqueConstraint,
)
from app.adapters.table_copy import (
    CopiedTable,
    CopyLoad,
    LinkDecision,
    TableCopyRequest,
    TableCopyTarget,
)
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import SCHEMA, make_schema, run

PLACE = "table_copy_test"
CUSTOMERS = f"{SCHEMA}.customers"
REGIONS = f"{SCHEMA}.regions"

ROWS = f"""
DROP SCHEMA IF EXISTS {PLACE} CASCADE;
CREATE SCHEMA {PLACE};
INSERT INTO {SCHEMA}.regions VALUES (1, 'north'), (2, 'south');
INSERT INTO {SCHEMA}.customers (region_id, region_code, name, balance, tags, feeling)
VALUES (1, 'north', 'Ann', 10, '{{1,2}}', 'happy'), (2, 'south', 'Bob', 0, NULL, NULL);
"""  # noqa: S608 -- module constants, never client input.


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        await run(ROWS)
        try:
            yield name
        finally:
            await run(f"DROP SCHEMA IF EXISTS {PLACE} CASCADE")


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


async def _described(*node_ids: str) -> dict[str, CopiedTable]:
    return {table.node_id: table for table in await _adapter().describe_for_copy(list(node_ids))}


def _request(
    targets: list[TableCopyTarget], *, place: str = PLACE, rows: bool = True
) -> TableCopyRequest:
    return TableCopyRequest(
        dialect="postgresql",
        place_node_id=place,
        same_database=True,
        tables=targets,
        rows=rows,
    )


async def _nothing(load: CopyLoad, rows: int, size: int) -> None:
    del load, rows, size


async def _copied(request: TableCopyRequest) -> None:
    adapter = _adapter()
    async with adapter.reading_tables() as tables:
        await adapter.carry_table_copy(
            request, lambda load: tables.rows(load.node_id, load.columns), _nothing
        )


async def _customers_alone(decision: LinkDecision) -> None:
    described = await _described(CUSTOMERS)
    await _copied(
        _request(
            [
                TableCopyTarget(
                    table=described[CUSTOMERS],
                    name="customers",
                    links={"customers_region_fkey": decision},
                )
            ]
        )
    )


async def test_a_table_arrives_with_its_rows_its_keys_and_the_table_it_points_at(
    schema: str,
) -> None:
    del schema
    described = await _described(CUSTOMERS, REGIONS)
    request = _request(
        [
            TableCopyTarget(
                table=described[CUSTOMERS],
                name="customers",
                links={"customers_region_fkey": "copy"},
            ),
            TableCopyTarget(table=described[REGIONS], name="regions"),
        ]
    )

    assert (await _adapter().plan_table_copy(request)).problems == []
    await _copied(request)

    model = await _adapter().relation_model(f"{PLACE}.customers")
    assert [(column.name, column.type.sql) for column in model.columns] == [
        (column.name, column.type.sql)
        for column in (await _adapter().relation_model(CUSTOMERS)).columns
    ]
    kinds = {type(constraint) for constraint in model.constraints}
    assert {PrimaryKey, UniqueConstraint, CheckConstraint, ForeignKey} <= kinds
    link = next(one for one in model.constraints if isinstance(one, ForeignKey))
    assert link.target_node_id == f"{PLACE}.regions"
    assert model.comment == "People who owe money"
    partial = next(index for index in model.indexes if index.predicate is not None)
    assert "balance" in (partial.predicate or "")

    page = await _adapter().fetch(FetchRequest(node_id=f"{PLACE}.customers", limit=10))
    names = [column.name for column in page.columns]
    by_name = {
        row[names.index("name")]: row[names.index("name_upper")] for row in page.rows
    }
    # Generated again from the copied rows rather than carried.
    assert by_name == {"Ann": "ANN", "Bob": "BOB"}


async def test_the_numbering_continues_after_the_copied_rows(schema: str) -> None:
    del schema
    await _customers_alone("original")

    await run(
        f"INSERT INTO {PLACE}.customers (region_id, region_code, name) VALUES (1, 'north', 'Cy')"  # noqa: S608 -- module constants
    )

    page = await _adapter().fetch(FetchRequest(node_id=f"{PLACE}.customers", limit=10))
    names = [column.name for column in page.columns]
    ids = {row[names.index("name")]: row[names.index("id")] for row in page.rows}
    assert int(str(ids["Cy"])) > max(int(str(ids["Ann"])), int(str(ids["Bob"])))


async def test_a_link_kept_points_at_the_original(schema: str) -> None:
    del schema
    await _customers_alone("original")

    model = await _adapter().relation_model(f"{PLACE}.customers")
    link = next(one for one in model.constraints if isinstance(one, ForeignKey))
    assert link.target_node_id == REGIONS


async def test_a_dropped_link_is_not_made(schema: str) -> None:
    del schema
    await _customers_alone("drop")

    model = await _adapter().relation_model(f"{PLACE}.customers")
    assert not any(isinstance(one, ForeignKey) for one in model.constraints)


async def test_structure_only_makes_the_tables_empty(schema: str) -> None:
    del schema
    described = await _described(REGIONS)

    await _copied(
        _request([TableCopyTarget(table=described[REGIONS], name="regions")], rows=False)
    )

    page = await _adapter().fetch(FetchRequest(node_id=f"{PLACE}.regions", limit=10))
    assert page.rows == []
    model = await _adapter().relation_model(f"{PLACE}.regions")
    assert any(isinstance(one, PrimaryKey) for one in model.constraints)


async def test_a_taken_name_is_a_conflict_and_nothing_runs(schema: str) -> None:
    described = await _described(REGIONS)
    request = _request(
        [TableCopyTarget(table=described[REGIONS], name="regions")], place=schema
    )

    plan = await _adapter().plan_table_copy(request)

    assert [(problem.kind, problem.message) for problem in plan.problems] == [
        ("conflict", f"{schema}.regions is already there")
    ]
    with pytest.raises(ValueError, match="already there"):
        await _copied(request)


async def test_a_failure_while_the_rows_arrive_leaves_nothing_behind(schema: str) -> None:
    del schema
    described = await _described(CUSTOMERS, REGIONS)
    request = _request(
        [
            TableCopyTarget(
                table=described[CUSTOMERS],
                name="customers",
                links={"customers_region_fkey": "copy"},
            ),
            TableCopyTarget(table=described[REGIONS], name="regions"),
        ]
    )

    async def failing(load: CopyLoad) -> AsyncIterator[bytes]:
        del load
        yield b""
        raise AdapterError("network", "The source went away")

    with pytest.raises(AdapterError):
        await _adapter().carry_table_copy(request, failing, _nothing)

    nodes = await _adapter().list_children(PLACE)
    assert nodes == []


async def test_what_cannot_be_copied_says_why(schema: str) -> None:
    described = await _described(
        f"{schema}.events", f"{schema}.events_2026", f"{schema}.rich_customers"
    )

    assert [table.refusal for table in described.values()] == [
        "partitioned tables are not copied yet",
        "partitions are not copied yet",
        "only tables are copied with their structure",
    ]


async def test_a_free_name_is_found_beside_a_taken_one(schema: str) -> None:
    free = await _adapter().free_table_names(schema, ["customers", "customers", "fresh"])

    assert free == ["customers_copy", "customers_copy_2", "fresh"]


async def test_a_fragment_that_is_not_one_expression_is_left_behind(schema: str) -> None:
    del schema
    described = await _described(CUSTOMERS)
    table = described[CUSTOMERS]
    lying = table.model_copy(
        update={
            "constraints": [
                constraint.model_copy(update={"definition": "CHECK (true); DROP TABLE x"})
                if constraint.kind == "check"
                else constraint
                for constraint in table.constraints
            ]
        }
    )

    plan = await _adapter().plan_table_copy(
        _request([TableCopyTarget(table=lying, name="customers")])
    )

    assert plan.problems == []
    assert any("could not be read" in warning for warning in plan.warnings)
    assert not any("DROP TABLE x" in statement.sql for statement in plan.statements)


async def test_a_type_whose_schema_is_not_there_is_made_in_the_place(schema: str) -> None:
    """Another database: the enum is made where the tables go, and every text
    that names it names the new one."""
    described = await _described(CUSTOMERS)
    table = described[CUSTOMERS]
    elsewhere = table.model_copy(
        update={
            "types": [
                one.model_copy(update={"schema_name": "gone", "spelled": "gone.mood"})
                for one in table.types
            ],
            "columns": [
                column.model_copy(
                    update={"type_sql": "gone.mood", "default": "'ok'::gone.mood"}
                )
                if column.name == "feeling"
                else column
                for column in table.columns
            ],
        }
    )
    request = _request([TableCopyTarget(table=elsewhere, name="customers")]).model_copy(
        update={"same_database": False}
    )

    plan = await _adapter().plan_table_copy(request)

    assert plan.problems == []
    sql = "\n".join(statement.sql for statement in plan.statements)
    assert f'CREATE TYPE "{PLACE}"."mood" AS ENUM' in sql
    assert f'"feeling" "{PLACE}"."mood" DEFAULT \'ok\'::"{PLACE}"."mood"' in sql
    assert "gone.mood" not in sql
    assert schema in {one.schema_name for one in table.types}
