import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from app.adapters.actions import (
    Action,
    ActionPreview,
    ActionRefused,
    ActionResult,
    Previews,
    PreviewsSet,
    TakesFile,
    TakesNodeSet,
    TakesParams,
    action_availability,
)
from app.adapters.fetch import FetchRequest
from app.adapters.postgres import actions as postgres_actions
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


def test_rename_marks_the_field_as_the_current_node_name() -> None:
    relation = postgres_actions.RenameRelationParams.model_json_schema()["properties"]
    schema = postgres_actions.RenameSchemaParams.model_json_schema()["properties"]

    assert relation["new_name"]["x-ui-purpose"] == "node-name"
    assert schema["new_name"]["x-ui-purpose"] == "node-name"


@pytest.mark.parametrize(
    ("action_type", "scope", "multiple"),
    [
        (postgres_actions.CreateSchema, "level", False),
        (postgres_actions.RenameSchema, "group", False),
        (postgres_actions.DropSchema, "group", False),
        (postgres_actions.RenameRelation, "node", False),
        (postgres_actions.MoveRelation, "node", True),
        (postgres_actions.DropRelation, "node", True),
        (postgres_actions.DescribeModel, "node", True),
        (postgres_actions.CreateTable, "destination", False),
        (postgres_actions.LoadCsv, "destination", False),
    ],
)
def test_postgres_action_target_contract(
    action_type: type[Action[Any]], scope: str, multiple: bool
) -> None:
    assert action_type.acts_on == scope
    assert action_type.bulk is multiple


async def test_move_accepts_several_relations_and_reports_each_replacement(
    schema: str,
) -> None:
    source = adapter()
    target = f"move_batch_{uuid.uuid4().hex}"
    await run(f'CREATE SCHEMA "{target}"')  # noqa: S608 -- generated test schema.
    try:
        nodes = [f"{schema}.customers", f"{schema}.regions"]
        action = source.action("move_relation")
        offers = [await source.available(node) for node in nodes]
        assert action_availability(action, nodes, offers).applicable
        assert isinstance(action, TakesParams)
        results = [
            await action.perform(node, {"target_schema": target}) for node in nodes
        ]
        assert [
            result.replacement.old_node_id
            for result in results
            if result.replacement is not None
        ] == nodes
        for name in ("customers", "regions"):
            path = await source.path_to(f"{target}.{name}")
            assert path[-1].name == name
    finally:
        await run(f'DROP SCHEMA "{target}" CASCADE')  # noqa: S608 -- generated test schema.


async def test_rename_is_offered_only_for_non_system_relations(schema: str) -> None:
    source = adapter()

    table = await source.available(f"{schema}.customers")
    view = await source.available(f"{schema}.rich_customers")
    system = await source.available("pg_catalog.pg_class")

    assert "rename_relation" in {action.name for action in table}
    assert "rename_relation" in {action.name for action in view}
    assert "move_relation" in {action.name for action in table}
    assert "move_relation" in {action.name for action in view}
    assert system == []


async def test_renames_a_view_with_a_source_issued_replacement(schema: str) -> None:
    source = adapter()
    action = source.action("rename_relation")
    assert isinstance(action, TakesParams)

    result = await action.perform(
        f"{schema}.rich_customers", {"new_name": "valuable_customers"}
    )

    assert result.reload_node_ids == [schema]
    assert result.replacement is not None
    assert result.replacement.old_node_id == f"{schema}.rich_customers"
    assert result.replacement.new_node_id == f"{schema}.valuable_customers"
    path = await source.path_to(result.replacement.new_node_id)
    assert path[-1].name == "valuable_customers"


