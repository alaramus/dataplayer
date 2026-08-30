from collections.abc import AsyncGenerator

import pytest

from app.adapters.column_changes import AddColumnRequest
from app.adapters.constraints import (
    ConstraintCreated,
    CreateConstraintRequest,
    DropConstraintRequest,
    ForeignKeySpec,
    RepeatingValues,
    UniqueConstraintSpec,
    UnmatchedRows,
)
from app.adapters.indexes import CreateIndexRequest
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.counting import COUNT_CEILING
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.relation import Constraint, ForeignKey, RelationModel
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


def _named(model: RelationModel, name: str) -> Constraint:
    return next(item for item in model.constraints if item.name == name)


async def _one_region(schema: str) -> None:
    await run(
        f"INSERT INTO {schema}.regions VALUES (1, 'EU')"  # noqa: S608 -- fixture-owned schema.
    )


async def _loose_codes(schema: str, adapter: PostgresAdapter, codes: str) -> None:
    """Rows carrying a code nothing points at yet.

    Not region_code: the fixture's own foreign key already stops a row that
    names no region, so a column with no constraint on it is needed to set up
    the situation a new key is being asked about.
    """
    await adapter.add_column(
        AddColumnRequest(
            node_id=f"{schema}.customers", name="home_code", type_code="text"
        )
    )
    await _one_region(schema)
    await run(
        f"INSERT INTO {schema}.customers "  # noqa: S608 -- fixture-owned schema.
        f"(region_id, region_code, name, home_code) {codes}"
    )
    await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=f"{schema}.regions",
            constraint=UniqueConstraintSpec(columns=["code"]),
        )
    )


async def test_a_relation_publishes_the_keys_it_can_be_pointed_at_by(
    schema: str,
) -> None:
    model = await _adapter().relation_model(f"{schema}.regions")

    assert model.constraint_changes_supported is True
    # The primary key over (id, code); nothing else in regions is unique.
    assert [key.columns for key in model.candidate_keys] == [["id", "code"]]


async def test_a_key_provided_twice_is_offered_once(schema: str) -> None:
    """A unique constraint and its own index are one column set, not two."""
    model = await _adapter().relation_model(f"{schema}.customers")

    shapes = [tuple(key.columns) for key in model.candidate_keys]
    assert len(shapes) == len(set(shapes))
    assert ("id",) in shapes
    assert ("name",) in shapes


async def test_a_partial_unique_index_is_not_a_candidate_key(schema: str) -> None:
    """customers_name_idx is unique on nothing: it is partial, so it promises
    uniqueness only among the rows its predicate admits."""
    model = await _adapter().relation_model(f"{schema}.customers")

    assert "customers_name_idx" not in {key.name for key in model.candidate_keys}


async def test_a_view_says_why_it_cannot_have_constraints(schema: str) -> None:
    view = await _adapter().relation_model(f"{schema}.rich_customers")

    assert view.constraint_changes_supported is False
    assert view.constraint_changes_reason == "Only tables can have constraints"


async def test_adds_a_unique_constraint_the_source_names(schema: str) -> None:
    adapter = _adapter()

    result = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=f"{schema}.customers",
            constraint=UniqueConstraintSpec(columns=["region_id", "region_code"]),
        )
    )

    assert isinstance(result, ConstraintCreated)
    assert result.name == "customers_region_id_region_code_key"
    model = await adapter.relation_model(f"{schema}.customers")
    assert result.name in {item.name for item in model.constraints}
    # And it becomes something a foreign key may point at.
    assert ["region_id", "region_code"] in [
        key.columns for key in model.candidate_keys
    ]


async def test_repeating_values_are_counted_instead_of_failing_the_add(
    schema: str,
) -> None:
    adapter = _adapter()
    await run(
        f"INSERT INTO {schema}.regions VALUES (1, 'EU'), (2, 'EU'), (3, 'US')"  # noqa: S608 -- fixture-owned schema.
    )

    result = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=f"{schema}.regions",
            constraint=UniqueConstraintSpec(columns=["code"]),
        )
    )

    assert isinstance(result, RepeatingValues)
    assert result.groups == 1
    assert result.exact is True


async def test_adds_a_foreign_key_with_a_closed_action_vocabulary(
    schema: str,
) -> None:
    adapter = _adapter()
    await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=f"{schema}.regions",
            constraint=UniqueConstraintSpec(columns=["code"]),
        )
    )

    result = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=f"{schema}.customers",
            constraint=ForeignKeySpec(
                columns=["region_code"],
                target_node_id=f"{schema}.regions",
                target_columns=["code"],
                on_update="cascade",
                on_delete="set_null",
            ),
        )
    )

    assert isinstance(result, ConstraintCreated)
    model = await adapter.relation_model(f"{schema}.customers")
    added = _named(model, result.name)
    assert isinstance(added, ForeignKey)
    assert added.target_node_id == f"{schema}.regions"
    assert added.on_update == "cascade"
    assert added.on_delete == "set_null"
    assert added.validated is True


async def test_rows_pointing_nowhere_are_counted_instead_of_failing_the_scan(
    schema: str,
) -> None:
    adapter = _adapter()
    await _loose_codes(
        schema,
        adapter,
        "VALUES (1, 'EU', 'ann', 'EU'), (1, 'EU', 'bob', 'XX'), "
        "(1, 'EU', 'cai', 'YY')",
    )

    result = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=f"{schema}.customers",
            constraint=ForeignKeySpec(
                columns=["home_code"],
                target_node_id=f"{schema}.regions",
                target_columns=["code"],
            ),
        )
    )

    assert isinstance(result, UnmatchedRows)
    assert result.rows == 2
    assert result.exact is True


