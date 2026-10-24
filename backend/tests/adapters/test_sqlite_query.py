"""The SQL console of a SQLite source (D62, D252, D253).

Reading the text needs nothing; running it needs only a file, written afresh
under a temporary home for every test.
"""

import asyncio
import time
from pathlib import Path

import pytest

from app.adapters.protocol import AdapterError
from app.adapters.query import (
    ExplainRequest,
    GenerateQueryRequest,
    ParameterValue,
    QueryExecution,
    QueryLimits,
    QueryMetadataRequest,
    QueryRequest,
    StatementFinished,
    SupportsExplain,
    SupportsQuery,
    SupportsQueryFormatting,
    SupportsQueryMetadata,
    SupportsRehearsal,
    SupportsTransactions,
    TransactionContext,
)
from app.adapters.sqlite.adapter import SqliteAdapter
from app.adapters.sqlite.options import SqliteOptions
from app.adapters.sqlite.statements import effect_of, format_text, prepare
from tests.adapters.sqlite_fixture import FILE, build

LIMITS = QueryLimits(
    statement_timeout_seconds=30,
    script_timeout_seconds=60,
    max_statements=50,
    max_statement_bytes=100_000,
    max_result_rows=1000,
    max_result_bytes=1_000_000,
    max_cell_bytes=100_000,
    max_run_results=20,
    max_run_bytes=5_000_000,
    max_messages=20,
)
ENDLESS = (
    "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) "
    "SELECT count(*) FROM n"
)


@pytest.fixture
def adapter(tmp_path: Path) -> SqliteAdapter:
    build(tmp_path)
    return SqliteAdapter(SqliteOptions(path=FILE), tmp_path)


def _request(text: str, mode: str = "read", **extra: object) -> QueryRequest:
    return QueryRequest(text=text, mode=mode, limits=LIMITS, **extra)  # type: ignore[arg-type]  # the mode is one of three literals


async def _finished(execution: QueryExecution) -> list[StatementFinished]:
    return [event async for event in execution.events() if isinstance(event, StatementFinished)]


async def _value(adapter: SqliteAdapter, text: str) -> str | None:
    finished = await _finished(adapter.open_query(_request(text)))
    assert finished[0].status == "succeeded", finished[0].diagnostic
    assert finished[0].result is not None
    return finished[0].result.rows[0][0]


# --- Reading the text (D252) ------------------------------------------------


def test_the_type_claims_the_whole_console(adapter: SqliteAdapter) -> None:
    for capability in (
        SupportsQuery,
        SupportsTransactions,
        SupportsRehearsal,
        SupportsExplain,
        SupportsQueryMetadata,
        SupportsQueryFormatting,
    ):
        assert isinstance(adapter, capability)
    profile = adapter.query_profile()
    assert (profile.dialect, profile.parameter_syntax) == ("sqlite", "named_colon")


def test_statements_end_where_sqlite_says() -> None:
    script = prepare(
        "SELECT ';' AS a; SELECT \"x;y\" FROM t -- ;\n; /* ; */ SELECT 1;\n"
        "CREATE TRIGGER tr AFTER INSERT ON t BEGIN UPDATE t SET a = 1; DELETE FROM u; END;"
        " SELECT 2"
    )

    assert [statement.text for statement in script.statements] == [
        "SELECT ';' AS a",
        'SELECT "x;y" FROM t',
        "SELECT 1",
        "CREATE TRIGGER tr AFTER INSERT ON t BEGIN UPDATE t SET a = 1; DELETE FROM u; END",
        "SELECT 2",
    ]


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("select * from items", "read"),
        ("VALUES (1), (2)", "read"),
        ("WITH c AS (SELECT 1) SELECT * FROM c", "read"),
        ("WITH c AS (SELECT 1) DELETE FROM items WHERE id IN c", "dml"),
        ("INSERT OR REPLACE INTO labels (name) VALUES ('x')", "dml"),
        ("REPLACE INTO labels (name) VALUES ('x')", "dml"),
        ("CREATE TABLE t (a)", "ddl"),
        ("CREATE TEMP VIEW v AS SELECT 1", "ddl"),
        ("ALTER TABLE items ADD COLUMN x", "ddl"),
        ("DROP INDEX items_expensive", "ddl"),
        ("EXPLAIN QUERY PLAN SELECT 1", "explain"),
        ("BEGIN IMMEDIATE", "transaction"),
        ("SAVEPOINT a", "transaction"),
        ("VACUUM", "maintenance"),
        ("ANALYZE", "maintenance"),
        ("PRAGMA optimize", "maintenance"),
        ("PRAGMA table_info(items)", "read"),
        ("PRAGMA main.user_version", "read"),
        ("PRAGMA integrity_check", "read"),
        ("PRAGMA user_version = 3", "session"),
        ("PRAGMA user_version(3)", "session"),
        ("PRAGMA foreign_keys = OFF", "session"),
        ("PRAGMA something_new", "unknown"),
        ("ATTACH 'x.db' AS x", "session"),
        ("SELEC 1", "unknown"),
    ],
)
def test_a_statement_is_classed_by_its_keyword(text: str, kind: str) -> None:
    assert prepare(text).statements[0].kind == kind


