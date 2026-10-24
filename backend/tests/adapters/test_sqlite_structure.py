"""Columns, indexes and constraints of a SQLite table changed (D27, D37–D40, D255).

Every test writes its own file under a temporary home.
"""

import sqlite3
from pathlib import Path

import pytest

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
    ForeignKeySpec,
    RepeatingValues,
    UniqueConstraintSpec,
    UnmatchedRows,
)
from app.adapters.content import ContentRequest, SqlContent
from app.adapters.indexes import (
    CreateIndexRequest,
    DropIndexRequest,
    IndexBlocked,
    IndexCreated,
)
from app.adapters.protocol import (
    SupportsAddColumn,
    SupportsColumnDefault,
    SupportsColumnNullability,
    SupportsColumnType,
    SupportsConstraints,
    SupportsDropColumn,
    SupportsIndexes,
    SupportsRenameColumn,
)
from app.adapters.relation import ForeignKey, UniqueConstraint
from app.adapters.sqlite.adapter import SqliteAdapter
from app.adapters.sqlite.definition import read_table
from app.adapters.sqlite.options import SqliteOptions
from app.adapters.sqlite.restructure import (
    after_type,
    constraint_names,
    edited,
    without_clause,
    without_items,
)
from tests.adapters.sqlite_fixture import FILE, build


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


@pytest.fixture
def adapter(home: Path) -> SqliteAdapter:
    return SqliteAdapter(SqliteOptions(path=FILE), home)


def _query(home: Path, statement: str) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(home / FILE)
    try:
        rows = list(connection.execute(statement).fetchall())
        connection.commit()
        return rows
    finally:
        connection.close()


async def _ddl(adapter: SqliteAdapter, node_id: str = "main.items") -> str:
    content = await adapter.read_content(ContentRequest(node_id=node_id, representation="sql"))
    assert isinstance(content, SqlContent)
    return content.text


def test_the_type_claims_structure_changes(adapter: SqliteAdapter) -> None:
    for capability in (
        SupportsAddColumn,
        SupportsDropColumn,
        SupportsRenameColumn,
        SupportsColumnDefault,
        SupportsColumnNullability,
        SupportsColumnType,
        SupportsIndexes,
        SupportsConstraints,
    ):
        assert isinstance(adapter, capability)


async def test_the_model_offers_what_can_be_changed(adapter: SqliteAdapter, home: Path) -> None:
    table = await adapter.relation_model("main.items")
    view = await adapter.relation_model("main.cheap")
    _query(home, "SELECT 1")

    assert table.column_changes_supported
    assert [option.code for option in table.column_type_options][:3] == ["text", "integer", "real"]
    assert [method.code for method in table.index_methods] == ["btree"]
    assert view.column_changes_supported is False
    assert view.column_changes_reason == "Only a table's structure can be changed"


# --- Editing the text (D255) ------------------------------------------------------


def test_a_clause_is_edited_and_everything_else_is_kept() -> None:
    text = (
        'CREATE TABLE "t" (\n'
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
        "  a TEXT NOT NULL ON CONFLICT REPLACE DEFAULT 'x' /* kept */,\n"
        "  b INT REFERENCES u ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED,\n"
        "  UNIQUE (a, b)\n"
        ")"
    )
    table = read_table(text)
    a = table.columns["a"]

    nullable = edited(text, [without_clause(table, clause) for clause in a.clauses if clause.kind == "not_null"])
    defaulted = edited(text, [after_type(table.columns["b"], "DEFAULT 1")])
    names = constraint_names(table)
    unkeyed = edited(text, [without_clause(table, names['UNIQUE ("a", "b")'])])

    assert "a TEXT DEFAULT 'x' /* kept */," in nullable
    assert "AUTOINCREMENT" in nullable and "DEFERRABLE INITIALLY DEFERRED" in nullable
    assert "b INT DEFAULT 1 REFERENCES u" in defaulted
    assert unkeyed.endswith("DEFERRABLE INITIALLY DEFERRED\n)")


