"""A MySQL table designed and planned, then created; a table made from rows (D236).

On MySQL and MariaDB.
"""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.adapters.actions import ActionRefused, TakesParams
from app.adapters.fetch import FetchRequest
from app.adapters.mysql import ids
from app.adapters.mysql.adapter import MysqlAdapter
from app.adapters.relation_changes import CreateRelationRequest, NewColumn
from app.adapters.table_design import TableDefinition, TablePlanRequest
from tests.adapters.mysql_fixture import TARGETS, Target, run

DATABASE = "dp_design"
NODE = ids.database_id(DATABASE)


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await run(
        chosen,
        f"DROP DATABASE IF EXISTS {DATABASE}",
        f"CREATE DATABASE {DATABASE}",
        f"CREATE TABLE {DATABASE}.makers (id INT PRIMARY KEY)",
    )
    yield chosen
    await run(chosen, f"DROP DATABASE IF EXISTS {DATABASE}")


def _name() -> str:
    return f"t_{uuid.uuid4().hex[:8]}"


def _definition(name: str, **extra: Any) -> TableDefinition:
    """A table with most of what a design can hold."""
    raw: dict[str, Any] = {
        "name": name,
        "comment": "made by a test",
        "columns": [
            {"id": "c1", "name": "id", "type": {"code": "integer"}, "not_null": True,
             "generation": {"kind": "identity", "start": 100}},
            {"id": "c2", "name": "label", "type": {"code": "varchar", "length": 40}, "not_null": True,
             "generation": {"kind": "literal", "value": "it's a \\ backslash"}, "comment": "shown"},
            {"id": "c3", "name": "price", "type": {"code": "decimal", "precision": 10, "scale": 2}},
            {"id": "c4", "name": "made", "type": {"code": "timestamp"},
             "generation": {"kind": "expression", "expression": {"kind": "call", "function": "now"}}},
            {"id": "c5", "name": "maker_id", "type": {"code": "integer"}},
            {"id": "c6", "name": "loud", "type": {"code": "varchar", "length": 40},
             "generation": {"kind": "generated", "expression": {
                 "kind": "call", "function": "upper", "arguments": [{"kind": "column", "column_id": "c2"}]}}},
        ],
        "primary_key": {"column_ids": ["c1"]},
        "unique_constraints": [{"id": "u1", "column_ids": ["c2"]}],
        "checks": [{"id": "k1", "expression": {
            "kind": "compare", "operator": "gte",
            "left": {"kind": "column", "column_id": "c3"},
            "right": {"kind": "literal", "value_kind": "number", "text": "0"}}}],
        "foreign_keys": [{"id": "f1", "column_ids": ["c5"],
                          "target_node_id": ids.relation_id(DATABASE, "makers"),
                          "target_columns": ["id"], "on_delete": "set_null"}],
        "indexes": [{"id": "i1", "keys": [{"kind": "column", "column_id": "c3", "direction": "desc"}]}],
    }
    raw.update(extra)
    return TableDefinition.model_validate(raw)


async def _create(adapter: MysqlAdapter, definition: TableDefinition, fingerprint: str) -> None:
    action = adapter.action("create_table")
    assert isinstance(action, TakesParams)
    await action.perform(
        NODE, {"definition": definition.model_dump(mode="json"), "fingerprint": fingerprint}
    )


async def test_a_database_offers_the_designer_and_the_server_s_own_do_not(target: Target) -> None:
    adapter = target.adapter()

    offered = await adapter.table_design_options(NODE)
    refused = await adapter.table_design_options(ids.database_id("mysql"))

    assert offered.supported
    assert {option.code for option in offered.types} >= {"integer", "varchar", "json", "timestamp"}
    assert [choice.code for choice in offered.persistence_options] == ["permanent"]
    assert [choice.code for choice in offered.match_modes] == ["simple"]
    assert "set_default" not in {choice.code for choice in offered.reference_actions}
    assert "utf8mb4_bin" in offered.collations
    assert not refused.supported and refused.reason
    assert [action.name for action in await adapter.available(NODE)] == ["create_table"]
    assert await adapter.available(ids.database_id("mysql")) == []


async def test_a_design_becomes_one_statement_and_then_one_table(target: Target) -> None:
    adapter = target.adapter()
    name = _name()
    definition = _definition(name)

    plan = await adapter.plan_table(TablePlanRequest(node_id=NODE, definition=definition))

    assert plan.problems == []
    [statement] = plan.statements
    assert statement.sql.startswith(f"CREATE TABLE `{DATABASE}`.`{name}`")
    for part in ("AUTO_INCREMENT", "PRIMARY KEY (`id`)", "UNIQUE (`label`)", "CHECK", "FOREIGN KEY",
                 "ON DELETE SET NULL", "DESC", "AUTO_INCREMENT=100", "GENERATED ALWAYS AS (UPPER(`label`)) STORED"):
        assert part in statement.sql, part

    await _create(adapter, definition, plan.fingerprint)
    model = await adapter.relation_model(ids.relation_id(DATABASE, name))
    columns = {column.name: column for column in model.columns}
    kinds = sorted(constraint.kind for constraint in model.constraints)

    assert columns["id"].identity == "by_default"
    assert columns["label"].comment == "shown"
    assert "it''s a \\ backslash" in (columns["label"].default or "") or "it''s a \\\\ backslash" in (
        columns["label"].default or ""
    )
    assert columns["loud"].generated is not None
    assert model.comment == "made by a test"
    assert kinds == ["check", "foreign_key", "primary_key", "unique"]