async def test_renames_a_materialized_view(schema: str) -> None:
    await run(
        f"CREATE MATERIALIZED VIEW {schema}.customer_snapshot "  # noqa: S608 -- fixture-owned schema.
        f"AS SELECT id, name FROM {schema}.customers"  # noqa: S608 -- fixture-owned schema.
    )
    source = adapter()
    action = source.action("rename_relation")
    assert isinstance(action, TakesParams)

    result = await action.perform(
        f"{schema}.customer_snapshot", {"new_name": "renamed_snapshot"}
    )

    assert result.replacement is not None
    path = await source.path_to(result.replacement.new_node_id)
    assert path[-1].name == "renamed_snapshot"


async def test_refuses_a_relation_name_that_is_already_taken(schema: str) -> None:
    source = adapter()
    action = source.action("rename_relation")
    assert isinstance(action, TakesParams)

    with pytest.raises(ActionRefused, match="already has"):
        await action.perform(f"{schema}.customers", {"new_name": "regions"})


async def test_rejects_a_name_postgres_would_truncate(schema: str) -> None:
    source = adapter()
    action = source.action("rename_relation")
    assert isinstance(action, TakesParams)

    with pytest.raises(ValueError, match="63 bytes"):
        await action.perform(f"{schema}.customers", {"new_name": "x" * 64})


async def test_schema_actions_are_offered_at_the_level_and_on_a_user_schema(
    schema: str,
) -> None:
    source = adapter()

    root = await source.available(None)
    user_schema = await source.available(schema)
    system_schema = await source.available("pg_catalog")

    assert [action.name for action in root] == ["create_schema"]
    assert {action.name for action in user_schema} == {
        "rename_schema",
        "load_csv",
        "create_table",
        "drop_schema",
        "describe_model",
    }
    assert system_schema == []


async def test_creates_a_schema_and_names_every_branch_to_refresh() -> None:
    source = adapter()
    name = f"created_{uuid.uuid4().hex}"
    action = source.action("create_schema")
    assert isinstance(action, TakesParams)
    try:
        result = await action.perform(None, {"name": name})

        assert result.reload_node_ids == [None, name]
        assert (await source.path_to(name))[-1].name == name
    finally:
        await run(
            f'DROP SCHEMA IF EXISTS "{name}" CASCADE'  # noqa: S608 -- generated test schema.
        )


async def test_refuses_a_schema_name_that_is_already_taken(schema: str) -> None:
    source = adapter()
    action = source.action("create_schema")
    assert isinstance(action, TakesParams)

    with pytest.raises(ActionRefused) as refused:
        await action.perform(None, {"name": schema})

    assert refused.value.reason == "conflict"


async def test_rejects_a_schema_name_postgres_would_truncate() -> None:
    source = adapter()
    action = source.action("create_schema")
    assert isinstance(action, TakesParams)

    with pytest.raises(ValueError, match="63 bytes"):
        await action.perform(None, {"name": "x" * 64})


async def test_renames_a_schema_with_its_source_issued_identity() -> None:
    source = adapter()
    old = f"old_{uuid.uuid4().hex}"
    new = f"new_{uuid.uuid4().hex}"
    await run(f'CREATE SCHEMA "{old}"')  # noqa: S608 -- generated test schema.
    action = source.action("rename_schema")
    assert isinstance(action, TakesParams)
    try:
        result = await action.perform(old, {"new_name": new})

        assert result.reload_node_ids == [None, old, new]
        assert result.replacement is not None
        assert result.replacement.old_node_id == old
        assert result.replacement.new_node_id == new
        assert (await source.path_to(new))[-1].name == new
    finally:
        await run(
            f'DROP SCHEMA IF EXISTS "{new}" CASCADE'  # noqa: S608 -- generated test schema.
        )
        await run(
            f'DROP SCHEMA IF EXISTS "{old}" CASCADE'  # noqa: S608 -- generated test schema.
        )


