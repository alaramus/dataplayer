"""Changing the structure of a MySQL table: columns, indexes, constraints (D235).

On MySQL and MariaDB. Each test makes the table it changes.
"""

import uuid
from collections.abc import AsyncIterator

import pytest

from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnDefaultRequest,
    ColumnNullabilityRequest,
    ColumnTypeRequest,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.constraints import (
    CreateConstraintRequest,
    DropConstraintRequest,
    ForeignKeySpec,
    UniqueConstraintSpec,
)
from app.adapters.indexes import CreateIndexRequest, DropIndexRequest
from app.adapters.mysql import ids
from app.adapters.mysql.adapter import MysqlAdapter
from app.adapters.relation import RelationModel
from tests.adapters.mysql_fixture import TARGETS, Target, run

DATABASE = "dp_struct"


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await run(
        chosen,
        f"DROP DATABASE IF EXISTS {DATABASE}",
        f"CREATE DATABASE {DATABASE}",
        f"CREATE TABLE {DATABASE}.parents (id INT PRIMARY KEY)",
        f"INSERT INTO {DATABASE}.parents VALUES (1), (2)",
    )
    yield chosen
    await run(chosen, f"DROP DATABASE IF EXISTS {DATABASE}")


async def _table(target: Target, columns: str, *rows: str) -> str:
    """A new table with these columns and rows, as its node id."""
    name = f"t_{uuid.uuid4().hex[:8]}"
    statements = [f"CREATE TABLE {DATABASE}.{name} ({columns})"]
    statements += [f"INSERT INTO {DATABASE}.{name} VALUES {row}" for row in rows]
    await run(target, *statements)
    return ids.relation_id(DATABASE, name)


async def _model(adapter: MysqlAdapter, node_id: str) -> RelationModel:
    return await adapter.relation_model(node_id)


def _column(model: RelationModel, name: str):  # type: ignore[no-untyped-def]  # a Column, found by name
    return next(column for column in model.columns if column.name == name)


async def test_a_table_offers_its_structure_and_a_view_does_not(target: Target) -> None:
    adapter = target.adapter()
    node = await _table(target, "id INT PRIMARY KEY")
    await run(target, f"CREATE OR REPLACE VIEW {DATABASE}.v AS SELECT 1 AS one")

    table = await _model(adapter, node)
    view = await _model(adapter, ids.relation_id(DATABASE, "v"))
    system = await _model(adapter, ids.relation_id("mysql", "db"))

    assert table.column_changes_supported and table.index_changes_supported
    assert table.constraint_changes_supported
    assert {option.code for option in table.column_type_options} >= {"text", "integer", "json"}
    assert {method.code for method in table.index_methods} == {"btree", "fulltext", "spatial"}
    assert not view.column_changes_supported and view.column_changes_reason
    assert not system.index_changes_supported and system.index_changes_reason


# --- Columns -------------------------------------------------------------


async def test_columns_are_added_renamed_and_dropped(target: Target) -> None:
    adapter = target.adapter()
    node = await _table(target, "id INT PRIMARY KEY", "(1)")

    await adapter.add_column(AddColumnRequest(node_id=node, name="note", type_code="text"))
    await adapter.add_column(
        AddColumnRequest(node_id=node, name="count", type_code="integer", nullable=False)
    )
    with pytest.raises(ValueError, match="already has"):
        await adapter.add_column(AddColumnRequest(node_id=node, name="NOTE", type_code="text"))
    with pytest.raises(ValueError, match="Unknown column type"):
        await adapter.add_column(AddColumnRequest(node_id=node, name="x", type_code="money"))
    await adapter.rename_column(RenameColumnRequest(node_id=node, name="note", new_name="remark"))
    await adapter.drop_column(DropColumnRequest(node_id=node, name="count"))
    model = await _model(adapter, node)

    assert [column.name for column in model.columns] == ["id", "remark"]
    assert _column(model, "remark").type.sql == "varchar(255)"


async def test_the_last_column_is_not_dropped(target: Target) -> None:
    adapter = target.adapter()
    node = await _table(target, "only_one INT")

    with pytest.raises(ValueError, match="at least one column"):
        await adapter.drop_column(DropColumnRequest(node_id=node, name="only_one"))


