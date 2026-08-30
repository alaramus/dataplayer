from collections.abc import AsyncGenerator

import pytest

from app.adapters.column_changes import AddColumnRequest
from app.adapters.indexes import (
    CreateIndexRequest,
    DropIndexRequest,
    IndexBlocked,
    IndexCreated,
)
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.counting import COUNT_CEILING
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.relation import Index, RelationModel
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


def _index(model: RelationModel, name: str) -> Index:
    return next(index for index in model.indexes if index.name == name)


async def _with_note(schema: str) -> PostgresAdapter:
    """The fixture plus one ordinary column nothing else depends on."""
    adapter = _adapter()
    await adapter.add_column(
        AddColumnRequest(node_id=f"{schema}.customers", name="note", type_code="text")
    )
    return adapter


async def _one_region(schema: str) -> None:
    await run(
        f"INSERT INTO {schema}.regions VALUES (1, 'EU')"  # noqa: S608 -- fixture-owned schema.
    )


async def test_a_table_publishes_index_methods_with_the_servers_own_limits(
    schema: str,
) -> None:
    model = await _adapter().relation_model(f"{schema}.customers")

    assert model.index_changes_supported is True
    assert model.index_changes_reason is None
    methods = {option.code: option for option in model.index_methods}
    assert methods["btree"].unique_supported is True
    assert methods["btree"].multi_column_supported is True
    # Read from pg_indexam_has_property, not written down in this repository.
    assert methods["hash"].unique_supported is False
    assert methods["hash"].multi_column_supported is False


async def test_a_view_says_why_it_cannot_be_indexed(schema: str) -> None:
    view = await _adapter().relation_model(f"{schema}.rich_customers")

    assert view.index_changes_supported is False
    assert view.index_changes_reason == (
        "Only tables and materialized views can be indexed"
    )
    assert view.index_methods == []


async def test_a_child_partition_can_be_indexed_although_its_shape_cannot_change(
    schema: str,
) -> None:
    """The two gates answer different questions, which is why there are two."""
    child = await _adapter().relation_model(f"{schema}.events_2026")

    assert child.column_changes_supported is False
    assert child.index_changes_supported is True


async def test_creates_an_index_the_source_names(schema: str) -> None:
    adapter = await _with_note(schema)

    result = await adapter.create_index(
        CreateIndexRequest(
            node_id=f"{schema}.customers", columns=["note"], method="btree"
        )
    )

    assert isinstance(result, IndexCreated)
    assert result.name == "customers_note_idx"
    created = _index(await adapter.relation_model(f"{schema}.customers"), result.name)
    assert created.columns == ["note"]
    assert created.unique is False


async def test_creates_a_multi_column_unique_index_in_the_order_given(
    schema: str,
) -> None:
    adapter = await _with_note(schema)

    result = await adapter.create_index(
        CreateIndexRequest(
            node_id=f"{schema}.customers",
            columns=["note", "region_id"],
            method="btree",
            unique=True,
        )
    )

    assert isinstance(result, IndexCreated)
    created = _index(await adapter.relation_model(f"{schema}.customers"), result.name)
    assert created.columns == ["note", "region_id"]
    assert created.unique is True


async def test_repeating_values_are_counted_instead_of_failing_the_build(
    schema: str,
) -> None:
    adapter = await _with_note(schema)
    await _one_region(schema)
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name, note) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'ann', 'x'), (1, 'EU', 'bob', 'x'), "
        "(1, 'EU', 'cai', 'y'), (1, 'EU', 'dee', 'y'), (1, 'EU', 'eve', 'z')"
    )

    result = await adapter.create_index(
        CreateIndexRequest(
            node_id=f"{schema}.customers",
            columns=["note"],
            method="btree",
            unique=True,
        )
    )

    assert isinstance(result, IndexBlocked)
    assert result.duplicate_groups == 2
    assert result.exact is True
    model = await adapter.relation_model(f"{schema}.customers")
    assert "customers_note_idx" not in {index.name for index in model.indexes}


async def test_rows_empty_in_a_key_column_do_not_repeat(schema: str) -> None:
    """PostgreSQL indexes NULLS DISTINCT, so counting nulls as collisions would
    refuse an index the server would have built."""
    adapter = await _with_note(schema)
    await _one_region(schema)
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name) "  # noqa: S608 -- fixture-owned schema.
        "VALUES (1, 'EU', 'ann'), (1, 'EU', 'bob')"
    )

    result = await adapter.create_index(
        CreateIndexRequest(
            node_id=f"{schema}.customers",
            columns=["note"],
            method="btree",
            unique=True,
        )
    )

    assert isinstance(result, IndexCreated)


