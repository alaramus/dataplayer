"""DuckDB columns, indexes and constraints changed in place; the table designer;
a table made from rows (D396, D397).

Every test writes its own file under a temporary home.
"""

from pathlib import Path
from typing import Any

import duckdb
import pytest

from app.adapters.actions import ActionRefused, TakesParams
from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnDefaultRequest,
    ColumnNullabilityRequest,
    ColumnTypeBlocked,
    ColumnTypeChanged,
    ColumnTypeRequest,
    DropColumnRequest,
    NullabilityBlocked,
    NullabilityChanged,
    RenameColumnRequest,
)
from app.adapters.constraints import (
    ConstraintCreated,
    CreateConstraintRequest,
    DropConstraintRequest,
    RepeatingValues,
)
from app.adapters.duckdb.adapter import DuckdbAdapter
from app.adapters.duckdb.options import DuckdbOptions
from app.adapters.fetch import FetchRequest
from app.adapters.indexes import (
    CreateIndexRequest,
    DropIndexRequest,
    IndexBlocked,
    IndexCreated,
)
from app.adapters.relation import ForeignKey, UniqueConstraint
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)
from app.adapters.table_design import TableDefinition, TablePlanRequest
from tests.adapters.duckdb_fixture import FILE, build


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


@pytest.fixture
def adapter(home: Path) -> DuckdbAdapter:
    return DuckdbAdapter(DuckdbOptions(path=FILE), home)


async def _columns(adapter: DuckdbAdapter, node_id: str) -> dict[str, Any]:
    model = await adapter.relation_model(node_id)
    return {column.name: column for column in model.columns}


# --- Columns (D396) ---------------------------------------------------------


async def test_a_table_offers_every_column_change_and_a_view_none(adapter: DuckdbAdapter) -> None:
    table = await adapter.relation_model("main.items")
    view = await adapter.relation_model("main.cheap")

    assert table.column_changes_supported and table.index_changes_supported
    assert table.column_operations == ["add", "drop", "rename", "default", "nullability", "type"]
    assert {option.code for option in table.column_type_options} >= {"text", "integer", "timestamptz"}
    assert [method.code for method in table.index_methods] == ["art"]
    assert view.column_changes_supported is False
    with pytest.raises(ValueError, match="Only a table"):
        await adapter.add_column(AddColumnRequest(node_id="main.cheap", name="x", type_code="text"))


async def test_a_column_is_added_renamed_and_dropped_in_place(adapter: DuckdbAdapter) -> None:
    await adapter.add_column(AddColumnRequest(node_id="main.events", name="note", type_code="text"))
    await adapter.rename_column(
        RenameColumnRequest(node_id="main.events", name="note", new_name="remark")
    )
    renamed = await _columns(adapter, "main.events")
    await adapter.drop_column(DropColumnRequest(node_id="main.events", name="remark"))

    assert renamed["remark"].type.sql == "VARCHAR"
    assert "remark" not in await _columns(adapter, "main.events")
    with pytest.raises(ValueError, match="already has a column"):
        await adapter.add_column(AddColumnRequest(node_id="main.events", name="KIND", type_code="text"))


async def test_a_required_column_is_not_added_to_a_table_with_rows(adapter: DuckdbAdapter) -> None:
    with pytest.raises(ValueError, match="table that has rows"):
        await adapter.add_column(
            AddColumnRequest(node_id="main.events", name="must", type_code="integer", nullable=False)
        )


async def test_a_change_that_breaks_a_view_is_refused_by_its_name(
    adapter: DuckdbAdapter, home: Path
) -> None:
    connection = duckdb.connect(str(home / FILE))
    try:
        connection.execute("CREATE VIEW kinds_seen AS SELECT kind FROM events")
    finally:
        connection.close()

    with pytest.raises(ValueError, match='View "kinds_seen"'):
        await adapter.rename_column(
            RenameColumnRequest(node_id="main.events", name="kind", new_name="sort")
        )

    # Nothing changed: the transaction was rolled back.
    assert "kind" in await _columns(adapter, "main.events")


