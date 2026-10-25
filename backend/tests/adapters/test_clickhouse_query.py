"""The SQL console of a ClickHouse source (D62, D270, D271).

Reading the text needs no server; running it needs the test ClickHouse.
"""

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.adapters.clickhouse.adapter import ClickhouseAdapter
from app.adapters.clickhouse.session import quoted_name
from app.adapters.clickhouse.statements import format_text, placeholders, prepare
from app.adapters.database_ids import database_id, relation_id
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
)
from tests.adapters.clickhouse_fixture import DATABASE, adapter, build, run, tear_down
from tests.utils.services import CLICKHOUSE

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
ITEMS = f"{quoted_name(DATABASE)}.items"


@pytest.fixture(scope="module")
async def server() -> AsyncIterator[None]:
    CLICKHOUSE.require()
    await build()
    yield
    await tear_down()


def _request(text: str, mode: str = "read", **extra: object) -> QueryRequest:
    return QueryRequest(text=text, mode=mode, limits=LIMITS, **extra)  # type: ignore[arg-type]  # the mode is one of three literals


async def _finished(execution: QueryExecution) -> list[StatementFinished]:
    return [event async for event in execution.events() if isinstance(event, StatementFinished)]


# --- What the source says it does -------------------------------------------


def test_it_claims_the_console_and_no_transaction() -> None:
    source = ClickhouseAdapter.__new__(ClickhouseAdapter)
    for capability in (SupportsQuery, SupportsExplain, SupportsQueryMetadata, SupportsQueryFormatting):
        assert isinstance(source, capability)
    # ClickHouse holds no transaction and undoes nothing (D271).
    assert not isinstance(source, SupportsTransactions)
    assert not isinstance(source, SupportsRehearsal)


def test_the_profile_names_its_own_parameters() -> None:
    profile = adapter().query_profile()

    assert profile.parameter_syntax == "named_braces"
    assert profile.statement_modes == ["read", "auto_commit"]
    assert profile.supports_cancel


# --- Reading the text ----------------------------------------------------


def test_statements_end_where_the_dialect_says() -> None:
    script = prepare("SELECT ';' AS a; SELECT `x;y` FROM t -- ;\n; /* ; */ SELECT 1")

    assert [statement.text for statement in script.statements] == [
        "SELECT ';' AS a",
        "SELECT `x;y` FROM t",
        "SELECT 1",
    ]


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("SELECT 1", "read"),
        ("WITH x AS (SELECT 1) SELECT * FROM x", "read"),
        ("SELECT * FROM t FINAL SETTINGS max_threads = 1", "read"),
        ("SHOW TABLES", "read"),
        ("DESCRIBE TABLE t", "read"),
        ("EXISTS TABLE t", "read"),
        ("EXPLAIN SELECT 1", "explain"),
        ("EXPLAIN PIPELINE SELECT 1", "read"),
        ("EXPLAIN SYNTAX SELECT 1", "read"),
        ("INSERT INTO t VALUES (1)", "dml"),
        ("INSERT INTO t SELECT * FROM s", "dml"),
        ('INSERT INTO t FORMAT JSONEachRow {"a": 1}', "dml"),
        ("DELETE FROM t WHERE a = 1", "dml"),
        ("ALTER TABLE t DELETE WHERE a = 1", "dml"),
        ("ALTER TABLE t UPDATE a = 2 WHERE a = 1", "dml"),
        ("CREATE TABLE t (a UInt8) ENGINE = MergeTree ORDER BY a", "ddl"),
        ("ALTER TABLE t ADD COLUMN b UInt8", "ddl"),
        ("RENAME TABLE a TO b", "ddl"),
        ("TRUNCATE TABLE t", "ddl"),
        ("DROP TABLE t", "ddl"),
        ("OPTIMIZE TABLE t FINAL", "maintenance"),
        ("SET max_threads = 1", "session"),
        ("KILL QUERY WHERE 1", "unknown"),
    ],
)
def test_a_statement_is_classed_by_the_parser(text: str, kind: str) -> None:
    assert prepare(text).statements[0].kind == kind


@pytest.mark.parametrize(
    "text",
    [
        "CREATE USER u",
        "GRANT SELECT ON *.* TO u",
        "CREATE FUNCTION f AS (x) -> x + 1",
        "SYSTEM DROP DNS CACHE",
        "DETACH TABLE t",
        "SELECT 1 FORMAT Pretty",
    ],
)
def test_what_falls_outside_the_editor_is_refused_by_name(text: str) -> None:
    assert prepare(text).statements[0].refused