def test_what_falls_outside_the_vocabulary_is_refused_by_name() -> None:
    trigger, attach = prepare(
        "CREATE TRIGGER t AFTER INSERT ON items BEGIN SELECT 1; END; ATTACH 'x' AS x"
    ).statements

    assert trigger.refused == "Triggers are not changed from the query editor"
    assert attach.refused == "A connection to this file opens no other file"


def test_risk_destruction_parameters_and_targets_are_read() -> None:
    update, delete, drop, insert = prepare(
        "UPDATE items SET price = :price; DELETE FROM items WHERE id = :id AND ':no' = '';"
        'DROP TABLE IF EXISTS main."odd t"; INSERT INTO labels (name) VALUES (:name)'
    ).statements

    assert (update.risk, update.parameters, update.targets) == ("high", ["price"], ["items"])
    assert (delete.risk, delete.parameters) == ("low", ["id"])
    assert (drop.destructive, drop.targets) == (True, ["odd t"])
    assert (insert.risk, insert.targets) == ("low", ["labels"])


def test_a_structure_change_names_what_it_changed() -> None:
    assert effect_of("CREATE TABLE t (a)").reload_node_ids == ["main"]
    assert effect_of("ALTER TABLE items ADD COLUMN x").relation_node_ids == ["main.items"]
    assert effect_of("ALTER TABLE items RENAME TO goods").reload_node_ids == ["main"]
    assert effect_of("CREATE INDEX i ON items (name)").relation_node_ids == ["main.items"]
    assert effect_of("DROP INDEX i").scope == "connection"
    assert effect_of("CREATE TEMP TABLE t (a)").is_empty()


def test_only_reads_and_row_changes_are_laid_out_again() -> None:
    assert format_text("select a,b from t where x=1") == "SELECT\n  a,\n  b\nFROM t\nWHERE\n  x = 1"
    kept = "create table t (a text collate nocase check (a <> ''))"
    assert format_text(kept) == kept
    assert format_text("select :a") == "select :a"


# --- Running it (D253) ------------------------------------------------------


async def test_a_read_answers_with_values_by_what_they_are(adapter: SqliteAdapter) -> None:
    finished = await _finished(
        adapter.open_query(
            _request("SELECT id, name, picture, 1.5 AS x, id AS id FROM items ORDER BY id LIMIT 1")
        )
    )

    result = finished[0].result
    assert result is not None
    assert [column.name for column in result.columns] == ["id", "name", "picture", "x", "id"]
    assert [column.type.category for column in result.columns] == [
        "number",
        "string",
        "binary",
        "number",
        "number",
    ]
    assert result.rows == [["1", "one", "0x00FF", "1.5", "1"]]


async def test_parameters_are_bound_by_name(adapter: SqliteAdapter) -> None:
    finished = await _finished(
        adapter.open_query(
            _request(
                "SELECT name FROM items WHERE price > :low AND name <> ':low'",
                parameters=[ParameterValue(name="low", value="5")],
            )
        )
    )

    assert finished[0].result is not None
    assert [row[0] for row in finished[0].result.rows] == ["100% pure", "under_score"]


async def test_a_read_cannot_write(adapter: SqliteAdapter) -> None:
    finished = await _finished(
        adapter.open_query(_request("SELECT 1; INSERT INTO labels (name) VALUES ('x')"))
    )

    assert finished[1].status == "failed"
    assert finished[1].diagnostic is not None
    assert finished[1].diagnostic.category == "read_only"


async def test_a_setting_this_application_keeps_cannot_be_changed(
    adapter: SqliteAdapter,
) -> None:
    # Not even by a statement of a class a run would admit: the authorizer
    # refuses it whatever reaches it (D253).
    finished = await _finished(
        adapter.open_query(
            _request("SELECT * FROM pragma_foreign_keys")
        )
    )
    assert finished[0].result is not None
    assert finished[0].result.rows == [["1"]]