async def test_a_table_something_depends_on_says_what_still_works(
    adapter: DuckdbAdapter,
) -> None:
    # items has an index of its own; labels is what items' foreign key names.
    for node_id, column in (("main.items", "name"), ("main.labels", "name")):
        with pytest.raises(ValueError, match="adding a column, a default or an index still works"):
            await adapter.rename_column(
                RenameColumnRequest(node_id=node_id, name=column, new_name="title")
            )
    await adapter.add_column(AddColumnRequest(node_id="main.labels", name="note", type_code="text"))


async def test_what_duckdb_refuses_is_said_in_its_words(adapter: DuckdbAdapter) -> None:
    # A unique key names price, and an index depends on it.
    with pytest.raises(ValueError, match="constraint|index|depend"):
        await adapter.drop_column(DropColumnRequest(node_id="main.items", name="price"))


async def test_a_default_is_tried_as_the_columns_type_then_set_and_dropped(
    adapter: DuckdbAdapter,
) -> None:
    with pytest.raises(ValueError, match="cannot be read as"):
        await adapter.change_column_default(
            ColumnDefaultRequest(node_id="main.events", name="step", action="set", value="many")
        )
    await adapter.change_column_default(
        ColumnDefaultRequest(node_id="main.events", name="step", action="set", value="7")
    )
    set_ = (await _columns(adapter, "main.events"))["step"].default
    await adapter.change_column_default(
        ColumnDefaultRequest(node_id="main.events", name="step", action="drop")
    )

    assert set_ is not None and "7" in set_
    assert (await _columns(adapter, "main.events"))["step"].default is None


async def test_a_requirement_counts_the_rows_without_a_value_first(adapter: DuckdbAdapter) -> None:
    blocked = await adapter.change_column_nullability(
        ColumnNullabilityRequest(node_id="main.items", name="label_id", nullable=False)
    )
    changed = await adapter.change_column_nullability(
        ColumnNullabilityRequest(node_id="main.events", name="kind", nullable=False)
    )
    back = await adapter.change_column_nullability(
        ColumnNullabilityRequest(node_id="main.events", name="kind", nullable=True)
    )

    assert isinstance(blocked, NullabilityBlocked) and blocked.rows_without_value == 2
    assert isinstance(changed, NullabilityChanged) and isinstance(back, NullabilityChanged)
    with pytest.raises(ValueError, match="primary key"):
        await adapter.change_column_nullability(
            ColumnNullabilityRequest(node_id="main.items", name="id", nullable=True)
        )


async def test_a_type_change_counts_what_would_not_convert_first(adapter: DuckdbAdapter) -> None:
    blocked = await adapter.change_column_type(
        ColumnTypeRequest(node_id="main.events", name="kind", type_code="integer")
    )
    changed = await adapter.change_column_type(
        ColumnTypeRequest(node_id="main.events", name="step", type_code="bigint")
    )

    assert isinstance(blocked, ColumnTypeBlocked) and blocked.rows_not_convertible == 4
    assert isinstance(changed, ColumnTypeChanged) and changed.type_sql == "BIGINT"
    assert (await _columns(adapter, "main.events"))["step"].type.sql == "BIGINT"


# --- Indexes and constraints (D396) -----------------------------------------


async def test_an_index_is_made_counted_first_when_unique_and_dropped(
    adapter: DuckdbAdapter,
) -> None:
    blocked = await adapter.create_index(
        CreateIndexRequest(node_id="main.events", columns=["kind"], method="art", unique=True)
    )
    made = await adapter.create_index(
        CreateIndexRequest(node_id="main.events", columns=["kind", "step"], method="art")
    )
    assert isinstance(made, IndexCreated)
    listed = [index.name for index in (await adapter.relation_model("main.events")).indexes]
    await adapter.drop_index(DropIndexRequest(node_id="main.events", name=made.name))

    assert isinstance(blocked, IndexBlocked) and blocked.duplicate_groups == 1
    assert made.name == "events_kind_step_idx" and made.name in listed
    assert (await adapter.relation_model("main.events")).indexes == []


