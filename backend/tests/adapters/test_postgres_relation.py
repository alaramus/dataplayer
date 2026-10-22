from collections.abc import AsyncGenerator

import pytest

from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import (
    CheckConstraint,
    ForeignKey,
    PrimaryKey,
    UniqueConstraint,
)
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def _relation() -> PostgresRelation:
    session = PostgresSession(PostgresUserPassword(**working_postgres_options()))
    return PostgresRelation(session)


async def test_a_relation_says_what_it_is(schema: str) -> None:
    model = await _relation().relation_model(f"{schema}.customers")
    assert model.node_id == f"{schema}.customers"
    assert model.schema_name == schema
    assert model.name == "customers"
    assert model.kind == "table"
    assert model.persistence == "permanent"
    assert model.comment == "People who owe money"
    assert model.owner != ""


async def test_columns_arrive_in_declaration_order_with_their_comments(
    schema: str,
) -> None:
    model = await _relation().relation_model(f"{schema}.customers")
    names = [column.name for column in model.columns]
    assert names[:4] == ["id", "region_id", "region_code", "name"]
    balance = next(column for column in model.columns if column.name == "balance")
    assert balance.comment == "In euros"


async def test_the_awkward_types_are_taken_apart(schema: str) -> None:
    model = await _relation().relation_model(f"{schema}.customers")
    by_name = {column.name: column for column in model.columns}
    assert by_name["tags"].type.sql == "integer[]"
    assert by_name["tags"].type.category == "array"
    assert by_name["tags"].type.element is not None
    assert by_name["tags"].type.element.sql == "integer"
    assert by_name["name"].type.sql == "character varying(50)"
    assert by_name["name"].type.length == 50
    assert by_name["balance"].type.precision == 10
    assert by_name["balance"].type.scale == 2
    assert by_name["feeling"].type.category == "enum"
    assert by_name["feeling"].type.enum_values == ["sad", "ok", "happy"]
    assert by_name["payload"].type.category == "json"
    assert by_name["token"].type.category == "uuid"
    assert by_name["picture"].type.category == "binary"


async def test_identity_generated_and_default_are_told_apart(schema: str) -> None:
    model = await _relation().relation_model(f"{schema}.customers")
    by_name = {column.name: column for column in model.columns}
    assert by_name["id"].identity == "by_default"
    assert by_name["name_upper"].generated is not None
    assert "upper" in by_name["name_upper"].generated
    assert by_name["balance"].default is not None
    assert by_name["name_upper"].default is None


async def test_the_type_of_every_column_can_be_written_back_into_ddl(
    schema: str,
) -> None:
    described = await _relation().relation_model(f"{schema}.customers")
    definition = ", ".join(
        f'"{column.name}" {column.type.sql}' for column in described.columns
    )
    await run(f"CREATE TABLE {schema}.round_trip ({definition})")
    rebuilt = await _relation().relation_model(f"{schema}.round_trip")
    original = {column.name: column.type.sql for column in described.columns}
    copied = {column.name: column.type.sql for column in rebuilt.columns}
    assert copied == original


async def test_a_view_has_columns_and_no_constraints(schema: str) -> None:
    model = await _relation().relation_model(f"{schema}.rich_customers")
    assert model.kind == "view"
    assert [column.name for column in model.columns] == ["id", "name"]
    assert model.constraints == []


async def test_a_relation_that_is_gone_is_not_a_failure(schema: str) -> None:
    with pytest.raises(NodeNotFound):
        await _relation().relation_model(f"{schema}.no_such_table")


async def test_selected_relations_share_a_batch_snapshot(schema: str) -> None:
    models = await _relation().relation_models_for_nodes(
        [
            f"{schema}.customers",
            f"{schema}.regions",
            f"{schema}.no_such_table",
        ]
    )

    assert [model.node_id for model in models] == [
        f"{schema}.customers",
        f"{schema}.regions",
    ]
    assert [column.name for column in models[0].columns][:4] == [
        "id",
        "region_id",
        "region_code",
        "name",
    ]
    assert any(isinstance(key, ForeignKey) for key in models[0].constraints)