def test_items_removed_together_keep_their_layout() -> None:
    text = "CREATE TABLE t (a, b, c, d)"
    table = read_table(text)

    assert edited(text, [without_items(table, [0, 1])]) == "CREATE TABLE t (c, d)"
    assert edited(text, [without_items(table, [1, 3])]) == "CREATE TABLE t (a, c)"
    with pytest.raises(ValueError):
        without_items(table, [0, 1, 2, 3])


# --- Columns ---------------------------------------------------------------------


async def test_a_column_that_may_be_empty_is_added_by_alter(
    adapter: SqliteAdapter, home: Path
) -> None:
    await adapter.add_column(AddColumnRequest(node_id="main.items", name="note", type_code="text"))

    assert ("note", "TEXT") in _query(home, "SELECT name, type FROM pragma_table_info('items')")


async def test_a_column_that_requires_a_value_is_refused_where_rows_are(
    adapter: SqliteAdapter, home: Path
) -> None:
    with pytest.raises(ValueError) as refused:
        await adapter.add_column(
            AddColumnRequest(node_id="main.items", name="note", type_code="text", nullable=False)
        )
    _query(home, "DELETE FROM pairs")
    await adapter.add_column(
        AddColumnRequest(node_id="main.pairs", name="weight", type_code="integer", nullable=False)
    )

    assert "requires a value" in str(refused.value)
    assert ("weight", 1) in _query(home, 'SELECT name, "notnull" FROM pragma_table_info(\'pairs\')')


async def test_a_rebuild_keeps_rows_rowids_indexes_triggers_and_the_counter(
    adapter: SqliteAdapter, home: Path
) -> None:
    _query(home, "SELECT 1")
    before = _query(home, "SELECT rowid, * FROM items ORDER BY rowid")
    connection = sqlite3.connect(home / FILE)
    connection.execute("UPDATE sqlite_sequence SET seq = 40 WHERE name = 'items'")
    connection.commit()
    connection.close()

    result = await adapter.change_column_type(
        ColumnTypeRequest(node_id="main.items", name="loose", type_code="text")
    )

    assert isinstance(result, ColumnTypeChanged) and result.type_sql == "TEXT"
    after = _query(home, "SELECT rowid, * FROM items ORDER BY rowid")
    assert [row[0] for row in after] == [row[0] for row in before]
    names = {str(row[0]) for row in _query(home, "SELECT name FROM sqlite_schema")}
    assert {"items_expensive", "items_named", "items"} <= names
    assert not any(name.startswith("dp_rebuild") for name in names)
    assert _query(home, "SELECT seq FROM sqlite_sequence WHERE name = 'items'") == [(40,)]
    ddl = await _ddl(adapter)
    assert "AUTOINCREMENT" in ddl and "COLLATE NOCASE" in ddl and "loose TEXT" in ddl


async def test_a_rebuild_leaves_the_rows_pointing_here_alone(
    adapter: SqliteAdapter, home: Path
) -> None:
    # items.label_id cascades on delete: dropping the old labels table with
    # foreign keys on would take the items with it.
    await adapter.change_column_type(
        ColumnTypeRequest(node_id="main.labels", name="name", type_code="json")
    )

    assert _query(home, "SELECT count(*) FROM items") == [(4,)]


async def test_a_default_is_set_as_a_literal_and_dropped(adapter: SqliteAdapter) -> None:
    await adapter.change_column_default(
        ColumnDefaultRequest(node_id="main.items", name="name", action="set", value="it's")
    )
    await adapter.change_column_default(
        ColumnDefaultRequest(node_id="main.items", name="price", action="set", value="2.5")
    )
    named = await adapter.relation_model("main.items")
    defaults = {column.name: column.default for column in named.columns}
    await adapter.change_column_default(
        ColumnDefaultRequest(node_id="main.items", name="price", action="drop")
    )
    dropped = await adapter.relation_model("main.items")

    assert defaults["name"] == "'it''s'"
    assert defaults["price"] == "2.5"
    assert next(column for column in dropped.columns if column.name == "price").default is None


