"""Changing the columns and skipping indexes of a ClickHouse table (D273)."""

from collections.abc import AsyncIterator

import pytest

from app.adapters.clickhouse.session import quoted_name
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
from app.adapters.database_ids import relation_id
from app.adapters.fetch import FetchRequest
from app.adapters.indexes import CreateIndexRequest, DropIndexRequest, IndexCreated
from app.adapters.protocol import SupportsConstraints
from tests.adapters.clickhouse_fixture import DATABASE, adapter, build, run, tear_down
from tests.utils.services import CLICKHOUSE

DB = quoted_name(DATABASE)
SHAPE = relation_id(DATABASE, "shape")
JOURNAL = relation_id(DATABASE, "journal")


@pytest.fixture(scope="module")
async def server() -> AsyncIterator[None]:
    CLICKHOUSE.require()
    await build()
    await run(
        f"""
        CREATE TABLE {DB}.shape (
            id UInt32,
            note String DEFAULT 'x' COMMENT 'kept' CODEC(ZSTD),
            numberish String,
            maybe Nullable(Int32),
            tag LowCardinality(String)
        ) ENGINE = MergeTree ORDER BY id
        """,
        f"INSERT INTO {DB}.shape (id, numberish, maybe, tag) VALUES (1, '5', NULL, 'a'), (2, 'abc', 3, 'b')",
    )
    yield
    await tear_down()


async def _columns() -> dict[str, tuple[str, str | None, str | None]]:
    model = await adapter().relation_model(SHAPE)
    return {column.name: (column.type.sql, column.default, column.comment) for column in model.columns}


async def _rows() -> list[list[str | None]]:
    return (await adapter().fetch(FetchRequest(node_id=SHAPE))).rows


def test_no_unique_key_and_no_foreign_key_are_offered() -> None:
    assert not isinstance(adapter(), SupportsConstraints)


@pytest.mark.usefixtures("server")
async def test_the_model_says_what_can_be_changed_and_why_not() -> None:
    shape = await adapter().relation_model(SHAPE)
    journal = await adapter().relation_model(JOURNAL)
    view = await adapter().relation_model(relation_id(DATABASE, "item_labels"))

    assert shape.column_changes_supported and shape.index_changes_supported
    assert [option.code for option in shape.index_methods] == ["minmax", "set", "bloom_filter"]
    assert not any(option.unique_supported for option in shape.index_methods)
    assert "String" in [option.sql for option in shape.column_type_options]
    assert not shape.constraint_changes_supported and shape.constraint_changes_reason
    assert not journal.column_changes_supported
    assert journal.column_changes_reason is not None and "Log" in journal.column_changes_reason
    assert not view.column_changes_supported


@pytest.mark.usefixtures("server")
async def test_a_column_is_added_renamed_given_a_default_and_dropped() -> None:
    source = adapter()

    await source.add_column(AddColumnRequest(node_id=SHAPE, name="extra", type_code="int64", nullable=True))
    await source.add_column(AddColumnRequest(node_id=SHAPE, name="counted", type_code="uint64", nullable=False))
    await source.rename_column(RenameColumnRequest(node_id=SHAPE, name="extra", new_name="more"))
    await source.change_column_default(
        ColumnDefaultRequest(node_id=SHAPE, name="note", action="set", value="it's \\ new")
    )
    columns = await _columns()

    assert columns["more"][0] == "Nullable(Int64)"
    assert columns["counted"][0] == "UInt64"
    # A literal kept as the server writes it; comment and codec untouched.
    assert columns["note"][1] == "'it\\'s \\\\ new'"
    assert columns["note"][2] == "kept"
    with pytest.raises(ValueError, match="cannot hold that default"):
        await source.change_column_default(
            ColumnDefaultRequest(node_id=SHAPE, name="counted", action="set", value="-1")
        )
    await source.change_column_default(ColumnDefaultRequest(node_id=SHAPE, name="note", action="drop"))
    await source.drop_column(DropColumnRequest(node_id=SHAPE, name="more"))
    await source.drop_column(DropColumnRequest(node_id=SHAPE, name="counted"))
    columns = await _columns()
    assert "more" not in columns and columns["note"][1] is None
    with pytest.raises(ValueError, match="already has a column"):
        await source.add_column(AddColumnRequest(node_id=SHAPE, name="note", type_code="text"))


@pytest.mark.usefixtures("server")
async def test_a_key_column_is_not_changed() -> None:
    source = adapter()

    with pytest.raises(ValueError, match="key"):
        await source.drop_column(DropColumnRequest(node_id=SHAPE, name="id"))
    with pytest.raises(ValueError, match="key"):
        await source.rename_column(RenameColumnRequest(node_id=SHAPE, name="id", new_name="ident"))
    with pytest.raises(ValueError, match="key"):
        await source.change_column_type(ColumnTypeRequest(node_id=SHAPE, name="id", type_code="uint64"))