async def test_an_auto_commit_run_is_one_transaction_with_its_structure(
    adapter: SqliteAdapter,
) -> None:
    failed = await _finished(
        adapter.open_query(
            _request(
                "CREATE TABLE made (a); INSERT INTO labels (name) VALUES ('red')",
                mode="auto_commit",
            )
        )
    )
    kept = await _finished(
        adapter.open_query(
            _request(
                "CREATE TABLE made (a); INSERT INTO made VALUES (1), (2)", mode="auto_commit"
            )
        )
    )

    # The duplicate label failed, and the table made before it went with it.
    assert [one.status for one in failed] == ["succeeded", "failed"]
    assert failed[1].diagnostic is not None and failed[1].diagnostic.category == "data"
    assert [one.status for one in kept] == ["succeeded", "succeeded"]
    assert kept[0].effect is not None and kept[0].effect.reload_node_ids == ["main"]
    assert kept[1].affected_rows == 2
    assert await _value(adapter, "SELECT count(*) FROM made") == "2"


async def test_foreign_keys_the_file_declares_are_enforced(adapter: SqliteAdapter) -> None:
    finished = await _finished(
        adapter.open_query(
            _request("INSERT INTO items (name, label_id) VALUES ('x', 99)", mode="auto_commit")
        )
    )

    assert finished[0].status == "failed"
    assert finished[0].diagnostic is not None
    assert "FOREIGN KEY" in finished[0].diagnostic.message


async def test_maintenance_runs_outside_a_transaction(adapter: SqliteAdapter) -> None:
    finished = await _finished(adapter.open_query(_request("VACUUM", mode="auto_commit")))

    assert finished[0].status == "succeeded", finished[0].diagnostic


async def test_a_failure_is_named_in_sqlites_words(adapter: SqliteAdapter) -> None:
    missing, syntax = await _finished(
        adapter.open_query(_request("SELECT * FROM missing_table"))
    ), await _finished(adapter.open_query(_request("SELECT FROM WHERE")))

    assert missing[0].diagnostic is not None
    assert (missing[0].diagnostic.category, missing[0].diagnostic.message) == (
        "missing_object",
        "no such table: missing_table",
    )
    assert syntax[0].diagnostic is not None and syntax[0].diagnostic.category == "syntax"


async def test_a_statement_past_its_time_is_stopped(adapter: SqliteAdapter) -> None:
    limits = LIMITS.model_copy(update={"statement_timeout_seconds": 1})
    started = time.monotonic()
    finished = await _finished(
        adapter.open_query(QueryRequest(text=f"{ENDLESS}; SELECT 1", mode="read", limits=limits))
    )

    assert [one.status for one in finished] == ["timed_out", "not_run"]
    assert time.monotonic() - started < 5


async def test_stop_cancels_the_running_statement(adapter: SqliteAdapter) -> None:
    execution = adapter.open_query(_request(ENDLESS))
    collected: list[StatementFinished] = []

    async def run() -> None:
        collected.extend(await _finished(execution))

    task = asyncio.create_task(run())
    await asyncio.sleep(0.3)
    await execution.cancel()
    await asyncio.wait_for(task, 5)

    assert [one.status for one in collected] == ["cancelled"]


async def test_another_schema_is_refused(adapter: SqliteAdapter) -> None:
    with pytest.raises(AdapterError):
        await _finished(adapter.open_query(_request("SELECT 1", search_path=["public"])))


# --- A transaction held open, and a rehearsal ---------------------------------


async def test_a_held_transaction_changes_structure_and_rolls_back(
    adapter: SqliteAdapter,
) -> None:
    transaction = await adapter.begin_transaction(TransactionContext())
    try:
        made = await _finished(transaction.execute(_request("CREATE TABLE held (a)")))
        transaction.absorb(transaction.execute(_request("SELECT 1")))
        run = transaction.execute(_request("INSERT INTO held VALUES (1); SELECT * FROM missing_table"))
        finished = await _finished(run)
        transaction.absorb(run)
        state = transaction.state()
        # A failed statement leaves a SQLite transaction open and usable.
        after = await _finished(transaction.execute(_request("SELECT count(*) FROM held")))
    finally:
        await transaction.rollback()

    assert made[0].status == "succeeded"
    assert [one.status for one in finished] == ["succeeded", "failed"]
    assert (state.open, state.broken) == (True, False)
    assert after[0].result is not None and after[0].result.rows == [["1"]]
    gone = await _finished(adapter.open_query(_request("SELECT * FROM held")))
    assert gone[0].status == "failed"