async def test_a_unique_key_is_added_in_place_after_a_count(adapter: DuckdbAdapter) -> None:
    blocked = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id="main.events", constraint={"kind": "unique", "columns": ["kind"]}
        )
    )
    made = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id="main.events", constraint={"kind": "unique", "columns": ["kind", "step"]}
        )
    )
    model = await adapter.relation_model("main.events")

    assert isinstance(blocked, RepeatingValues) and blocked.groups == 1
    assert isinstance(made, ConstraintCreated)
    assert any(isinstance(one, UniqueConstraint) for one in model.constraints)


async def test_what_duckdb_cannot_do_to_constraints_is_refused_with_why(
    adapter: DuckdbAdapter,
) -> None:
    with pytest.raises(ValueError, match="foreign key"):
        await adapter.create_constraint(
            CreateConstraintRequest(
                node_id="main.events",
                constraint={
                    "kind": "foreign_key",
                    "columns": ["step"],
                    "target_node_id": "main.labels",
                    "target_columns": ["id"],
                },
            )
        )
    with pytest.raises(ValueError, match="cannot drop a constraint"):
        await adapter.drop_constraint(
            DropConstraintRequest(node_id="main.items", name="items_name_price_key")
        )


# --- The designer (D397) ----------------------------------------------------


def _definition(name: str = "made", **extra: Any) -> TableDefinition:
    raw: dict[str, Any] = {
        "name": name,
        "comment": "Made by the designer",
        "columns": [
            {"id": "c1", "name": "id", "type": {"code": "bigint"}, "not_null": True,
             "generation": {"kind": "identity", "start": 100, "increment": 5}},
            {"id": "c2", "name": "label", "type": {"code": "text"}, "not_null": True,
             "collation": "nocase", "generation": {"kind": "literal", "value": "it's"},
             "comment": "What it is called"},
            {"id": "c3", "name": "price", "type": {"code": "decimal", "precision": 10, "scale": 2},
             "generation": {"kind": "literal", "value": "1.5"}},
            {"id": "c4", "name": "made_at", "type": {"code": "timestamptz"},
             "generation": {"kind": "expression", "expression": {"kind": "call", "function": "now"}}},
            {"id": "c5", "name": "label_id", "type": {"code": "integer"}},
            {"id": "c6", "name": "loud", "type": {"code": "text"},
             "generation": {"kind": "generated", "expression": {
                 "kind": "call", "function": "upper", "arguments": [{"kind": "column", "column_id": "c2"}]}}},
            {"id": "c7", "name": "tags", "type": {"code": "text", "dimensions": 1}},
        ],
        "primary_key": {"column_ids": ["c1"]},
        "unique_constraints": [{"id": "u1", "column_ids": ["c2"]}],
        "checks": [{"id": "k1", "expression": {
            "kind": "compare", "operator": "gte",
            "left": {"kind": "column", "column_id": "c3"},
            "right": {"kind": "literal", "value_kind": "number", "text": "0"}}}],
        "foreign_keys": [{"id": "f1", "column_ids": ["c5"], "target_node_id": "main.labels",
                          "target_columns": ["id"], "on_delete": "restrict"}],
        "indexes": [{"id": "i1", "keys": [{"kind": "column", "column_id": "c3", "direction": "desc"}],
                     "method": "art"}],
    }
    raw.update(extra)
    return TableDefinition.model_validate(raw)


async def _create(adapter: DuckdbAdapter, definition: TableDefinition, fingerprint: str) -> None:
    action = adapter.action("create_table")
    assert isinstance(action, TakesParams)
    await action.perform(
        "main", {"definition": definition.model_dump(mode="json"), "fingerprint": fingerprint}
    )


async def test_a_schema_offers_the_designer_with_duckdbs_vocabulary(adapter: DuckdbAdapter) -> None:
    offered = await adapter.table_design_options("main")
    refused = await adapter.table_design_options("main.items")

    assert offered.supported
    assert [one.code for one in offered.reference_actions] == ["no_action", "restrict"]
    assert offered.collations == ["NOCASE", "NOACCENT", "NFC"]
    assert offered.abilities.partial_indexes is False
    assert offered.abilities.comments is True
    assert refused.supported is False