async def test_moves_a_relation_and_refreshes_both_schemas(schema: str) -> None:
    source = adapter()
    target = f"target_{uuid.uuid4().hex}"
    relation = f"movable_{uuid.uuid4().hex}"
    await run(f'CREATE SCHEMA "{target}"')  # noqa: S608 -- generated test schema.
    await run(
        f'CREATE TABLE "{schema}"."{relation}" (id integer)'  # noqa: S608 -- generated fixture names.
    )
    action = source.action("move_relation")
    assert isinstance(action, TakesParams)
    try:
        result = await action.perform(
            f"{schema}.{relation}", {"target_schema": target}
        )

        assert result.reload_node_ids == [schema, target]
        assert result.replacement is not None
        assert result.replacement.new_node_id == f"{target}.{relation}"
        moved = (await source.path_to(result.replacement.new_node_id))[-1]
        assert moved.name == relation
    finally:
        await run(
            f'DROP SCHEMA IF EXISTS "{target}" CASCADE'  # noqa: S608 -- generated test schema.
        )


async def test_refuses_moving_a_relation_into_a_system_schema(schema: str) -> None:
    source = adapter()
    action = source.action("move_relation")
    assert isinstance(action, TakesParams)

    with pytest.raises(ActionRefused, match="system schema"):
        await action.perform(
            f"{schema}.rich_customers", {"target_schema": "pg_catalog"}
        )


async def test_a_schema_drop_is_rehearsed_and_can_include_its_contents() -> None:
    source = adapter()
    name = f"drop_{uuid.uuid4().hex}"
    await run(f'CREATE SCHEMA "{name}"')  # noqa: S608 -- generated test schema.
    await run(
        f'CREATE TABLE "{name}"."kept_until_drop" (id integer)'  # noqa: S608 -- generated test schema.
    )
    action = source.action("drop_schema")
    assert isinstance(action, Previews)
    assert isinstance(action, TakesParams)
    try:
        blocked = await action.preview(name, {"cascade": False})
        cascade = await action.preview(name, {"cascade": True})

        assert blocked.blocked is True
        assert cascade.blocked is False
        assert any("kept_until_drop" in item for item in cascade.items)

        result = await action.perform(name, {"cascade": True})
        assert result.reload_node_ids == [None, name]
        assert name not in {node.name for node in await source.list_children(None)}
    finally:
        await run(
            f'DROP SCHEMA IF EXISTS "{name}" CASCADE'  # noqa: S608 -- generated test schema.
        )


class Upload:
    """The smallest thing that satisfies FilePayload."""

    def __init__(self, body: bytes, filename: str | None = "prices.csv") -> None:
        self.filename = filename
        self._body = body

    async def read(self, size: int) -> bytes:
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


async def _load(
    source: PostgresAdapter, schema: str, upload: Upload, **params: object
) -> ActionResult:
    action = source.action("load_csv")
    assert isinstance(action, TakesFile)
    return await action.perform_with_file(schema, params, upload)


async def test_load_from_csv_is_offered_on_a_schema_and_not_on_a_relation(
    schema: str,
) -> None:
    source = adapter()

    here = await source.available(schema)
    table = await source.available(f"{schema}.customers")
    system = await source.available("pg_catalog")

    assert {action.name for action in here} == {
        "rename_schema",
        "load_csv",
        "create_table",
        "drop_schema",
        "describe_model",
    }
    assert "load_csv" not in [action.name for action in table]
    # A schema the server owns is a real schema, and it admits nothing.
    assert system == []


async def test_a_csv_becomes_a_table_of_that_schema(schema: str) -> None:
    source = adapter()

    result = await _load(source, schema, Upload(b"sku,amount\na-1,10\na-2,20\n"))

    assert result.message == "prices created with 2 rows"
    # The schema is what gained a child, so it is what the client re-reads.
    assert result.reload_node_ids == [schema]

    page = await source.fetch(FetchRequest(node_id=f"{schema}.prices", limit=10))
    assert [column.name for column in page.columns] == ["sku", "amount"]
    assert sorted(str(row[0]) for row in page.rows) == ["a-1", "a-2"]


