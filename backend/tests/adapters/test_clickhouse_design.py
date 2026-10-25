"""A ClickHouse table designed and planned, then created; a table made from rows (D274)."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.adapters.actions import ActionRefused, TakesParams
from app.adapters.clickhouse.adapter import ClickhouseAdapter
from app.adapters.database_ids import database_id, relation_id
from app.adapters.fetch import FetchRequest
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewColumn,
    RelationCreated,
)
from app.adapters.table_design import TableDefinition, TablePlanRequest
from app.adapters.update import ValuesRejected
from tests.adapters.clickhouse_fixture import adapter, run
from tests.utils.services import CLICKHOUSE

DATABASE = "dp_design"
NODE = database_id(DATABASE)


@pytest.fixture(scope="module")
async def server() -> AsyncIterator[None]:
    CLICKHOUSE.require()
    await run(f"DROP DATABASE IF EXISTS {DATABASE}", f"CREATE DATABASE {DATABASE}")
    yield
    await run(f"DROP DATABASE IF EXISTS {DATABASE}")


def _name() -> str:
    return f"t_{uuid.uuid4().hex[:8]}"


def _definition(name: str, **extra: Any) -> TableDefinition:
    """A table with most of what a ClickHouse design can hold."""
    raw: dict[str, Any] = {
        "name": name,
        "comment": "made by a test",
        "columns": [
            {"id": "c1", "name": "id", "type": {"code": "uint64"}, "not_null": True},
            {"id": "c2", "name": "label", "type": {"code": "text"}, "not_null": True,
             "generation": {"kind": "literal", "value": "it's a \\ backslash"}, "comment": "shown"},
            {"id": "c3", "name": "price", "type": {"code": "decimal", "precision": 10, "scale": 2}},
            {"id": "c4", "name": "made", "type": {"code": "datetime"}, "not_null": True,
             "generation": {"kind": "expression", "expression": {"kind": "call", "function": "now"}}},
            {"id": "c5", "name": "tags", "type": {"code": "repeated_text", "dimensions": 1}},
            {"id": "c6", "name": "loud", "type": {"code": "text"}, "not_null": True,
             "generation": {"kind": "generated", "expression": {
                 "kind": "call", "function": "upper", "arguments": [{"kind": "column", "column_id": "c2"}]}}},
            {"id": "c7", "name": "at", "type": {"code": "datetime64", "precision": 6}},
        ],
        "primary_key": {"column_ids": ["c1"]},
        "checks": [{"id": "k1", "expression": {
            "kind": "compare", "operator": "gte",
            "left": {"kind": "column", "column_id": "c3"},
            "right": {"kind": "literal", "value_kind": "number", "text": "0"}}}],
        "indexes": [{"id": "i1", "method": "bloom_filter", "keys": [{"kind": "column", "column_id": "c2"}]}],
    }
    raw.update(extra)
    return TableDefinition.model_validate(raw)


async def _create(source: ClickhouseAdapter, definition: TableDefinition, fingerprint: str) -> None:
    action = source.action("create_table")
    assert isinstance(action, TakesParams)
    await action.perform(
        NODE, {"definition": definition.model_dump(mode="json"), "fingerprint": fingerprint}
    )


@pytest.mark.usefixtures("server")
async def test_a_database_offers_the_designer_and_the_server_s_own_do_not() -> None:
    source = adapter()

    offered = await source.table_design_options(NODE)
    refused = await source.table_design_options(database_id("system"))

    assert offered.supported
    assert {option.code for option in offered.types} >= {"uint64", "text", "decimal", "datetime64"}
    assert not any(option.identity_supported for option in offered.types)
    assert not offered.reference_actions and not offered.hypertable.offered
    assert not refused.supported and refused.reason
    assert "create_table" in [action.name for action in await source.available(NODE)]
    assert "create_table" not in [action.name for action in await source.available(database_id("system"))]


@pytest.mark.usefixtures("server")
async def test_a_plan_is_one_create_table_with_its_sorting_key() -> None:
    source = adapter()
    name = _name()

    plan = await source.plan_table(TablePlanRequest(node_id=NODE, definition=_definition(name)))

    assert plan.problems == []
    [statement] = plan.statements
    sql = statement.sql
    assert sql.startswith(f"CREATE TABLE `{DATABASE}`.`{name}` (")
    assert "`label` String DEFAULT 'it\\'s a \\\\ backslash' COMMENT 'shown'" in sql
    assert "`price` Nullable(Decimal(10, 2))" in sql
    assert "`made` DateTime('UTC') DEFAULT now()" in sql
    assert "`tags` Array(LowCardinality(String))" in sql
    assert "`loud` String MATERIALIZED upperUTF8(`label`)" in sql
    assert "`at` Nullable(DateTime64(6, 'UTC'))" in sql
    assert f"INDEX `{name}_label_idx` (`label`) TYPE bloom_filter GRANULARITY 1" in sql
    assert f"CONSTRAINT `{name}_chk` CHECK (`price` >= 0)" in sql
    assert sql.endswith("ENGINE = MergeTree\nORDER BY (`id`)\nCOMMENT 'made by a test'")
    # The primary key is said to be what it is in ClickHouse (D269).
    assert any("does not stop two rows" in warning for warning in plan.warnings)
    assert any('"tags" cannot hold NULL' in warning for warning in plan.warnings)


@pytest.mark.usefixtures("server")
async def test_what_clickhouse_has_not_got_is_a_problem_on_its_object() -> None:
    source = adapter()
    definition = _definition(
        _name(),
        unique_constraints=[{"id": "u1", "column_ids": ["c2"]}],
        foreign_keys=[{"id": "f1", "column_ids": ["c1"], "target_node_id": relation_id(DATABASE, "x"),
                       "target_columns": ["id"]}],
        primary_key={"column_ids": ["c3"]},
        columns=[
            {"id": "c1", "name": "id", "type": {"code": "uint64"}, "not_null": True,
             "generation": {"kind": "identity"}},
            {"id": "c2", "name": "label", "type": {"code": "text"}, "collation": "utf8mb4_bin"},
            {"id": "c3", "name": "price", "type": {"code": "decimal"}},
        ],
        checks=[],
        indexes=[{"id": "i1", "method": "minmax", "unique": True, "keys": [{"kind": "column", "column_id": "c3"}]}],
    )

    plan = await source.plan_table(TablePlanRequest(node_id=NODE, definition=definition))

    by_object = {(problem.object_id, problem.field) for problem in plan.problems}
    assert ("u1", None) in by_object and ("f1", None) in by_object
    assert ("c1", "generation") in by_object
    assert ("c2", "collation") in by_object
    assert ("c3", "not_null") in by_object
    assert ("i1", "unique") in by_object
    assert plan.statements == [] and plan.fingerprint == ""


@pytest.mark.usefixtures("server")
async def test_a_reviewed_plan_is_created_and_a_changed_one_refused() -> None:
    source = adapter()
    name = _name()
    definition = _definition(name)
    plan = await source.plan_table(TablePlanRequest(node_id=NODE, definition=definition))

    with pytest.raises(ActionRefused):
        await _create(source, definition, "0" * 64)
    await _create(source, definition, plan.fingerprint)

    model = await source.relation_model(relation_id(DATABASE, name))
    columns = {column.name: column for column in model.columns}
    assert columns["label"].default == "'it\\'s a \\\\ backslash'"
    assert columns["loud"].generated == "upperUTF8(label)"
    assert [constraint.name for constraint in model.constraints] == [f"{name}_chk"]
    await run(f"INSERT INTO {DATABASE}.{name} (id, price) VALUES (1, 2.5)")
    page = await source.fetch(FetchRequest(node_id=relation_id(DATABASE, name)))
    names = [column.name for column in page.columns]
    row = dict(zip(names, page.rows[0], strict=True))
    assert (row["label"], row["loud"], row["price"]) == ("it's a \\ backslash", "IT'S A \\ BACKSLASH", "2.50")
    with pytest.raises(ActionRefused):
        await _create(source, definition, plan.fingerprint)


@pytest.mark.usefixtures("server")
async def test_a_table_is_made_from_rows_or_not_at_all() -> None:
    source = adapter()
    name = _name()
    columns = [NewColumn(name="n", type_code="int32"), NewColumn(name="t", type_code="text")]

    refused = await source.create_relation(
        CreateRelationRequest(parent_node_id=NODE, name=name, columns=columns, rows=[["1", "a"], ["x", "b"]])
    )
    made = await source.create_relation(
        CreateRelationRequest(parent_node_id=NODE, name=name, columns=columns, rows=[["1", "a"], [None, "b"]])
    )

    assert isinstance(refused, ValuesRejected)
    assert [(cell.row, cell.column) for cell in refused.cells] == [(1, "n")]
    assert isinstance(made, RelationCreated) and made.inserted == 2
    page = await source.fetch(FetchRequest(node_id=relation_id(DATABASE, name)))
    assert sorted(page.rows, key=lambda row: row[1] or "") == [["1", "a"], [None, "b"]]