async def test_a_row_empty_in_its_key_points_nowhere_and_is_not_counted(
    schema: str,
) -> None:
    """MATCH SIMPLE: PostgreSQL accepts such a row, so counting it would refuse
    a key the server would have added."""
    adapter = _adapter()
    await _loose_codes(schema, adapter, "VALUES (1, 'EU', 'ann', NULL)")

    result = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=f"{schema}.customers",
            constraint=ForeignKeySpec(
                columns=["home_code"],
                target_node_id=f"{schema}.regions",
                target_columns=["code"],
            ),
        )
    )

    assert isinstance(result, ConstraintCreated)


async def test_the_count_of_unmatched_rows_stops_at_its_ceiling(
    schema: str,
) -> None:
    adapter = _adapter()
    await _loose_codes(
        schema,
        adapter,
        "SELECT 1, 'EU', 'c' || g, 'XX' FROM generate_series(1, "  # noqa: S608 -- a test constant.
        f"{COUNT_CEILING + 1}) AS g",
    )

    result = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=f"{schema}.customers",
            constraint=ForeignKeySpec(
                columns=["home_code"],
                target_node_id=f"{schema}.regions",
                target_columns=["code"],
            ),
        )
    )

    assert isinstance(result, UnmatchedRows)
    assert result.rows == COUNT_CEILING
    assert result.exact is False


async def test_a_target_without_a_key_over_those_columns_is_named(
    schema: str,
) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="no unique key"):
        await adapter.create_constraint(
            CreateConstraintRequest(
                node_id=f"{schema}.customers",
                constraint=ForeignKeySpec(
                    columns=["region_code"],
                    target_node_id=f"{schema}.regions",
                    target_columns=["code"],
                ),
            )
        )


async def test_a_bare_unique_index_may_be_pointed_at(schema: str) -> None:
    """PostgreSQL accepts one, so the published keys include it."""
    adapter = _adapter()
    await adapter.create_index(
        CreateIndexRequest(
            node_id=f"{schema}.regions", columns=["code"], method="btree", unique=True
        )
    )

    result = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=f"{schema}.customers",
            constraint=ForeignKeySpec(
                columns=["region_code"],
                target_node_id=f"{schema}.regions",
                target_columns=["code"],
            ),
        )
    )

    assert isinstance(result, ConstraintCreated)


async def test_create_rejects_unknown_columns_and_relations(schema: str) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="no column"):
        await adapter.create_constraint(
            CreateConstraintRequest(
                node_id=f"{schema}.customers",
                constraint=UniqueConstraintSpec(columns=["missing"]),
            )
        )
    with pytest.raises(ValueError, match="Only tables"):
        await adapter.create_constraint(
            CreateConstraintRequest(
                node_id=f"{schema}.rich_customers",
                constraint=UniqueConstraintSpec(columns=["name"]),
            )
        )


async def test_a_column_name_is_composed_and_never_executed(schema: str) -> None:
    adapter = _adapter()
    name = 'note"); DROP TABLE regions; --'
    await adapter.add_column(
        AddColumnRequest(node_id=f"{schema}.customers", name=name, type_code="text")
    )

    result = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=f"{schema}.customers",
            constraint=UniqueConstraintSpec(columns=[name]),
        )
    )

    assert isinstance(result, ConstraintCreated)
    assert (await adapter.relation_model(f"{schema}.regions")).name == "regions"


async def test_drops_one_constraint(schema: str) -> None:
    adapter = _adapter()

    dropped = await adapter.drop_constraint(
        DropConstraintRequest(
            node_id=f"{schema}.customers", name="customers_balance_check"
        )
    )

    assert dropped.name == "customers_balance_check"
    model = await adapter.relation_model(f"{schema}.customers")
    assert "customers_balance_check" not in {item.name for item in model.constraints}


async def test_a_constraint_something_depends_on_is_refused_safely(
    schema: str,
) -> None:
    """A foreign key holds the unique constraint it points at in place."""
    adapter = _adapter()
    await _loose_codes(schema, adapter, "VALUES (1, 'EU', 'ann', 'EU')")
    await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=f"{schema}.customers",
            constraint=ForeignKeySpec(
                columns=["home_code"],
                target_node_id=f"{schema}.regions",
                target_columns=["code"],
            ),
        )
    )

    with pytest.raises(ValueError, match="depends on this constraint"):
        await adapter.drop_constraint(
            DropConstraintRequest(node_id=f"{schema}.regions", name="regions_code_key")
        )
    model = await adapter.relation_model(f"{schema}.regions")
    assert "regions_code_key" in {item.name for item in model.constraints}


async def test_a_primary_key_is_not_dropped_in_this_round(schema: str) -> None:
    """Not because PostgreSQL minds, but because rows stop being editable."""
    adapter = _adapter()

    with pytest.raises(ValueError, match="rows can only be edited"):
        await adapter.drop_constraint(
            DropConstraintRequest(
                node_id=f"{schema}.customers", name="customers_pkey"
            )
        )


async def test_drop_rejects_a_constraint_this_relation_does_not_have(
    schema: str,
) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="no constraint"):
        await adapter.drop_constraint(
            DropConstraintRequest(node_id=f"{schema}.regions", name="customers_pkey")
        )