async def test_the_literal_default_is_stored_as_typed(target: Target) -> None:
    adapter = target.adapter()
    name = _name()
    definition = _definition(name)
    plan = await adapter.plan_table(TablePlanRequest(node_id=NODE, definition=definition))
    await _create(adapter, definition, plan.fingerprint)

    await run(target, f"INSERT INTO {DATABASE}.{name} (price) VALUES (1)")
    page = await adapter.fetch(FetchRequest(node_id=ids.relation_id(DATABASE, name)))

    assert page.rows[0][1] == "it's a \\ backslash"
    assert page.rows[0][0] == "100"


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"persistence": "unlogged"}, "persistence"),
        ({"foreign_keys": [{"id": "f1", "column_ids": ["c5"], "target_node_id": "dp_design.makers",
                            "target_columns": ["id"], "deferrable": True}]}, "deferrable"),
        ({"foreign_keys": [{"id": "f1", "column_ids": ["c5"], "target_node_id": "dp_design.makers",
                            "target_columns": ["id"], "on_delete": "set_default"}]}, "on_delete"),
        ({"indexes": [{"id": "i1", "keys": [{"kind": "column", "column_id": "c3"}], "include_column_ids": ["c5"]}]},
         "include_column_ids"),
        ({"indexes": [{"id": "i1", "keys": [{"kind": "column", "column_id": "c3", "nulls": "last"}]}]}, "nulls"),
        ({"unique_constraints": [{"id": "u1", "column_ids": ["c2"], "nulls_not_distinct": True}]},
         "nulls_not_distinct"),
    ],
)
async def test_what_mysql_has_not_got_is_named_on_its_object(
    target: Target, change: dict[str, Any], field: str
) -> None:
    plan = await target.adapter().plan_table(
        TablePlanRequest(node_id=NODE, definition=_definition(_name(), **change))
    )

    assert plan.statements == [] and plan.fingerprint == ""
    assert field in [problem.field for problem in plan.problems]


async def test_an_identity_must_lead_a_key_and_step_by_one(target: Target) -> None:
    adapter = target.adapter()
    keyless = _definition(_name(), primary_key=None, unique_constraints=[])
    stepping = _definition(_name())
    stepping.columns[0].generation.increment = 5  # type: ignore[union-attr]  # an identity, built above

    first = await adapter.plan_table(TablePlanRequest(node_id=NODE, definition=keyless))
    second = await adapter.plan_table(TablePlanRequest(node_id=NODE, definition=stepping))

    assert any(problem.object_id == "c1" for problem in first.problems)
    assert any(problem.field == "generation" for problem in second.problems)


async def test_a_name_in_use_is_a_conflict_and_a_moved_plan_is_refused(target: Target) -> None:
    adapter = target.adapter()
    taken = await adapter.plan_table(
        TablePlanRequest(node_id=NODE, definition=_definition("MAKERS"))
    )
    assert [problem.kind for problem in taken.problems] == ["conflict"]

    with pytest.raises(ActionRefused):
        await _create(adapter, _definition(_name()), "0" * 64)


async def test_a_table_is_made_from_rows_or_names_the_values_it_cannot_hold(target: Target) -> None:
    adapter = target.adapter()
    name = _name()
    columns = [NewColumn(name="n", type_code="integer"), NewColumn(name="s", type_code="text")]

    refused = await adapter.create_relation(
        CreateRelationRequest(parent_node_id=NODE, name=name, columns=columns, rows=[["1", "a"], ["two", "b"]])
    )
    nothing = await adapter.list_children(NODE)
    made = await adapter.create_relation(
        CreateRelationRequest(parent_node_id=NODE, name=name, columns=columns, rows=[["1", "a"], ["2", None]])
    )

    assert refused.kind == "rejected"
    assert [(cell.row, cell.column) for cell in refused.cells] == [(1, "n")]  # type: ignore[union-attr]  # rejected
    assert name not in {node.name for node in nothing}
    assert made.kind == "created" and made.inserted == 2  # type: ignore[union-attr]  # created
    with pytest.raises(ValueError):
        await adapter.create_relation(
            CreateRelationRequest(parent_node_id=NODE, name=name, columns=columns, rows=[])
        )
