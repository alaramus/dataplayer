from collections.abc import AsyncGenerator

import pytest

from app.adapters.actions import ActionRefused, ActionResult, TakesFile, TakesParams
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


async def test_rename_is_offered_only_for_non_system_relations(schema: str) -> None:
    source = adapter()

    table = await source.available(f"{schema}.customers")
    view = await source.available(f"{schema}.rich_customers")
    system = await source.available("pg_catalog.pg_class")

    assert [action.name for action in table] == ["rename_relation"]
    assert [action.name for action in view] == ["rename_relation"]
    assert system == []


async def test_renames_a_view_with_a_source_issued_replacement(schema: str) -> None:
    source = adapter()
    action = source.action("rename_relation")
    assert isinstance(action, TakesParams)

    result = await action.perform(
        f"{schema}.rich_customers", {"new_name": "valuable_customers"}
    )

    assert result.reload_node_id == schema
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

    assert [action.name for action in here] == ["load_csv"]
    assert "load_csv" not in [action.name for action in table]
    # A schema the server owns is a real schema, and it admits nothing.
    assert system == []


async def test_a_csv_becomes_a_table_of_that_schema(schema: str) -> None:
    source = adapter()

    result = await _load(source, schema, Upload(b"sku,amount\na-1,10\na-2,20\n"))

    assert result.message == "prices created with 2 rows"
    # The schema is what gained a child, so it is what the client re-reads.
    assert result.reload_node_id == schema

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


async def test_the_table_is_named_after_the_file_unless_one_is_typed(
    schema: str,
) -> None:
    source = adapter()

    await _load(source, schema, Upload(b"a\n1\n", filename="regions.csv"))
    await _load(source, schema, Upload(b"a\n1\n"), name="chosen")

    names = {node.name for node in await source.list_children(schema)}
    assert {"regions", "chosen"} <= names


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