async def test_an_id_that_is_not_a_relation_is_refused(schema: str) -> None:
    with pytest.raises(ValueError):
        await _relation().relation_model(schema)


async def test_the_adapter_delegates_to_it(schema: str) -> None:
    adapter = PostgresAdapter(PostgresUserPassword(**working_postgres_options()))
    model = await adapter.relation_model(f"{schema}.customers")
    assert model.name == "customers"


async def test_a_composite_foreign_key_is_one_constraint_in_key_order(
    schema: str,
) -> None:
    model = await _relation().relation_model(f"{schema}.customers")
    keys = [c for c in model.constraints if isinstance(c, ForeignKey)]
    assert len(keys) == 1
    key = keys[0]
    assert key.name == "customers_region_fkey"
    assert key.columns == ["region_id", "region_code"]
    assert key.target_columns == ["id", "code"]
    assert key.on_update == "cascade"
    assert key.on_delete == "restrict"


async def test_a_foreign_key_names_its_target_the_way_the_catalog_does(
    schema: str,
) -> None:
    model = await _relation().relation_model(f"{schema}.customers")
    key = next(c for c in model.constraints if isinstance(c, ForeignKey))
    assert key.target_node_id == f"{schema}.regions"


async def test_the_primary_key_of_the_target_is_composite_and_ordered(
    schema: str,
) -> None:
    model = await _relation().relation_model(f"{schema}.regions")
    key = next(c for c in model.constraints if isinstance(c, PrimaryKey))
    assert key.columns == ["id", "code"]


async def test_unique_and_check_are_reported_with_their_own_shape(
    schema: str,
) -> None:
    model = await _relation().relation_model(f"{schema}.customers")
    unique = next(c for c in model.constraints if isinstance(c, UniqueConstraint))
    assert unique.name == "customers_name_unique"
    assert unique.columns == ["name"]
    check = next(c for c in model.constraints if isinstance(c, CheckConstraint))
    assert check.name == "customers_balance_check"
    assert "balance" in check.expression
    assert check.columns == ["balance"]


async def test_indexes_are_listed_with_their_method_and_predicate(
    schema: str,
) -> None:
    model = await _relation().relation_model(f"{schema}.customers")
    by_name = {index.name: index for index in model.indexes}
    partial = by_name["customers_name_idx"]
    assert partial.method == "btree"
    assert partial.columns == ["name"]
    assert partial.predicate is not None
    assert "balance" in partial.predicate
    assert partial.unique is False
    assert by_name["customers_pkey"].primary is True


async def test_a_partitioned_table_says_how_it_is_split(schema: str) -> None:
    model = await _relation().relation_model(f"{schema}.events")
    assert model.kind == "partitioned_table"
    assert model.partitioning is not None
    assert model.partitioning.strategy == "range"
    assert "happened" in model.partitioning.key


async def test_a_partition_names_its_parent_as_a_node_id(schema: str) -> None:
    model = await _relation().relation_model(f"{schema}.events_2026")
    assert model.partition_of is not None
    assert model.partition_of.parent_node_id == f"{schema}.events"
    assert "2026-01-01" in model.partition_of.bounds


SERVER_TABLE = "pg_catalog.pg_tablespace"


async def test_the_structure_of_a_relation_the_server_owns_does_not_change() -> None:
    """PostgreSQL refuses this DDL itself; the source says so before it is tried."""
    model = await _relation().relation_model(SERVER_TABLE)

    assert model.columns
    assert model.column_changes_supported is False
    assert model.index_changes_supported is False
    assert model.constraint_changes_supported is False
    assert model.column_operations == []
    assert model.index_methods == []
    for reason in (
        model.column_changes_reason,
        model.index_changes_reason,
        model.constraint_changes_reason,
    ):
        assert reason is not None
        assert "pg_catalog" in reason