async def test_a_default_is_set_as_a_literal_and_dropped(target: Target) -> None:
    adapter = target.adapter()
    node = await _table(target, "id INT PRIMARY KEY, n INT, s VARCHAR(40)")

    with pytest.raises(ValueError, match="cannot hold that default"):
        await adapter.change_column_default(
            ColumnDefaultRequest(node_id=node, name="n", action="set", value="many")
        )
    await adapter.change_column_default(
        ColumnDefaultRequest(node_id=node, name="n", action="set", value="5")
    )
    await adapter.change_column_default(
        ColumnDefaultRequest(node_id=node, name="s", action="set", value="it's; DROP TABLE x")
    )
    model = await _model(adapter, node)
    assert _column(model, "n").default in ("5", "'5'")
    assert "it''s; DROP TABLE x" in (_column(model, "s").default or "")

    await adapter.change_column_default(ColumnDefaultRequest(node_id=node, name="n", action="drop"))
    assert _column(await _model(adapter, node), "n").default is None


async def test_requiring_a_value_counts_the_rows_without_one(target: Target) -> None:
    adapter = target.adapter()
    node = await _table(target, "id INT PRIMARY KEY, n INT", "(1, NULL)", "(2, NULL)", "(3, 7)")

    blocked = await adapter.change_column_nullability(
        ColumnNullabilityRequest(node_id=node, name="n", nullable=False)
    )

    assert blocked.kind == "blocked"
    assert blocked.rows_without_value == 2  # type: ignore[union-attr]  # blocked, asserted above
    with pytest.raises(ValueError, match="primary key"):
        await adapter.change_column_nullability(
            ColumnNullabilityRequest(node_id=node, name="id", nullable=True)
        )


async def test_modify_keeps_what_it_was_not_asked_to_change(target: Target) -> None:
    """MODIFY takes the whole definition; a rebuilt one loses its default and comment."""
    adapter = target.adapter()
    node = await _table(
        target,
        "id INT AUTO_INCREMENT PRIMARY KEY, "
        "s VARCHAR(10) CHARACTER SET latin1 COLLATE latin1_bin DEFAULT 'x' COMMENT 'kept'",
        "(1, '12')",
    )

    changed = await adapter.change_column_nullability(
        ColumnNullabilityRequest(node_id=node, name="s", nullable=False)
    )
    # Text to text keeps the character set and collation; MySQL gives a TEXT
    # column no literal default, so the wider type is a VARCHAR.
    retyped = await adapter.change_column_type(
        ColumnTypeRequest(node_id=node, name="s", type_code="text")
    )
    model = await _model(adapter, node)
    column = _column(model, "s")

    assert changed.kind == "changed" and retyped.kind == "changed"
    assert column.type.sql == "varchar(255)"
    assert not column.nullable
    assert column.default in ("x", "'x'")
    assert column.comment == "kept"
    assert column.collation == "latin1_bin"
    assert _column(model, "id").identity == "by_default"


async def test_a_type_the_values_do_not_fit_is_refused_with_a_count(target: Target) -> None:
    adapter = target.adapter()
    node = await _table(
        target, "id INT PRIMARY KEY, s VARCHAR(10)", "(1, '12')", "(2, 'twelve')", "(3, 'x')", "(4, NULL)"
    )

    blocked = await adapter.change_column_type(
        ColumnTypeRequest(node_id=node, name="s", type_code="integer")
    )
    model = await _model(adapter, node)

    assert blocked.kind == "blocked"
    assert blocked.rows_not_convertible == 2  # type: ignore[union-attr]  # blocked, asserted above
    assert _column(model, "s").type.sql == "varchar(10)"


async def test_a_type_the_values_fit_is_taken(target: Target) -> None:
    adapter = target.adapter()
    node = await _table(target, "id INT PRIMARY KEY, s VARCHAR(10)", "(1, '12')", "(2, NULL)")

    changed = await adapter.change_column_type(
        ColumnTypeRequest(node_id=node, name="s", type_code="bigint")
    )

    assert changed.kind == "changed"
    page_type = _column(await _model(adapter, node), "s").type
    assert page_type.category == "number"


# --- Indexes -------------------------------------------------------------