async def test_every_column_arrives_as_text(schema: str) -> None:
    """A delimited file states no types, so none is invented for it."""
    source = adapter()

    await _load(source, schema, Upload(b"sku,amount\na-1,10\n"))

    model = await source.relation_model(f"{schema}.prices")
    assert [(column.name, column.type.sql) for column in model.columns] == [
        ("sku", "text"),
        ("amount", "text"),
    ]


async def test_only_chosen_csv_columns_arrive_under_their_new_names(
    schema: str,
) -> None:
    source = adapter()

    await _load(
        source,
        schema,
        Upload(b"sku,amount,note\na-1,10,old\n"),
        columns=[
            {"source": "amount", "target": "price"},
            {"source": "sku", "target": "product"},
        ],
    )

    page = await source.fetch(FetchRequest(node_id=f"{schema}.prices", limit=10))
    assert [column.name for column in page.columns] == ["price", "product"]
    assert page.rows == [["10", "a-1"]]


async def test_at_least_one_csv_column_must_be_chosen(schema: str) -> None:
    source = adapter()

    with pytest.raises(ActionRefused, match="at least one"):
        await _load(source, schema, Upload(b"sku\na-1\n"), columns=[])


async def test_a_csv_can_create_its_destination_schema(schema: str) -> None:
    source = adapter()
    destination = f"loaded_{uuid.uuid4().hex}"
    try:
        result = await _load(
            source,
            schema,
            Upload(b"sku\na-1\n"),
            schema_name=destination,
            create_schema=True,
        )

        path = await source.path_to(f"{destination}.prices")
        assert path[-1].name == "prices"
        assert result.reload_node_ids == [None, destination]
    finally:
        await run(
            f'DROP SCHEMA IF EXISTS "{destination}" CASCADE'  # noqa: S608 -- generated test schema.
        )


async def test_the_table_is_named_after_the_file_unless_one_is_typed(
    schema: str,
) -> None:
    source = adapter()

    await _load(source, schema, Upload(b"a\n1\n", filename="loaded_regions.csv"))
    await _load(source, schema, Upload(b"a\n1\n"), name="chosen")

    names = {node.name for node in await source.list_children(schema)}
    assert {"loaded_regions", "chosen"} <= names


async def test_a_tab_separated_file_is_read_by_its_name(schema: str) -> None:
    source = adapter()

    await _load(source, schema, Upload(b"sku\tamount\na-1\t10\n", filename="p.tsv"))

    page = await source.fetch(FetchRequest(node_id=f"{schema}.p", limit=10))
    assert [column.name for column in page.columns] == ["sku", "amount"]


async def test_a_header_written_by_hand_still_names_every_column(schema: str) -> None:
    source = adapter()

    await _load(source, schema, Upload(b"id,,id\n1,2,3\n"))

    page = await source.fetch(FetchRequest(node_id=f"{schema}.prices", limit=10))
    assert [column.name for column in page.columns] == ["id", "column_2", "id_3"]


async def test_a_taken_name_is_refused_before_the_file_is_read(schema: str) -> None:
    source = adapter()

    with pytest.raises(ActionRefused) as refused:
        await _load(source, schema, Upload(b"a\n1\n"), name="customers")

    assert refused.value.reason == "conflict"


async def test_a_file_with_no_first_line_makes_nothing(schema: str) -> None:
    source = adapter()

    with pytest.raises(ActionRefused) as refused:
        await _load(source, schema, Upload(b""))

    assert refused.value.reason == "not_applicable"
    assert "prices" not in {node.name for node in await source.list_children(schema)}


