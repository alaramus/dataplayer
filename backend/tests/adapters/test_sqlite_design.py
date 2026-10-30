"""A SQLite table designed and planned, then created; a table made from rows (D256).

Every test writes its own file under a temporary home.
"""

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from app.adapters.actions import ActionRefused, TakesParams
from app.adapters.fetch import FetchRequest
from app.adapters.relation import ForeignKey
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)
from app.adapters.sqlite.adapter import SqliteAdapter
from app.adapters.sqlite.options import SqliteOptions
from app.adapters.table_design import TableDefinition, TablePlanRequest
from tests.adapters.sqlite_fixture import FILE, build


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


@pytest.fixture
def adapter(home: Path) -> SqliteAdapter:
    return SqliteAdapter(SqliteOptions(path=FILE), home)


def _definition(name: str = "made", **extra: Any) -> TableDefinition:
    """A table with most of what a design can hold."""
    raw: dict[str, Any] = {
        "name": name,
        "columns": [
            {"id": "c1", "name": "id", "type": {"code": "integer"},
             "generation": {"kind": "identity", "start": 100}},
            {"id": "c2", "name": "label", "type": {"code": "varchar", "length": 40}, "not_null": True,
             "collation": "NOCASE", "generation": {"kind": "literal", "value": "it's"}},
            {"id": "c3", "name": "price", "type": {"code": "decimal", "precision": 10, "scale": 2}},
            {"id": "c4", "name": "made_at", "type": {"code": "datetime"},
             "generation": {"kind": "expression", "expression": {"kind": "call", "function": "now"}}},
            {"id": "c5", "name": "label_id", "type": {"code": "integer"}},
            {"id": "c6", "name": "loud", "type": {"code": "text"},
             "generation": {"kind": "generated", "expression": {
                 "kind": "call", "function": "upper", "arguments": [{"kind": "column", "column_id": "c2"}]}}},
        ],
        "primary_key": {"column_ids": ["c1"]},
        "unique_constraints": [{"id": "u1", "column_ids": ["c2"]}],
        "checks": [{"id": "k1", "expression": {
            "kind": "compare", "operator": "gte",
            "left": {"kind": "column", "column_id": "c3"},
            "right": {"kind": "literal", "value_kind": "number", "text": "0"}}}],
        "foreign_keys": [{"id": "f1", "column_ids": ["c5"], "target_node_id": "main.labels",
                          "target_columns": ["id"], "on_delete": "set_null", "deferrable": True}],
        "indexes": [{"id": "i1", "keys": [{"kind": "column", "column_id": "c3", "direction": "desc"}],
                     "predicate": {"kind": "null_test", "negated": True,
                                   "operand": {"kind": "column", "column_id": "c3"}}}],
    }
    raw.update(extra)
    return TableDefinition.model_validate(raw)


async def _create(adapter: SqliteAdapter, definition: TableDefinition, fingerprint: str) -> None:
    action = adapter.action("create_table")
    assert isinstance(action, TakesParams)
    await action.perform(
        "main", {"definition": definition.model_dump(mode="json"), "fingerprint": fingerprint}
    )


async def test_main_offers_the_designer(adapter: SqliteAdapter) -> None:
    offered = await adapter.table_design_options("main")

    assert offered.supported
    assert {option.code for option in offered.types} >= {"integer", "text", "blob", "json"}
    assert offered.collations == ["BINARY", "NOCASE", "RTRIM"]
    assert "set_default" in {choice.code for choice in offered.reference_actions}
    assert offered.hypertable.offered is False
    # SQLite keeps no comments and defers a foreign key but never a unique one.
    assert offered.abilities.partial_indexes and not offered.abilities.comments
    assert offered.abilities.deferrable_foreign_keys and not offered.abilities.deferrable_unique
    assert "create_table" in [action.name for action in await adapter.available("main")]
    assert "create_table" not in [action.name for action in await adapter.available("main.items")]