async def test_a_designed_table_is_planned_and_created_whole(
    adapter: DuckdbAdapter, home: Path
) -> None:
    plan = await adapter.plan_table(TablePlanRequest(node_id="main", definition=_definition()))
    assert plan.problems == [], plan.problems
    assert plan.fingerprint is not None
    sql = [statement.sql for statement in plan.statements]
    assert sql[0] == 'CREATE SEQUENCE "main"."made_id_seq" START 100 INCREMENT BY 5'
    assert "DEFAULT nextval('main.made_id_seq')" in sql[1]
    assert "GENERATED ALWAYS AS (upper(\"label\")) VIRTUAL" in sql[1]
    assert any("COMMENT ON COLUMN" in one for one in sql)
    assert plan.warnings

    await _create(adapter, _definition(), plan.fingerprint)

    model = await adapter.relation_model("main.made")
    assert model.comment == "Made by the designer"
    assert any(isinstance(one, ForeignKey) for one in model.constraints)
    connection = duckdb.connect(str(home / FILE))
    try:
        connection.execute("INSERT INTO made (label_id) VALUES (1)")
        connection.execute("INSERT INTO made (label, label_id) VALUES ('second', 2)")
        rows = connection.execute(
            "SELECT id, label, CAST(price AS VARCHAR), loud FROM made ORDER BY id"
        ).fetchall()
    finally:
        connection.close()
    # The identity counts from 100 by 5; the defaults and the generated column fill in.
    assert rows == [(100, "it's", "1.50", "IT'S"), (105, "second", "1.50", "SECOND")]


async def test_what_duckdb_lacks_is_a_problem_on_its_object(adapter: DuckdbAdapter) -> None:
    definition = _definition(
        persistence="unlogged",
        foreign_keys=[{"id": "f1", "column_ids": ["c5"], "target_node_id": "main.labels",
                       "target_columns": ["id"], "on_delete": "cascade"}],
        indexes=[{"id": "i1", "keys": [{"kind": "column", "column_id": "c3"}], "method": "art",
                  "predicate": {"kind": "null_test", "negated": True,
                                "operand": {"kind": "column", "column_id": "c3"}}}],
    )
    plan = await adapter.plan_table(TablePlanRequest(node_id="main", definition=definition))

    fields = {(problem.object_id, problem.field) for problem in plan.problems}
    assert (None, "persistence") in fields
    assert ("f1", "on_delete") in fields
    assert ("i1", "predicate") in fields
    assert plan.statements == []


async def test_a_default_duckdb_could_not_read_is_a_problem_while_planning(
    adapter: DuckdbAdapter,
) -> None:
    raw = _definition().model_dump(mode="json")
    raw["columns"][2]["generation"] = {"kind": "literal", "value": "cheap"}
    definition = TableDefinition.model_validate(raw)

    plan = await adapter.plan_table(TablePlanRequest(node_id="main", definition=definition))

    assert [(problem.object_id, problem.field) for problem in plan.problems] == [("c3", "generation")]


async def test_a_changed_plan_is_not_created(adapter: DuckdbAdapter) -> None:
    with pytest.raises(ActionRefused):
        await _create(adapter, _definition(), "not-the-plan")


# --- A table made from rows -------------------------------------------------


async def test_a_table_is_made_with_its_rows_in_one_go(adapter: DuckdbAdapter) -> None:
    options = await adapter.new_relation_options("sales\\.eu")
    made = await adapter.create_relation(
        CreateRelationRequest(
            parent_node_id="sales\\.eu",
            name="loaded",
            columns=[
                NewColumn(name="day", type_code="date"),
                NewColumn(name="amount", type_code="decimal"),
            ],
            rows=[["2026-01-02", "1.5"], ["2026-01-03", None]],
        )
    )
    page = await adapter.fetch(FetchRequest(node_id="sales\\.eu.loaded"))

    assert options.supported and options.text_type == "text"
    assert isinstance(made, RelationCreated) and made.inserted == 2
    assert page.rows == [["2026-01-02", "1.500"], ["2026-01-03", None]]
    with pytest.raises(ValueError):
        await adapter.create_relation(
            CreateRelationRequest(
                parent_node_id="main",
                name="refused",
                columns=[NewColumn(name="day", type_code="date")],
                rows=[["soon"]],
            )
        )
    assert "refused" not in {node.name for node in await adapter.list_children("main")}