async def test_a_held_transaction_commits(adapter: SqliteAdapter) -> None:
    transaction = await adapter.begin_transaction(TransactionContext())
    await _finished(transaction.execute(_request("INSERT INTO labels (name) VALUES ('blue')")))
    await transaction.commit()

    assert await _value(adapter, "SELECT count(*) FROM labels") == "3"
    assert transaction.state().open is False


async def test_a_change_is_rehearsed_and_undone(adapter: SqliteAdapter) -> None:
    rehearsal = await adapter.rehearse_query(
        _request("DELETE FROM events; DROP TABLE events; SELECT 1", mode="auto_commit")
    )

    assert [one.outcome for one in rehearsal.statements] == ["ok", "ok", "not_run"]
    assert rehearsal.statements[0].affected_rows == 6
    assert rehearsal.runnable
    assert rehearsal.effect.reload_node_ids == ["main"]
    assert await _value(adapter, "SELECT count(*) FROM events") == "6"


async def test_a_rehearsal_inside_a_held_transaction_keeps_what_came_before(
    adapter: SqliteAdapter,
) -> None:
    transaction = await adapter.begin_transaction(TransactionContext())
    try:
        await _finished(transaction.execute(_request("INSERT INTO labels (name) VALUES ('blue')")))
        rehearsal = await transaction.rehearse(_request("DELETE FROM labels WHERE name = 'blue'"))
        counted = await _finished(transaction.execute(_request("SELECT count(*) FROM labels")))
    finally:
        await transaction.rollback()

    assert rehearsal.statements[0].affected_rows == 1
    assert counted[0].result is not None and counted[0].result.rows == [["3"]]


async def test_a_rehearsal_behind_somebody_elses_lock_says_it_is_blocked(
    adapter: SqliteAdapter,
) -> None:
    transaction = await adapter.begin_transaction(TransactionContext())
    try:
        await _finished(transaction.execute(_request("INSERT INTO labels (name) VALUES ('blue')")))
        rehearsal = await adapter.rehearse_query(
            _request("DELETE FROM labels", mode="auto_commit")
        )
    finally:
        await transaction.rollback()

    assert rehearsal.blocked
    assert rehearsal.statements[0].outcome == "blocked"


# --- Explain, completion, generated statements ---------------------------------


async def test_a_plan_is_a_tree_of_sqlites_sentences(adapter: SqliteAdapter) -> None:
    result = await adapter.explain_query(
        ExplainRequest(text="SELECT * FROM items WHERE id = :id ORDER BY name")
    )

    labels = [child.label for child in result.plan.children]
    assert any(label.startswith("SEARCH items") for label in labels)
    assert result.plan.children[0].relation == "items"
    assert result.raw.startswith("QUERY PLAN\n|--")


async def test_explain_refuses_what_it_does_not_plan(adapter: SqliteAdapter) -> None:
    for text in ("SELECT 1; SELECT 2", "EXPLAIN SELECT 1", "CREATE TABLE t (a)"):
        with pytest.raises(ValueError):
            await adapter.explain_query(ExplainRequest(text=text))


async def test_completion_knows_main_and_its_columns(adapter: SqliteAdapter) -> None:
    metadata = await adapter.query_metadata(
        QueryMetadataRequest(relations=["main.items", "labels", "nothing"])
    )

    assert metadata.schemas == ["main"]
    assert {relation.name for relation in metadata.relations} >= {"items", "cheap", "notes"}
    assert [column.name for column in metadata.columns["main.items"]][:2] == ["id", "name"]
    assert [column.name for column in metadata.columns["labels"]] == ["id", "name"]
    assert "nothing" not in metadata.columns


async def test_statements_about_a_node_are_quoted_by_sqlite(adapter: SqliteAdapter) -> None:
    select = await adapter.generate_query(GenerateQueryRequest(node_id='main.odd, "name"'))
    name = await adapter.generate_query(
        GenerateQueryRequest(node_id="main.items", kind="name")
    )

    assert select.text == 'SELECT "a b", "c", "d"\nFROM "main"."odd, ""name"""\nLIMIT 100'
    assert name.text == '"main"."items"'
    with pytest.raises(ValueError):
        await adapter.generate_query(GenerateQueryRequest(node_id="main.nothing"))