@pytest.mark.usefixtures("server")
async def test_a_type_is_changed_only_when_every_value_converts() -> None:
    """A failed conversion would leave the table unreadable, so it is counted first."""
    source = adapter()

    blocked = await source.change_column_type(
        ColumnTypeRequest(node_id=SHAPE, name="numberish", type_code="int32")
    )
    assert isinstance(blocked, ColumnTypeBlocked)
    assert blocked.rows_not_convertible == 1
    assert len(await _rows()) == 2

    await run(f"ALTER TABLE {DB}.shape UPDATE numberish = '7' WHERE numberish = 'abc' SETTINGS mutations_sync = 1")
    changed = await source.change_column_type(
        ColumnTypeRequest(node_id=SHAPE, name="numberish", type_code="int32")
    )
    assert isinstance(changed, ColumnTypeChanged) and changed.type_sql == "Int32"
    # Nullable stays Nullable, and LowCardinality stays outside.
    widened = await source.change_column_type(
        ColumnTypeRequest(node_id=SHAPE, name="maybe", type_code="int64")
    )
    assert isinstance(widened, ColumnTypeChanged) and widened.type_sql == "Nullable(Int64)"
    with pytest.raises(ValueError, match="already has type"):
        await source.change_column_type(ColumnTypeRequest(node_id=SHAPE, name="tag", type_code="repeated_text"))


@pytest.mark.usefixtures("server")
async def test_nullability_counts_what_stands_in_the_way() -> None:
    source = adapter()

    blocked = await source.change_column_nullability(
        ColumnNullabilityRequest(node_id=SHAPE, name="maybe", nullable=False)
    )
    assert isinstance(blocked, NullabilityBlocked) and blocked.rows_without_value == 1

    loosened = await source.change_column_nullability(
        ColumnNullabilityRequest(node_id=SHAPE, name="tag", nullable=True)
    )
    assert isinstance(loosened, NullabilityChanged)
    assert (await _columns())["tag"][0] == "LowCardinality(Nullable(String))"
    tightened = await source.change_column_nullability(
        ColumnNullabilityRequest(node_id=SHAPE, name="tag", nullable=False)
    )
    assert isinstance(tightened, NullabilityChanged)
    assert (await _columns())["tag"][0] == "LowCardinality(String)"


@pytest.mark.usefixtures("server")
async def test_a_skipping_index_is_made_over_the_rows_there_and_dropped() -> None:
    source = adapter()

    made = await source.create_index(
        CreateIndexRequest(node_id=SHAPE, columns=["note", "tag"], method="bloom_filter")
    )
    again = await source.create_index(CreateIndexRequest(node_id=SHAPE, columns=["note", "tag"], method="minmax"))

    assert isinstance(made, IndexCreated) and isinstance(again, IndexCreated)
    assert made.name == "shape_note_tag_idx" and again.name == "shape_note_tag_idx2"
    indexes = {index.name: index for index in (await source.relation_model(SHAPE)).indexes}
    assert indexes[made.name].method == "bloom_filter"
    with pytest.raises(ValueError, match="unique"):
        await source.create_index(CreateIndexRequest(node_id=SHAPE, columns=["note"], method="set", unique=True))
    with pytest.raises(ValueError, match="primary key"):
        await source.drop_index(DropIndexRequest(node_id=SHAPE, name="PRIMARY KEY"))
    await source.drop_index(DropIndexRequest(node_id=SHAPE, name=made.name))
    await source.drop_index(DropIndexRequest(node_id=SHAPE, name=again.name))
    assert [index.name for index in (await source.relation_model(SHAPE)).indexes] == ["PRIMARY KEY"]


@pytest.mark.usefixtures("server")
async def test_a_table_that_cannot_change_says_why() -> None:
    with pytest.raises(ValueError, match="Log"):
        await adapter().add_column(AddColumnRequest(node_id=JOURNAL, name="x", type_code="text"))


@pytest.mark.usefixtures("server")
async def test_a_failed_conversion_is_undone_and_the_table_still_reads() -> None:
    """Past the count — a value it could not see coming — the mutation is
    killed and the old type put back, rather than the table left unreadable."""
    from app.adapters.clickhouse.columns import ClickhouseColumns
    from app.adapters.clickhouse.relation import ClickhouseRelation

    await run(
        f"CREATE TABLE {DB}.fragile (id UInt32, v String) ENGINE = MergeTree ORDER BY id",
        f"INSERT INTO {DB}.fragile VALUES (1, '5'), (2, 'abc')",
    )
    source = adapter()
    relation = ClickhouseRelation(source._session)
    columns = ClickhouseColumns(source._session, relation)
    fragile = relation_id(DATABASE, "fragile")
    facts = await relation.facts(fragile)

    with pytest.raises(ValueError, match="left as it was"):
        await columns._modify(facts, facts.columns[1], "Int32")

    after = await source.fetch(FetchRequest(node_id=fragile))
    assert after.rows == [["1", "5"], ["2", "abc"]]
    assert (await source.relation_model(fragile)).columns[1].type.sql == "String"
    # Nothing is left waiting in front of the next change.
    await source.add_column(AddColumnRequest(node_id=fragile, name="w", type_code="text"))