async def test_an_index_is_made_named_by_the_server_and_dropped(target: Target) -> None:
    adapter = target.adapter()
    node = await _table(target, "id INT PRIMARY KEY, a INT, b VARCHAR(20)", "(1, 1, 'x')", "(2, 1, 'y')")

    made = await adapter.create_index(CreateIndexRequest(node_id=node, columns=["a", "b"], method="btree"))
    blocked = await adapter.create_index(
        CreateIndexRequest(node_id=node, columns=["a"], method="btree", unique=True)
    )
    assert made.kind == "created" and made.name  # type: ignore[union-attr]  # created, asserted
    assert blocked.kind == "blocked" and blocked.duplicate_groups == 1  # type: ignore[union-attr]  # blocked

    with pytest.raises(ValueError, match="text columns"):
        await adapter.create_index(CreateIndexRequest(node_id=node, columns=["a"], method="fulltext"))
    with pytest.raises(ValueError, match="primary key"):
        await adapter.drop_index(DropIndexRequest(node_id=node, name="PRIMARY"))
    await adapter.drop_index(DropIndexRequest(node_id=node, name=made.name))  # type: ignore[union-attr]  # created
    model = await _model(adapter, node)
    assert [index.name for index in model.indexes] == ["PRIMARY"]


# --- Constraints ---------------------------------------------------------


async def test_unique_and_foreign_keys_are_counted_made_and_dropped(target: Target) -> None:
    adapter = target.adapter()
    node = await _table(
        target, "id INT PRIMARY KEY, code INT, parent_id INT", "(1, 10, 1)", "(2, 10, 9)", "(3, 11, NULL)"
    )
    parents = ids.relation_id(DATABASE, "parents")

    repeating = await adapter.create_constraint(
        CreateConstraintRequest(node_id=node, constraint=UniqueConstraintSpec(columns=["code"]))
    )
    unmatched = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=node,
            constraint=ForeignKeySpec(
                columns=["parent_id"], target_node_id=parents, target_columns=["id"]
            ),
        )
    )
    assert repeating.kind == "repeating" and repeating.groups == 1  # type: ignore[union-attr]  # repeating
    # The NULL names no row and is not counted: MATCH SIMPLE.
    assert unmatched.kind == "unmatched" and unmatched.rows == 1  # type: ignore[union-attr]  # unmatched

    await run(target, f"UPDATE {DATABASE}.{ids.parse(node)[1]} SET code = id, parent_id = 2 WHERE id = 2")
    unique = await adapter.create_constraint(
        CreateConstraintRequest(node_id=node, constraint=UniqueConstraintSpec(columns=["code"]))
    )
    foreign = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id=node,
            constraint=ForeignKeySpec(
                columns=["parent_id"],
                target_node_id=parents,
                target_columns=["id"],
                on_delete="cascade",
            ),
        )
    )
    model = await _model(adapter, node)
    names = {constraint.name: constraint.kind for constraint in model.constraints}
    assert names[unique.name] == "unique"  # type: ignore[union-attr]  # created
    assert names[foreign.name] == "foreign_key"  # type: ignore[union-attr]  # created

    with pytest.raises(ValueError, match="SET DEFAULT"):
        await adapter.create_constraint(
            CreateConstraintRequest(
                node_id=node,
                constraint=ForeignKeySpec(
                    columns=["parent_id"],
                    target_node_id=parents,
                    target_columns=["id"],
                    on_delete="set_default",
                ),
            )
        )
    with pytest.raises(ValueError, match="primary key"):
        await adapter.drop_constraint(DropConstraintRequest(node_id=node, name="PRIMARY"))
    await adapter.drop_constraint(DropConstraintRequest(node_id=node, name=foreign.name))  # type: ignore[union-attr]  # created
    await adapter.drop_constraint(DropConstraintRequest(node_id=node, name=unique.name))  # type: ignore[union-attr]  # created
    kinds = [constraint.kind for constraint in (await _model(adapter, node)).constraints]
    assert kinds == ["primary_key"]


async def test_a_check_is_dropped_on_either_server(target: Target) -> None:
    adapter = target.adapter()
    node = await _table(target, "id INT PRIMARY KEY, n INT, CONSTRAINT n_positive CHECK (n > 0)")

    await adapter.drop_constraint(DropConstraintRequest(node_id=node, name="n_positive"))

    assert not [c for c in (await _model(adapter, node)).constraints if c.kind == "check"]