def test_a_change_that_cannot_be_read_back_is_marked() -> None:
    script = prepare(
        "DROP TABLE t; ALTER TABLE t DROP COLUMN a; ALTER TABLE t ADD COLUMN b UInt8; "
        "ALTER TABLE t DELETE WHERE 1"
    )

    assert [statement.destructive for statement in script.statements] == [
        True,
        True,
        False,
        False,
    ]
    # A delete with nothing to bound it is asked about every time (D66).
    assert prepare("DELETE FROM t WHERE 1 = 1").statements[0].risk == "low"
    assert prepare("ALTER TABLE t ADD COLUMN b UInt8").statements[0].risk == "high"


def test_a_parameter_is_the_server_s_own_and_named_once() -> None:
    text = "SELECT {id:UInt32}, {tags: Array(String)}, '{no:String}', {'k': 1}, {id:UInt32}"
    script = prepare(text)

    assert script.parameters == ["id", "tags"]
    assert [name for _, _, name in placeholders(text)] == ["id", "tags", "id"]


def test_formatting_keeps_what_it_cannot_lay_out() -> None:
    assert format_text("select a,b from t where a=1") == "SELECT\n  a,\n  b\nFROM t\nWHERE\n  a = 1"
    kept = "SYSTEM FLUSH LOGS"
    assert format_text(kept) == kept


# --- Running it ----------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_a_read_answers_with_its_columns_types_and_values() -> None:
    [finished] = await _finished(
        adapter().open_query(_request(f"SELECT id, amount, made, tags FROM {ITEMS} ORDER BY id LIMIT 2"))
    )

    assert finished.status == "succeeded", finished.diagnostic
    assert finished.result is not None
    assert [column.name for column in finished.result.columns] == ["id", "amount", "made", "tags"]
    assert finished.result.columns[1].type.category == "number"
    assert finished.result.rows[0] == [
        "1",
        "12345678901234567890.0123456789",
        "2024-01-02T03:04:05Z",
        '["a","b\\"c"]',
    ]
    assert finished.row_count == 2


@pytest.mark.usefixtures("server")
async def test_a_parameter_is_parsed_by_the_server_as_its_type() -> None:
    source = adapter()

    [found] = await _finished(
        source.open_query(
            _request(
                f"SELECT label FROM {ITEMS} WHERE id = {{id:UInt32}} OR {{none:Nullable(UInt8)}} = 1",
                parameters=[ParameterValue(name="id", value="2"), ParameterValue(name="none")],
            )
        )
    )
    [refused] = await _finished(
        source.open_query(
            _request("SELECT {id:UInt32}", parameters=[ParameterValue(name="id", value="-1")])
        )
    )

    assert found.result is not None and found.result.rows == [["50% off"]]
    assert refused.status == "failed"
    assert refused.diagnostic is not None and refused.diagnostic.category == "data"


@pytest.mark.usefixtures("server")
async def test_a_read_cannot_write() -> None:
    read, write = await _finished(
        adapter().open_query(_request(f"SELECT 1; INSERT INTO {ITEMS} (id) VALUES (9)"))
    )

    assert read.status == "succeeded"
    # Refused by its class before the server is asked.
    assert write.status == "failed"
    assert write.diagnostic is not None and write.diagnostic.code == "dp_not_admitted"


@pytest.mark.usefixtures("server")
async def test_the_server_refuses_a_write_a_read_carries() -> None:
    """readonly=2 is the server's own guard, under the class (D271)."""
    [finished] = await _finished(
        adapter().open_query(_request("SELECT 1 SETTINGS readonly = 0"))
    )

    assert finished.status == "failed"
    assert finished.diagnostic is not None
    assert finished.diagnostic.category == "read_only"


@pytest.mark.usefixtures("server")
async def test_a_change_runs_alone_and_says_what_it_touched() -> None:
    source = adapter()
    table = f"{quoted_name(DATABASE)}.made_here"

    [created] = await _finished(
        source.open_query(
            _request(f"CREATE TABLE {table} (a UInt8) ENGINE = MergeTree ORDER BY a", mode="auto_commit")
        )
    )
    [inserted] = await _finished(
        source.open_query(_request(f"INSERT INTO {table} VALUES (1), (2), (3)", mode="auto_commit"))
    )
    [deleted] = await _finished(
        source.open_query(_request(f"ALTER TABLE {table} DELETE WHERE a = 1", mode="auto_commit"))
    )
    together = await _finished(
        source.open_query(
            _request(f"INSERT INTO {table} VALUES (4); SELECT count() FROM {table}", mode="auto_commit")
        )
    )
    [counted] = await _finished(source.open_query(_request(f"SELECT count() FROM {table}")))

    assert created.status == "succeeded", created.diagnostic
    assert created.effect is not None
    assert created.effect.reload_node_ids == [database_id(DATABASE)]
    assert inserted.affected_rows == 3
    # A mutation is waited for, so the count after it is already true.
    assert deleted.status == "succeeded", deleted.diagnostic
    # ClickHouse keeps a change at once, so it shares a run with nothing (D271).
    assert together[0].status == "failed"
    assert together[0].diagnostic is not None
    assert together[0].diagnostic.code == "dp_not_admitted"
    assert together[1].status == "not_run"
    assert counted.result is not None and counted.result.rows == [["2"]]


