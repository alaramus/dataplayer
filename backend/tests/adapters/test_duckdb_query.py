"""The SQL console of a DuckDB source (D62, D392–D394).

Reading the text needs nothing; running it needs only a file, written afresh
under a temporary home for every test.
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.adapters.duckdb.adapter import DuckdbAdapter
from app.adapters.duckdb.options import DuckdbOptions
from app.adapters.duckdb.statements import effect_of, format_text, prepare
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
from tests.adapters.duckdb_fixture import FILE, build

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
ENDLESS = "SELECT count(*) FROM range(1000000000000) a"


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


@pytest.fixture
def adapter(home: Path) -> DuckdbAdapter:
    return DuckdbAdapter(DuckdbOptions(path=FILE), home)


def _request(text: str, mode: str = "read", **extra: object) -> QueryRequest:
    return QueryRequest(text=text, mode=mode, limits=LIMITS, **extra)  # type: ignore[arg-type]  # the mode is one of three literals


async def _finished(execution: QueryExecution) -> list[StatementFinished]:
    return [event async for event in execution.events() if isinstance(event, StatementFinished)]


async def _rows(adapter: DuckdbAdapter, text: str, mode: str = "read") -> list[list[str | None]]:
    finished = await _finished(adapter.open_query(_request(text, mode)))
    assert finished[-1].status == "succeeded", finished[-1].diagnostic
    assert finished[-1].result is not None
    return finished[-1].result.rows


# --- Reading the text (D392) ------------------------------------------------


def test_the_type_claims_the_whole_console(adapter: DuckdbAdapter) -> None:
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
    assert (profile.dialect, profile.parameter_syntax) == ("duckdb", "named_dollar")
    assert profile.runs_unclassified is False


def test_statements_end_where_duckdbs_tokens_say() -> None:
    text = (
        "SELECT ';' AS a; SELECT \"x;y\" FROM t -- ;\n; /* ; */ SELECT $$a;b$$;\n"
        "  SELECT 2  -- trailing\n"
    )
    script = prepare(text)

    assert [statement.text for statement in script.statements] == [
        "SELECT ';' AS a",
        'SELECT "x;y" FROM t',
        "SELECT $$a;b$$",
        "SELECT 2",
    ]
    assert all(text[s.start : s.end] == s.text for s in script.statements)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("SELECT 1", "read"),
        ("WITH q AS (SELECT 1) SELECT * FROM q", "read"),
        ("FROM items", "read"),
        ("DESCRIBE items", "read"),
        ("SHOW TABLES", "read"),
        ("SUMMARIZE items", "read"),
        ("PIVOT items ON name USING sum(price)", "read"),
        ("CALL pragma_version()", "read"),
        ("PRAGMA table_info('items')", "read"),
        ("PRAGMA version", "read"),
        ("INSERT INTO labels VALUES (3, 'blue')", "dml"),
        ("UPDATE items SET price = 1 WHERE id = 1", "dml"),
        ("DELETE FROM events", "dml"),
        ("TRUNCATE events", "dml"),
        ("MERGE INTO labels USING labels s ON labels.id = s.id WHEN MATCHED THEN DELETE", "dml"),
        ("CREATE TABLE t (a INTEGER)", "ddl"),
        ("CREATE OR REPLACE VIEW v AS SELECT 1", "ddl"),
        ("ALTER TABLE items ADD COLUMN b INTEGER", "ddl"),
        ("COMMENT ON TABLE items IS 'x'", "ddl"),
        ("DROP TABLE events", "ddl"),
        ("CREATE MACRO twice(x) AS x * 2", "ddl"),
        ("EXPLAIN SELECT 1", "explain"),
        ("EXPLAIN ANALYZE SELECT 1", "explain"),
        ("EXPLAIN ANALYZE DELETE FROM events", "dml"),
        ("BEGIN", "transaction"),
        ("CHECKPOINT", "maintenance"),
        ("VACUUM", "maintenance"),
        ("ANALYZE", "maintenance"),
        ("SET threads = 1", "session"),
        ("USE \"sales.eu\"", "session"),
        ("PRAGMA threads = 1", "session"),
        ("ATTACH 'other.duckdb' AS o", "session"),
        ("COPY items TO 'x.csv'", "session"),
        ("EXPORT DATABASE 'out'", "session"),
        ("IMPORT DATABASE 'out'", "session"),
        ("INSTALL spatial", "session"),
        ("LOAD spatial", "session"),
        ("UPDATE EXTENSIONS", "session"),
        ("PREPARE p AS SELECT 1", "session"),
        ("CREATE SECRET s (TYPE s3)", "session"),
    ],
)
def test_a_statement_is_classed_by_duckdbs_parser(text: str, kind: str) -> None:
    assert prepare(text).statements[0].kind == kind


def test_what_reaches_past_the_file_is_refused_with_a_reason() -> None:
    refused = {
        statement.text: statement.refused
        for statement in prepare(
            "ATTACH 'o.duckdb' AS o; COPY items TO 'x.csv'; INSTALL spatial; SET threads = 1;"
            " PREPARE p AS SELECT 1; CREATE SECRET s (TYPE s3); SELECT 1"
        ).statements
    }

    assert refused["ATTACH 'o.duckdb' AS o"] == "A connection to this file opens no other database"
    assert "INSERT … SELECT" in (refused["COPY items TO 'x.csv'"] or "")
    assert refused["INSTALL spatial"] == "Extensions are not installed or loaded here"
    assert refused["SET threads = 1"] is not None
    assert refused["PREPARE p AS SELECT 1"] is not None
    assert refused["CREATE SECRET s (TYPE s3)"] is not None
    assert refused["SELECT 1"] is None


def test_a_statement_duckdb_cannot_parse_is_refused_with_its_sentence() -> None:
    first, second = prepare("SELEC 1; SELECT 2").statements

    assert first.kind == "unknown"
    assert first.refused is not None and "syntax error" in first.refused
    assert "LINE" not in first.refused
    assert (second.kind, second.refused) == ("read", None)


def test_risk_destruction_parameters_and_targets_are_read() -> None:
    script = prepare(
        "DELETE FROM events; DELETE FROM events WHERE kind = $kind;"
        " CREATE OR REPLACE TABLE items AS SELECT 1; DROP VIEW cheap;"
        " SELECT * FROM \"sales.eu\".orders WHERE id = $id AND $id > $floor"
    )
    risky = [statement.risk for statement in script.statements]
    destructive = [statement.destructive for statement in script.statements]

    assert risky == ["high", "low", "high", "high", "low"]
    assert destructive == [False, False, True, True, False]
    assert script.statements[1].parameters == ["kind"]
    assert script.statements[4].parameters == ["id", "floor"]
    assert script.statements[4].targets == ["sales.eu.orders"]
    assert script.parameters == ["kind", "id", "floor"]


def test_a_structure_change_names_what_it_changed() -> None:
    assert effect_of("CREATE TABLE t (a INTEGER)").reload_node_ids == ["main"]
    assert effect_of('CREATE TABLE "sales.eu".t (a INTEGER)').reload_node_ids == ["sales\\.eu"]
    assert effect_of("ALTER TABLE items ADD COLUMN b INTEGER").relation_node_ids == ["main.items"]
    assert effect_of("ALTER TABLE items RENAME TO wares").reload_node_ids == ["main"]
    assert effect_of("CREATE INDEX i ON items (name)").relation_node_ids == ["main.items"]
    assert effect_of("DROP INDEX i").scope == "connection"
    assert effect_of("CREATE SCHEMA s").reload_node_ids == [None]
    assert effect_of("COMMENT ON TABLE items IS 'x'").relation_node_ids == ["main.items"]
    assert effect_of("CREATE TEMP TABLE t (a INTEGER)").is_empty()
    assert effect_of("CREATE TABLE t (a INTEGER)", "sales.eu").reload_node_ids == ["sales\\.eu"]


def test_only_reads_and_row_changes_are_laid_out_again() -> None:
    assert format_text("select a,b from t where a=1") != "select a,b from t where a=1"
    ddl = "create table t (a integer)"
    assert format_text(ddl) == ddl
    with_parameter = "select * from t where a = $a"
    assert format_text(with_parameter) == with_parameter


# --- Running it (D393, D394) ------------------------------------------------


async def test_a_read_answers_in_duckdbs_own_text(adapter: DuckdbAdapter) -> None:
    finished = await _finished(
        adapter.open_query(
            _request(
                "SELECT huge, exact, moment, span, tags, point, picture, 1 AS a, 2 AS a"
                " FROM kinds WHERE id = 1"
            )
        )
    )
    result = finished[0].result

    assert result is not None
    assert [column.name for column in result.columns][-2:] == ["a", "a"]
    assert result.rows == [
        [
            "170141183460469231731687303715884105727",
            "12345678901234567890.0123456789",
            "2026-01-02 00:04:05+00",
            "1 year 2 days 03:00:00",
            '["a",null]',
            '{"x":1,"the label":"p"}',
            "0xAA00",
            "1",
            "2",
        ]
    ]
    assert result.columns[0].type.category == "number"
    assert result.columns[4].type.category == "array"


async def test_reads_that_are_not_selects_answer_too(adapter: DuckdbAdapter) -> None:
    assert (await _rows(adapter, "PRAGMA version"))[0][0] is not None
    assert ["id", "INTEGER"] == (await _rows(adapter, "DESCRIBE items"))[0][:2]
    pivoted = await _finished(adapter.open_query(_request("PIVOT events ON kind USING count(*)")))
    assert pivoted[0].result is not None
    assert [column.name for column in pivoted[0].result.columns] == ["step", "a", "b", "c"]


async def test_parameters_are_bound_by_name(adapter: DuckdbAdapter) -> None:
    finished = await _finished(
        adapter.open_query(
            _request(
                "SELECT name FROM items WHERE price > $floor AND $floor IS NOT NULL ORDER BY id",
                parameters=[ParameterValue(name="floor", value="5")],
            )
        )
    )

    assert finished[0].result is not None
    assert finished[0].result.rows == [["100% pure"], ["under_score"]]


async def test_a_file_of_the_home_is_read_and_nothing_outside_it(
    adapter: DuckdbAdapter, home: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    (home / "data" / "sales.csv").write_text("amount\n5\n7\n")
    outside = tmp_path_factory.mktemp("elsewhere") / "secret.csv"
    outside.write_text("x\n1\n")

    assert await _rows(adapter, "SELECT sum(amount) FROM '~/data/sales.csv'") == [["12"]]
    # The person's own SQL naming a path the test made, as the console runs it.
    reaching = f"SELECT * FROM read_csv('{outside.as_posix()}')"  # noqa: S608
    refused = await _finished(adapter.open_query(_request(reaching)))
    assert refused[0].status == "failed"
    assert refused[0].diagnostic is not None
    assert refused[0].diagnostic.category == "permission"


async def test_a_failure_writes_the_home_as_a_tilde(adapter: DuckdbAdapter, home: Path) -> None:
    missing = f"SELECT * FROM '{home.as_posix()}/data/none.csv'"  # noqa: S608
    finished = await _finished(adapter.open_query(_request(missing)))

    assert finished[0].status == "failed"
    assert finished[0].diagnostic is not None
    message = finished[0].diagnostic.message
    assert "~/data/none.csv" in message
    assert home.as_posix() not in message and str(home) not in message
    assert "LINE" not in message


async def test_a_read_cannot_write(adapter: DuckdbAdapter) -> None:
    finished = await _finished(adapter.open_query(_request("DELETE FROM events")))

    assert finished[0].status == "failed"
    assert finished[0].diagnostic is not None
    assert finished[0].diagnostic.category == "read_only"
    assert await _rows(adapter, "SELECT count(*) FROM events") == [["4"]]


async def test_a_refused_statement_is_not_run_in_any_mode(adapter: DuckdbAdapter, home: Path) -> None:
    finished = await _finished(
        adapter.open_query(_request("COPY items TO '~/data/out.csv'", "auto_commit"))
    )

    assert finished[0].status == "failed"
    assert not (home / "data" / "out.csv").exists()


async def test_an_auto_commit_run_is_one_transaction_with_its_structure(
    adapter: DuckdbAdapter,
) -> None:
    failed = await _finished(
        adapter.open_query(
            _request(
                "CREATE TABLE made (a INTEGER); INSERT INTO made VALUES (1); SELECT * FROM nope",
                "auto_commit",
            )
        )
    )
    done = await _finished(
        adapter.open_query(
            _request("CREATE TABLE made (a INTEGER); INSERT INTO made VALUES (1), (2)", "auto_commit")
        )
    )

    assert [one.status for one in failed] == ["succeeded", "succeeded", "failed"]
    assert done[1].affected_rows == 2
    assert done[0].effect is not None and done[0].effect.reload_node_ids == ["main"]
    assert await _rows(adapter, "SELECT count(*) FROM made") == [["2"]]


async def test_returning_answers_rows_and_runs_once(adapter: DuckdbAdapter) -> None:
    finished = await _finished(
        adapter.open_query(
            _request("INSERT INTO labels VALUES (3, 'blue') RETURNING id, name", "auto_commit")
        )
    )

    assert finished[0].result is not None
    assert finished[0].result.rows == [["3", "blue"]]
    assert await _rows(adapter, "SELECT count(*) FROM labels") == [["3"]]


async def test_maintenance_runs_outside_a_transaction(adapter: DuckdbAdapter) -> None:
    finished = await _finished(adapter.open_query(_request("CHECKPOINT", "auto_commit")))

    assert finished[0].status == "succeeded", finished[0].diagnostic


async def test_a_statement_past_its_time_is_stopped(adapter: DuckdbAdapter) -> None:
    limits = LIMITS.model_copy(update={"statement_timeout_seconds": 1})
    finished = await _finished(
        adapter.open_query(QueryRequest(text=ENDLESS, mode="read", limits=limits))
    )

    assert finished[0].status == "timed_out"


async def test_stop_cancels_the_running_statement(adapter: DuckdbAdapter) -> None:
    execution = adapter.open_query(_request(ENDLESS))
    collected: list[StatementFinished] = []

    async def run() -> None:
        collected.extend(await _finished(execution))

    task = asyncio.create_task(run())
    await asyncio.sleep(0.5)
    started = time.monotonic()
    await execution.cancel()
    await task

    assert collected[0].status == "cancelled"
    assert time.monotonic() - started < 5


async def test_the_search_path_is_the_files_schemas(adapter: DuckdbAdapter) -> None:
    finished = await _finished(
        adapter.open_query(_request("SELECT id FROM orders", search_path=["sales.eu"]))
    )
    assert finished[0].result is not None and finished[0].result.rows == [["10"]]

    with pytest.raises(AdapterError):
        await _finished(adapter.open_query(_request("SELECT 1", search_path=["nowhere"])))


# --- A transaction held open, and a rehearsal -------------------------------


async def test_a_held_transaction_changes_structure_and_rolls_back(
    adapter: DuckdbAdapter,
) -> None:
    transaction = await adapter.begin_transaction(TransactionContext())
    try:
        made = await _finished(transaction.execute(_request("CREATE TABLE held (a INTEGER)")))
        seen = await _finished(transaction.execute(_request("SELECT count(*) FROM held")))
        run = transaction.execute(_request("INSERT INTO held VALUES (1); SELECT * FROM missing"))
        finished = await _finished(run)
        transaction.absorb(run)
        state = transaction.state()
    finally:
        await transaction.rollback()

    assert made[0].status == "succeeded"
    assert seen[0].result is not None and seen[0].result.rows == [["0"]]
    assert [one.status for one in finished] == ["succeeded", "failed"]
    # Any failure aborts a DuckDB transaction (D393).
    assert (state.open, state.broken) == (True, True)
    gone = await _finished(adapter.open_query(_request("SELECT * FROM held")))
    assert gone[0].status == "failed"


def _another_program_opens(path: Path) -> bool:
    opened = subprocess.run(
        [sys.executable, "-c", "import duckdb, sys; duckdb.connect(sys.argv[1], read_only=True)", str(path)],
        capture_output=True,
        check=False,
    )
    return opened.returncode == 0


async def test_a_held_transaction_commits_and_holds_the_file_meanwhile(
    adapter: DuckdbAdapter, home: Path
) -> None:
    transaction = await adapter.begin_transaction(TransactionContext())
    await _finished(transaction.execute(_request("INSERT INTO labels VALUES (3, 'blue')")))
    # Another program is locked out while the transaction is held (D393).
    held = await asyncio.to_thread(_another_program_opens, home / FILE)
    await transaction.commit()
    released = await asyncio.to_thread(_another_program_opens, home / FILE)

    assert (held, released) == (False, True)

    assert await _rows(adapter, "SELECT count(*) FROM labels") == [["3"]]
    assert transaction.state().open is False


async def test_a_change_is_rehearsed_and_undone(adapter: DuckdbAdapter) -> None:
    rehearsal = await adapter.rehearse_query(
        _request("DELETE FROM events WHERE kind = 'a'; DROP TABLE events", "auto_commit")
    )

    assert rehearsal.runnable
    assert [one.outcome for one in rehearsal.statements] == ["ok", "ok"]
    assert rehearsal.statements[0].affected_rows == 2
    assert rehearsal.effect.reload_node_ids == ["main"]
    assert await _rows(adapter, "SELECT count(*) FROM events") == [["4"]]


async def test_a_rehearsal_inside_a_held_transaction_is_refused(adapter: DuckdbAdapter) -> None:
    transaction = await adapter.begin_transaction(TransactionContext())
    try:
        with pytest.raises(AdapterError, match="savepoints"):
            await transaction.rehearse(_request("DROP TABLE events", "manual"))
    finally:
        await transaction.rollback()


# --- Explain, completion and generated statements ---------------------------


async def test_a_plan_is_a_tree_of_duckdbs_operators(adapter: DuckdbAdapter) -> None:
    result = await adapter.explain_query(
        ExplainRequest(text="SELECT name, count(*) FROM items WHERE price > 1 GROUP BY name")
    )

    kinds: list[str] = []

    def walk(node: object) -> None:
        kinds.append(node.kind)  # type: ignore[attr-defined]  # an ExplainNode
        for child in node.children:  # type: ignore[attr-defined]  # an ExplainNode
            walk(child)

    walk(result.plan)
    assert "HASH_GROUP_BY" in kinds
    assert any(kind.endswith("SCAN") for kind in kinds)
    assert result.raw


async def test_explain_refuses_what_it_does_not_plan(adapter: DuckdbAdapter) -> None:
    with pytest.raises(ValueError):
        await adapter.explain_query(ExplainRequest(text="CREATE TABLE t (a INTEGER)"))
    with pytest.raises(ValueError):
        await adapter.explain_query(ExplainRequest(text="SELECT 1; SELECT 2"))


async def test_completion_knows_every_schema_and_the_columns_asked_for(
    adapter: DuckdbAdapter,
) -> None:
    metadata = await adapter.query_metadata(
        QueryMetadataRequest(relations=["items", "sales.eu.orders", "orders"], search_path=["sales.eu"])
    )

    assert metadata.schemas == ["main", "sales.eu"]
    assert {(one.schema_name, one.name) for one in metadata.relations} >= {
        ("main", "items"),
        ("sales.eu", "orders"),
    }
    assert [column.name for column in metadata.columns["items"]] == [
        "id",
        "name",
        "price",
        "label_id",
    ]
    assert [column.name for column in metadata.columns["orders"]] == ["id", "item"]


async def test_statements_about_a_node_are_quoted_by_duckdb(adapter: DuckdbAdapter) -> None:
    generated = await adapter.generate_query(
        GenerateQueryRequest(node_id="sales\\.eu.orders", kind="select")
    )

    assert generated.text == 'SELECT "id", "item"\nFROM "sales.eu"."orders"\nLIMIT 100'
    with pytest.raises(ValueError):
        await adapter.generate_query(GenerateQueryRequest(node_id="main.nothing"))