async def test_a_requirement_is_counted_before_it_is_made(
    adapter: SqliteAdapter, home: Path
) -> None:
    blocked = await adapter.change_column_nullability(
        ColumnNullabilityRequest(node_id="main.items", name="label_id", nullable=False)
    )
    _query(home, "SELECT 1")
    changed = await adapter.change_column_nullability(
        ColumnNullabilityRequest(node_id="main.items", name="name", nullable=True)
    )

    assert isinstance(blocked, NullabilityBlocked) and blocked.rows_without_value == 2
    assert isinstance(changed, NullabilityChanged)
    assert ("name", 0) in _query(home, 'SELECT name, "notnull" FROM pragma_table_info(\'items\')')
    with pytest.raises(ValueError):
        await adapter.change_column_nullability(
            ColumnNullabilityRequest(node_id="main.items", name="id", nullable=True)
        )


async def test_a_strict_tables_type_change_is_counted(
    adapter: SqliteAdapter, home: Path
) -> None:
    connection = sqlite3.connect(home / FILE)
    connection.executescript(
        "CREATE TABLE s (id INTEGER PRIMARY KEY, v TEXT) STRICT;"
        "INSERT INTO s (v) VALUES ('1'), ('two'), ('3'), ('four');"
    )
    connection.close()

    blocked = await adapter.change_column_type(
        ColumnTypeRequest(node_id="main.s", name="v", type_code="integer")
    )
    model = await adapter.relation_model("main.s")

    assert isinstance(blocked, ColumnTypeBlocked) and blocked.rows_not_convertible == 2
    assert [option.code for option in model.column_type_options] == [
        "text",
        "integer",
        "real",
        "blob",
        "any",
    ]


async def test_a_column_is_dropped_with_its_keys_and_indexes(
    adapter: SqliteAdapter, home: Path
) -> None:
    connection = sqlite3.connect(home / FILE)
    connection.executescript(
        "CREATE TABLE t2 (a TEXT, b INT, c INT, UNIQUE (a, b)); CREATE INDEX t2_b ON t2 (b);"
        "CREATE INDEX t2_c ON t2 (c); INSERT INTO t2 VALUES ('x', 1, 2);"
    )
    connection.close()

    await adapter.drop_column(DropColumnRequest(node_id="main.t2", name="b"))

    ddl = await _ddl(adapter, "main.t2")
    assert _query(home, "SELECT * FROM t2") == [("x", 2)]
    assert "UNIQUE" not in ddl and "t2_b" not in ddl
    assert "CREATE INDEX t2_c" in ddl


async def test_a_drop_a_check_reads_is_refused(adapter: SqliteAdapter) -> None:
    # CHECK (price >= 0) stays in the text, and reads a column that is gone.
    with pytest.raises(ValueError) as refused:
        await adapter.drop_column(DropColumnRequest(node_id="main.items", name="price"))

    assert "price" in str(refused.value)


async def test_a_drop_something_reads_is_refused_in_sqlites_words(
    adapter: SqliteAdapter,
) -> None:
    # The view `cheap` reads name and price.
    with pytest.raises(ValueError) as refused:
        await adapter.drop_column(DropColumnRequest(node_id="main.items", name="name"))

    assert "cheap" in str(refused.value)


async def test_a_column_is_renamed_everywhere_sqlite_knows(
    adapter: SqliteAdapter, home: Path
) -> None:
    await adapter.rename_column(
        RenameColumnRequest(node_id="main.items", name="price", new_name="cost")
    )

    view = _query(home, "SELECT sql FROM sqlite_schema WHERE name = 'cheap'")[0][0]
    assert "cost" in str(view)
    with pytest.raises(ValueError):
        await adapter.rename_column(
            RenameColumnRequest(node_id="main.items", name="cost", new_name="NAME")
        )


# --- Indexes and constraints ---------------------------------------------------------


async def test_an_index_is_made_named_and_dropped(adapter: SqliteAdapter) -> None:
    made = await adapter.create_index(
        CreateIndexRequest(node_id="main.events", columns=["kind"], method="btree")
    )
    blocked = await adapter.create_index(
        CreateIndexRequest(node_id="main.events", columns=["kind"], method="btree", unique=True)
    )

    assert isinstance(made, IndexCreated) and made.name == "events_kind_idx"
    assert isinstance(blocked, IndexBlocked) and blocked.duplicate_groups == 1
    await adapter.drop_index(DropIndexRequest(node_id="main.events", name=made.name))
    model = await adapter.relation_model("main.events")
    assert model.indexes == []