async def test_the_count_of_repeating_values_stops_at_its_ceiling(
    schema: str,
) -> None:
    adapter = await _with_note(schema)
    await _one_region(schema)
    await run(
        f"INSERT INTO {schema}.customers (region_id, region_code, name, note) "  # noqa: S608 -- fixture-owned schema.
        "SELECT 1, 'EU', 'c' || g || '-' || r, 'n' || g "
        f"FROM generate_series(1, {COUNT_CEILING + 1}) AS g, "
        "generate_series(1, 2) AS r"
    )

    result = await adapter.create_index(
        CreateIndexRequest(
            node_id=f"{schema}.customers",
            columns=["note"],
            method="btree",
            unique=True,
        )
    )

    assert isinstance(result, IndexBlocked)
    assert result.duplicate_groups == COUNT_CEILING
    assert result.exact is False


async def test_a_method_is_refused_by_the_limits_it_published(schema: str) -> None:
    adapter = await _with_note(schema)

    with pytest.raises(ValueError, match="unique index"):
        await adapter.create_index(
            CreateIndexRequest(
                node_id=f"{schema}.customers",
                columns=["note"],
                method="hash",
                unique=True,
            )
        )
    with pytest.raises(ValueError, match="more than one column"):
        await adapter.create_index(
            CreateIndexRequest(
                node_id=f"{schema}.customers",
                columns=["note", "region_id"],
                method="hash",
            )
        )


async def test_a_method_that_does_not_fit_the_type_is_left_to_the_server(
    schema: str,
) -> None:
    """Operator classes change with what is installed, so the server answers."""
    adapter = _adapter()

    with pytest.raises(ValueError, match="does not fit the type"):
        await adapter.create_index(
            CreateIndexRequest(
                node_id=f"{schema}.customers", columns=["region_id"], method="gin"
            )
        )


async def test_create_rejects_unknown_columns_methods_and_relations(
    schema: str,
) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="no column"):
        await adapter.create_index(
            CreateIndexRequest(
                node_id=f"{schema}.customers", columns=["missing"], method="btree"
            )
        )
    with pytest.raises(ValueError, match="Unknown index method"):
        await adapter.create_index(
            CreateIndexRequest(
                node_id=f"{schema}.customers",
                columns=["name"],
                method="btree (name); DROP TABLE regions; --",
            )
        )
    with pytest.raises(ValueError, match="materialized views"):
        await adapter.create_index(
            CreateIndexRequest(
                node_id=f"{schema}.rich_customers", columns=["name"], method="btree"
            )
        )
    assert (await adapter.relation_model(f"{schema}.regions")).name == "regions"


async def test_a_column_name_is_composed_and_never_executed(schema: str) -> None:
    adapter = _adapter()
    name = 'note"); DROP TABLE regions; --'
    await adapter.add_column(
        AddColumnRequest(node_id=f"{schema}.customers", name=name, type_code="text")
    )

    result = await adapter.create_index(
        CreateIndexRequest(
            node_id=f"{schema}.customers", columns=[name], method="btree"
        )
    )

    assert isinstance(result, IndexCreated)
    created = _index(await adapter.relation_model(f"{schema}.customers"), result.name)
    assert created.columns == [name]
    assert (await adapter.relation_model(f"{schema}.regions")).name == "regions"


async def test_drops_one_index_of_this_relation(schema: str) -> None:
    adapter = await _with_note(schema)
    created = await adapter.create_index(
        CreateIndexRequest(
            node_id=f"{schema}.customers", columns=["note"], method="btree"
        )
    )
    assert isinstance(created, IndexCreated)

    dropped = await adapter.drop_index(
        DropIndexRequest(node_id=f"{schema}.customers", name=created.name)
    )

    assert dropped.name == created.name
    model = await adapter.relation_model(f"{schema}.customers")
    assert created.name not in {index.name for index in model.indexes}


async def test_an_index_a_constraint_stands_on_is_named_not_relayed(
    schema: str,
) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="primary key"):
        await adapter.drop_index(
            DropIndexRequest(node_id=f"{schema}.customers", name="customers_pkey")
        )
    with pytest.raises(ValueError, match="customers_name_unique"):
        await adapter.drop_index(
            DropIndexRequest(
                node_id=f"{schema}.customers", name="customers_name_unique"
            )
        )
    model = await adapter.relation_model(f"{schema}.customers")
    assert {"customers_pkey", "customers_name_unique"} <= {
        index.name for index in model.indexes
    }


async def test_drop_rejects_an_index_this_relation_does_not_have(
    schema: str,
) -> None:
    adapter = _adapter()

    with pytest.raises(ValueError, match="no index"):
        await adapter.drop_index(
            DropIndexRequest(node_id=f"{schema}.customers", name="no_such_index")
        )
    # An index of another relation is not this relation's either.
    with pytest.raises(ValueError, match="no index"):
        await adapter.drop_index(
            DropIndexRequest(node_id=f"{schema}.regions", name="customers_name_idx")
        )