async def test_a_design_becomes_a_table_and_its_indexes(adapter: SqliteAdapter, home: Path) -> None:
    definition = _definition()

    plan = await adapter.plan_table(TablePlanRequest(node_id="main", definition=definition))

    assert plan.problems == []
    table, index, counter = plan.statements
    for part in (
        '"id" INTEGER PRIMARY KEY AUTOINCREMENT',
        '"label" VARCHAR(40) COLLATE NOCASE NOT NULL DEFAULT \'it\'\'s\'',
        '"made_at" DATETIME DEFAULT (CURRENT_TIMESTAMP)',
        'GENERATED ALWAYS AS (upper("label")) STORED',
        'CONSTRAINT "made_label_key" UNIQUE ("label")',
        'CONSTRAINT "made_check" CHECK (("price" >= 0))',
        "ON DELETE SET NULL DEFERRABLE INITIALLY IMMEDIATE",
    ):
        assert part in table.sql, part
    assert index.sql == (
        'CREATE INDEX "main"."made_price_idx" ON "made" ("price" DESC) WHERE ("price" IS NOT NULL)'
    )
    assert "VALUES ('made', 99)" in counter.sql

    await _create(adapter, definition, plan.fingerprint)

    model = await adapter.relation_model("main.made")
    assert [column.name for column in model.columns][:2] == ["id", "label"]
    assert any(isinstance(c, ForeignKey) and c.target_node_id == "main.labels" for c in model.constraints)
    connection = sqlite3.connect(home / FILE)
    try:
        connection.execute("INSERT INTO made (label) VALUES ('first')")
        assert connection.execute("SELECT id, loud FROM made").fetchall() == [(100, "FIRST")]
    finally:
        connection.close()


async def test_what_sqlite_lacks_is_named_on_the_object(adapter: SqliteAdapter) -> None:
    definition = _definition(
        persistence="unlogged",
        unique_constraints=[{"id": "u1", "column_ids": ["c2"], "nulls_not_distinct": True}],
        indexes=[{"id": "i1", "keys": [{"kind": "column", "column_id": "c3", "nulls": "first"}]}],
    )

    plan = await adapter.plan_table(TablePlanRequest(node_id="main", definition=definition))

    places = {(problem.object_id, problem.field) for problem in plan.problems}
    assert (None, "persistence") in places
    assert ("u1", "nulls_not_distinct") in places
    assert ("i1", "nulls") in places
    assert plan.statements == []


async def test_an_identity_is_the_whole_primary_key(adapter: SqliteAdapter) -> None:
    definition = _definition(
        columns=[
            {"id": "c1", "name": "id", "type": {"code": "integer"},
             "generation": {"kind": "identity", "generated": "always"}},
            {"id": "c2", "name": "other", "type": {"code": "integer"}, "not_null": True},
        ],
        primary_key={"column_ids": ["c1", "c2"]},
        unique_constraints=[],
        checks=[],
        foreign_keys=[],
        indexes=[],
    )

    plan = await adapter.plan_table(TablePlanRequest(node_id="main", definition=definition))

    messages = [problem.message for problem in plan.problems]
    assert "An identity column is SQLite's rowid, so it is the whole primary key" in messages
    assert "SQLite takes a value written into its rowid; it cannot be ALWAYS" in messages


async def test_a_taken_name_is_a_conflict_and_a_changed_plan_is_refused(
    adapter: SqliteAdapter,
) -> None:
    taken = await adapter.plan_table(
        TablePlanRequest(node_id="main", definition=_definition("Items"))
    )
    plan = await adapter.plan_table(TablePlanRequest(node_id="main", definition=_definition()))

    assert [problem.kind for problem in taken.problems] == ["conflict"]
    with pytest.raises(ActionRefused):
        await _create(adapter, _definition(), "0" * 64)
    await _create(adapter, _definition(), plan.fingerprint)


async def test_a_table_is_made_from_rows_in_one_transaction(adapter: SqliteAdapter) -> None:
    columns = [NewColumn(name="n", type_code="integer"), NewColumn(name="t", type_code="text")]

    made = await adapter.create_relation(
        CreateRelationRequest(parent_node_id="main", name="fresh", columns=columns, rows=[["1", "a"], ["2", None]])
    )
    page = await adapter.fetch(FetchRequest(node_id="main.fresh"))

    assert isinstance(made, RelationCreated) and made.inserted == 2
    assert page.rows == [["1", "a"], ["2", None]]
    with pytest.raises(ValueError):
        await adapter.create_relation(
            CreateRelationRequest(parent_node_id="main", name="fresh", columns=columns, rows=[])
        )