async def test_an_index_behind_a_key_is_dropped_through_the_key(adapter: SqliteAdapter) -> None:
    model = await adapter.relation_model("main.items")
    behind = next(index for index in model.indexes if index.name.startswith("sqlite_autoindex"))

    with pytest.raises(ValueError) as refused:
        await adapter.drop_index(DropIndexRequest(node_id="main.items", name=behind.name))

    assert "drop that instead" in str(refused.value)


async def test_a_unique_key_is_counted_added_and_dropped(adapter: SqliteAdapter) -> None:
    repeating = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id="main.events", constraint=UniqueConstraintSpec(columns=["kind"])
        )
    )
    made = await adapter.create_constraint(
        CreateConstraintRequest(
            node_id="main.events", constraint=UniqueConstraintSpec(columns=["kind", "at"])
        )
    )

    assert isinstance(repeating, RepeatingValues) and repeating.groups == 1
    assert isinstance(made, ConstraintCreated) and made.name == "events_kind_at_key"
    model = await adapter.relation_model("main.events")
    assert any(isinstance(c, UniqueConstraint) and c.name == made.name for c in model.constraints)
    await adapter.drop_constraint(DropConstraintRequest(node_id="main.events", name=made.name))
    model = await adapter.relation_model("main.events")
    assert not any(isinstance(c, UniqueConstraint) for c in model.constraints)


async def test_a_foreign_key_is_counted_added_and_dropped_by_its_shown_name(
    adapter: SqliteAdapter, home: Path
) -> None:
    _query(home, "SELECT 1")
    connection = sqlite3.connect(home / FILE)
    connection.executescript("CREATE TABLE notes2 (id INTEGER PRIMARY KEY, label INT); INSERT INTO notes2 (label) VALUES (1), (7), (NULL);")
    connection.close()
    spec = ForeignKeySpec(columns=["label"], target_node_id="main.labels", target_columns=["id"], on_delete="cascade")

    unmatched = await adapter.create_constraint(
        CreateConstraintRequest(node_id="main.notes2", constraint=spec)
    )
    _query(home, "SELECT 1")
    connection = sqlite3.connect(home / FILE)
    connection.execute("DELETE FROM notes2 WHERE label = 7")
    connection.commit()
    connection.close()
    made = await adapter.create_constraint(CreateConstraintRequest(node_id="main.notes2", constraint=spec))

    assert isinstance(unmatched, UnmatchedRows) and unmatched.rows == 1
    assert isinstance(made, ConstraintCreated)
    model = await adapter.relation_model("main.notes2")
    key = next(c for c in model.constraints if isinstance(c, ForeignKey))
    assert (key.name, key.on_delete, key.target_node_id) == ("notes2_label_fkey", "cascade", "main.labels")
    # An unnamed key is dropped by the name the catalog shows it under (D249).
    await adapter.drop_constraint(
        DropConstraintRequest(node_id="main.pairs", name='FOREIGN KEY ("left_id")')
    )
    pairs = await adapter.relation_model("main.pairs")
    assert not any(isinstance(c, ForeignKey) for c in pairs.constraints)


async def test_a_foreign_key_must_point_at_a_key(adapter: SqliteAdapter) -> None:
    with pytest.raises(ValueError):
        await adapter.create_constraint(
            CreateConstraintRequest(
                node_id="main.events",
                constraint=ForeignKeySpec(
                    columns=["kind"], target_node_id="main.items", target_columns=["picture"]
                ),
            )
        )


async def test_what_cannot_be_restructured_says_why(adapter: SqliteAdapter) -> None:
    with pytest.raises(ValueError) as refused:
        await adapter.add_column(AddColumnRequest(node_id="main.cheap", name="x", type_code="text"))
    with pytest.raises(ValueError):
        await adapter.drop_constraint(DropConstraintRequest(node_id="main.pairs", name="PRIMARY KEY"))

    assert str(refused.value) == "Only a table's structure can be changed"