async def test_more_rows_than_the_ceiling_are_refused_rather_than_cut_off(
    schema: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A whole file was handed over; a part of one arriving would go unnoticed."""
    monkeypatch.setattr(postgres_actions, "CSV_ROW_CEILING", 2)
    source = adapter()

    with pytest.raises(ActionRefused) as refused:
        await _load(source, schema, Upload(b"a\n1\n2\n3\n"))

    assert refused.value.reason == "too_large"
    assert "prices" not in {node.name for node in await source.list_children(schema)}


async def test_a_file_larger_than_the_ceiling_is_refused_while_it_arrives(
    schema: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(postgres_actions, "CSV_MAX_BYTES", 16)
    source = adapter()

    with pytest.raises(ActionRefused) as refused:
        await _load(source, schema, Upload(b"a\n" + b"1\n" * 100))

    assert refused.value.reason == "too_large"


async def test_a_name_postgres_would_truncate_is_refused(schema: str) -> None:
    source = adapter()

    with pytest.raises(ValueError):
        await _load(source, schema, Upload(b"a\n1\n"), name="я" * 63)


async def test_a_column_named_like_a_statement_is_quoted_not_composed(
    schema: str,
) -> None:
    source = adapter()

    await _load(source, schema, Upload(b'"a""); drop table x; --",b\n1,2\n'))

    model = await source.relation_model(f"{schema}.prices")
    assert [column.name for column in model.columns] == ['a"); drop table x; --', "b"]


async def _preview(source: PostgresAdapter, node_id: str, **params: object) -> ActionPreview:
    action = source.action("drop_relation")
    assert isinstance(action, Previews)
    return await action.preview(node_id, params)


async def _drop(source: PostgresAdapter, node_id: str, **params: object) -> ActionResult:
    action = source.action("drop_relation")
    assert isinstance(action, TakesParams)
    return await action.perform(node_id, params)


async def _drop_set(
    source: PostgresAdapter, *node_ids: str, **params: object
) -> ActionResult:
    action = source.action("drop_relation")
    assert isinstance(action, TakesNodeSet)
    return await action.perform_on_set(list(node_ids), params)


async def _preview_set(
    source: PostgresAdapter, *node_ids: str, **params: object
) -> ActionPreview:
    action = source.action("drop_relation")
    assert isinstance(action, PreviewsSet)
    return await action.preview_on_set(list(node_ids), params)


async def _names(source: PostgresAdapter, schema: str) -> set[str]:
    return {node.name for node in await source.list_children(schema)}


async def test_drop_is_offered_for_a_table_and_a_view(schema: str) -> None:
    source = adapter()

    table = await source.available(f"{schema}.customers")
    view = await source.available(f"{schema}.rich_customers")
    system = await source.available("pg_catalog.pg_class")

    assert "drop_relation" in {action.name for action in table}
    assert "drop_relation" in {action.name for action in view}
    assert system == []


async def test_a_relation_nothing_stands_on_says_so(schema: str) -> None:
    source = adapter()

    answer = await _preview(source, f"{schema}.rich_customers")

    assert answer.items == []
    assert answer.blocked is False
    assert "rich_customers" in answer.summary


async def test_a_preview_names_what_stands_in_the_way_and_blocks(schema: str) -> None:
    source = adapter()

    answer = await _preview(source, f"{schema}.customers")

    # The server's own account of it, not a rule restated here.
    assert answer.blocked is True
    assert any("rich_customers" in item for item in answer.items)


async def test_a_preview_with_cascade_lists_what_would_go(schema: str) -> None:
    source = adapter()

    answer = await _preview(source, f"{schema}.customers", cascade=True)

    assert answer.blocked is False
    assert any("rich_customers" in item for item in answer.items)


async def test_a_preview_changes_nothing(schema: str) -> None:
    """The drop is performed to find out, and then not kept."""
    source = adapter()

    await _preview(source, f"{schema}.customers", cascade=True)

    assert {"customers", "rich_customers"} <= await _names(source, schema)


async def test_dropping_what_something_is_built_on_is_refused(schema: str) -> None:
    source = adapter()

    with pytest.raises(ValueError) as refused:
        await _drop(source, f"{schema}.customers")

    assert "built on" in str(refused.value)
    assert "customers" in await _names(source, schema)


async def test_dropping_with_cascade_takes_the_view_with_it(schema: str) -> None:
    source = adapter()

    result = await _drop(source, f"{schema}.customers", cascade=True)

    assert result.message == "customers dropped"
    # The schema is what lost a child, so it is what the client re-reads.
    assert result.reload_node_ids == [schema]
    left = await _names(source, schema)
    assert "customers" not in left
    assert "rich_customers" not in left


async def test_a_view_is_dropped_as_a_view(schema: str) -> None:
    """DROP TABLE does not drop a view, and the kind comes from the catalog."""
    source = adapter()

    await _drop(source, f"{schema}.rich_customers")

    assert "rich_customers" not in await _names(source, schema)


async def test_a_materialized_view_is_dropped_as_one(schema: str) -> None:
    await run(
        f"CREATE MATERIALIZED VIEW {schema}.customer_snapshot "  # noqa: S608 -- fixture-owned schema.
        f"AS SELECT id, name FROM {schema}.customers"  # noqa: S608 -- fixture-owned schema.
    )
    source = adapter()

    await _drop(source, f"{schema}.customer_snapshot")

    assert "customer_snapshot" not in await _names(source, schema)


async def test_a_system_relation_cannot_be_dropped() -> None:
    source = adapter()

    with pytest.raises(ActionRefused) as refused:
        await _drop(source, "pg_catalog.pg_class")

    assert refused.value.reason == "not_applicable"


async def test_a_schema_is_not_a_relation_to_drop(schema: str) -> None:
    source = adapter()

    with pytest.raises(ActionRefused):
        await _drop(source, schema)


async def test_a_view_and_the_table_under_it_go_together(schema: str) -> None:
    """The set is the question: apart, the table is refused; together it is not."""
    source = adapter()

    result = await _drop_set(
        source, f"{schema}.rich_customers", f"{schema}.customers"
    )

    assert result.message == "2 relations dropped"
    assert result.reload_node_ids == [schema]
    left = await _names(source, schema)
    assert "customers" not in left
    assert "rich_customers" not in left


async def test_a_set_previews_as_one_account_of_the_whole_selection(
    schema: str,
) -> None:
    answer = await _preview_set(
        adapter(), f"{schema}.rich_customers", f"{schema}.customers"
    )

    assert answer.blocked is False
    assert "2 relations" in answer.summary


async def test_a_set_that_cannot_go_whole_leaves_all_of_it_standing(
    schema: str,
) -> None:
    """One transaction: half a drop is a schema nobody asked for."""
    source = adapter()

    with pytest.raises(ValueError) as refused:
        # The view goes first and would succeed; the table is referenced by
        # customers and is refused, which must take the view back with it.
        await _drop_set(source, f"{schema}.rich_customers", f"{schema}.regions")

    assert "built on" in str(refused.value)
    assert {"rich_customers", "regions"} <= await _names(source, schema)


async def test_a_set_preview_that_would_be_refused_says_so_and_blocks(
    schema: str,
) -> None:
    answer = await _preview_set(
        adapter(), f"{schema}.rich_customers", f"{schema}.regions"
    )

    assert answer.blocked is True
    assert any("customers" in item for item in answer.items)
    # A refusal is about what was selected, and two relations are not "this
    # relation".
    assert answer.summary == "Something else is built on 2 relations"


async def test_a_relation_may_be_selected_only_once(schema: str) -> None:
    source = adapter()

    with pytest.raises(ActionRefused) as refused:
        await _drop_set(source, f"{schema}.regions", f"{schema}.regions")

    assert refused.value.reason == "not_applicable"
    assert "regions" in await _names(source, schema)


async def test_a_system_relation_in_a_set_refuses_the_whole_set(
    schema: str,
) -> None:
    source = adapter()

    with pytest.raises(ActionRefused):
        await _drop_set(source, f"{schema}.rich_customers", "pg_catalog.pg_class")

    assert "rich_customers" in await _names(source, schema)