@pytest.mark.usefixtures("server")
async def test_a_failure_carries_the_server_s_sentence_and_where() -> None:
    [finished] = await _finished(adapter().open_query(_request("SELECT 1 FROM system.one FOR UPDATE")))
    [missing] = await _finished(adapter().open_query(_request("SELECT * FROM dp_gone.nothing")))

    assert finished.status == "failed"
    assert finished.diagnostic is not None
    assert finished.diagnostic.category == "syntax"
    assert finished.diagnostic.position is not None
    assert "DB::Exception" not in finished.diagnostic.message
    assert missing.diagnostic is not None and missing.diagnostic.category == "missing_object"


@pytest.mark.usefixtures("server")
async def test_a_long_result_is_cut_and_says_so() -> None:
    limits = LIMITS.model_copy(update={"max_result_rows": 5})
    [finished] = await _finished(
        adapter().open_query(QueryRequest(text="SELECT number FROM system.numbers", mode="read", limits=limits))
    )

    assert finished.result is not None
    assert finished.result.truncated
    assert [row[0] for row in finished.result.rows] == ["0", "1", "2", "3", "4"]


@pytest.mark.usefixtures("server")
async def test_a_statement_is_stopped_by_its_time_and_by_stop() -> None:
    source = adapter()
    limits = LIMITS.model_copy(update={"statement_timeout_seconds": 1})
    slow = "SELECT count() FROM numbers(100000000000)"

    [timed] = await _finished(source.open_query(QueryRequest(text=slow, mode="read", limits=limits)))
    execution = source.open_query(_request(slow))
    collected = asyncio.ensure_future(_finished(execution))
    await asyncio.sleep(1)
    await execution.cancel()
    [cancelled] = await collected

    assert timed.status == "timed_out"
    assert cancelled.status == "cancelled"


@pytest.mark.usefixtures("server")
async def test_a_search_path_names_the_database_and_is_checked() -> None:
    [finished] = await _finished(
        adapter().open_query(_request("SELECT count() FROM items", search_path=[DATABASE]))
    )

    assert finished.result is not None and finished.result.rows == [["3"]]
    with pytest.raises(AdapterError):
        await _finished(adapter().open_query(_request("SELECT 1", search_path=["dp_gone"])))


# --- Explain, completion and generated statements ------------------------


@pytest.mark.usefixtures("server")
async def test_explain_reads_the_plan_tree_and_its_text() -> None:
    result = await adapter().explain_query(
        ExplainRequest(text=f"SELECT label FROM {ITEMS} WHERE id > {{id:UInt32}}", parameters=[ParameterValue(name="id", value="1")])
    )

    kinds = [result.plan.kind]
    stack = list(result.plan.children)
    while stack:
        node = stack.pop()
        kinds.append(node.kind)
        stack.extend(node.children)
    assert "ReadFromMergeTree" in kinds
    assert "ReadFromMergeTree" in result.raw
    with pytest.raises(ValueError):
        await adapter().explain_query(ExplainRequest(text=f"DROP TABLE {ITEMS}"))
    with pytest.raises(ValueError):
        await adapter().explain_query(ExplainRequest(text="SELECT * FROM dp_gone.nothing"))


@pytest.mark.usefixtures("server")
async def test_completion_is_asked_for_progressively() -> None:
    metadata = await adapter().query_metadata(
        QueryMetadataRequest(search_path=[DATABASE], relations=[f"{DATABASE}.items"])
    )

    assert DATABASE in metadata.schemas and "system" in metadata.schemas
    assert {relation.name for relation in metadata.relations} >= {"items", "item_ids"}
    assert not any(relation.name.startswith(".inner") for relation in metadata.relations)
    assert [column.name for column in metadata.columns[f"{DATABASE}.items"]][:2] == ["id", "label"]


@pytest.mark.usefixtures("server")
async def test_a_generated_select_is_quoted_by_the_dialect() -> None:
    generated = await adapter().generate_query(
        GenerateQueryRequest(node_id=relation_id(DATABASE, "items"))
    )

    assert generated.text.startswith("SELECT `id`, `label`, `100%`")
    assert f"FROM {quoted_name(DATABASE)}.`items`" in generated.text
    await run(f"SELECT count() FROM {quoted_name(DATABASE)}.items")
