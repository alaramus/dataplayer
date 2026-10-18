"""The SQL console of a MySQL source (D62, D232, D233).

Reading the text needs no server; running it is tried on MySQL and MariaDB.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator

import pytest

from app.adapters.mysql import ids
from app.adapters.mysql.statements import bind, bound_names, format_text, prepare
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
from tests.adapters.mysql_fixture import (
    DATABASE,
    TARGETS,
    Target,
    build,
    run,
    tear_down,
)

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
ITEMS = f"`{DATABASE}`.items"


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    yield chosen
    await tear_down(chosen)


def _request(text: str, mode: str = "read", **extra: object) -> QueryRequest:
    return QueryRequest(text=text, mode=mode, limits=LIMITS, **extra)  # type: ignore[arg-type]  # the mode is one of three literals


async def _finished(execution: QueryExecution) -> list[StatementFinished]:
    return [event async for event in execution.events() if isinstance(event, StatementFinished)]


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
        ("SHOW TABLES", "read"),
        ("DESCRIBE t", "read"),
        ("WITH c AS (SELECT 1) SELECT * FROM c", "read"),
        ("EXPLAIN SELECT 1", "explain"),
        ("INSERT INTO t VALUES (1)", "dml"),
        ("REPLACE INTO t VALUES (1)", "dml"),
        ("UPDATE t SET a = 1 WHERE b = 2", "dml"),
        ("CREATE TABLE t (a INT)", "ddl"),
        ("DROP DATABASE d", "ddl"),
        ("ALTER TABLE t ENGINE = InnoDB", "ddl"),
        ("TRUNCATE t", "ddl"),
        ("START TRANSACTION", "transaction"),
        ("USE d", "session"),
        ("SELECT a INTO @v FROM t", "session"),
        ("ANALYZE TABLE t", "maintenance"),
        # What the parser does not model is not run, whatever it looks like.
        ("FLUSH PRIVILEGES", "unknown"),
        ("TABLE t", "unknown"),
        ("CALL p()", "unknown"),
        ("LOAD DATA INFILE 'x' INTO TABLE t", "unknown"),
        ("SELECT * INTO OUTFILE '/tmp/x' FROM t", "unknown"),
    ],
)
def test_a_statement_is_classed_by_the_parser(text: str, kind: str) -> None:
    assert prepare(text).statements[0].kind == kind


def test_the_vocabulary_of_structure_changes_is_closed() -> None:
    def refused(text: str) -> str | None:
        return prepare(text).statements[0].refused

    assert refused("CREATE TABLE t (a INT)") is None
    assert refused("CREATE DATABASE d") is None
    assert refused("RENAME TABLE a TO b") is None
    assert refused("CREATE USER u") is not None
    assert refused("GRANT ALL ON *.* TO u") is not None
    assert refused("CREATE PROCEDURE p() SELECT 1") is not None
    assert refused("ALTER DATABASE d CHARACTER SET utf8mb4") is not None
    assert refused("RENAME USER a TO b") is not None


def test_what_cannot_be_undone_is_said() -> None:
    def destructive(text: str) -> bool:
        return prepare(text).statements[0].destructive

    assert destructive("DROP TABLE t")
    assert destructive("TRUNCATE t")
    assert destructive("ALTER TABLE t DROP COLUMN a")
    assert destructive("ALTER TABLE t MODIFY a BIGINT")
    assert not destructive("ALTER TABLE t ADD COLUMN a INT")
    assert prepare("UPDATE t SET a = 1").statements[0].risk == "high"
    assert prepare("UPDATE t SET a = 1 WHERE b = 2").statements[0].risk == "low"


def test_parameters_are_named_and_bound_in_place() -> None:
    text = "SELECT ':no', @a := 1, a FROM t WHERE a = :x AND b LIKE 'p%' AND c = :x OR d = :y"

    assert prepare(text).parameters == ["x", "y"]
    assert bound_names(text) == ["x", "x", "y"]
    assert bind(text) == (
        "SELECT ':no', @a := 1, a FROM t WHERE a = %s AND b LIKE 'p%%' AND c = %s OR d = %s"
    )


def test_formatting_keeps_what_it_cannot_read_back() -> None:
    assert format_text("select a,b from t where a=1") != "select a,b from t where a=1"
    assert format_text("SELECT * FROM t WHERE a = :x") == "SELECT * FROM t WHERE a = :x"
    assert format_text("FLUSH PRIVILEGES") == "FLUSH PRIVILEGES"


# --- The capability as a whole -----------------------------------------


async def test_the_console_is_offered_without_a_rehearsal(target: Target) -> None:
    adapter = target.adapter()

    for capability in (
        SupportsQuery,
        SupportsTransactions,
        SupportsExplain,
        SupportsQueryMetadata,
        SupportsQueryFormatting,
    ):
        assert isinstance(adapter, capability)
    # MySQL commits a structure change at once, so it cannot be undone (D233).
    assert not isinstance(adapter, SupportsRehearsal)
    assert adapter.query_profile().parameter_syntax == "named_colon"


# --- Running -------------------------------------------------------------


async def test_a_read_keeps_columns_apart_and_values_exact(target: Target) -> None:
    finished = await _finished(
        target.adapter().open_query(
            _request(f"SELECT id, label AS id, amount, seen FROM {ITEMS} ORDER BY 1 LIMIT 1")
        )
    )

    result = finished[0].result
    assert finished[0].status == "succeeded", finished[0].diagnostic
    assert result is not None
    assert [column.name for column in result.columns] == ["id", "id", "amount", "seen"]
    assert result.rows == [
        ["1", "alpha", "12345678901234567890.0123456789", "2024-01-02T03:04:05+00:00"]
    ]


async def test_a_read_refuses_a_write_by_its_class(target: Target) -> None:
    finished = await _finished(
        target.adapter().open_query(_request(f"DELETE FROM {ITEMS} WHERE id = 1"))
    )

    assert finished[0].status == "failed"
    assert finished[0].diagnostic is not None
    assert finished[0].diagnostic.category == "read_only"


async def test_parameters_are_bound_rather_than_written_in(target: Target) -> None:
    finished = await _finished(
        target.adapter().open_query(
            _request(
                f"SELECT label FROM {ITEMS} WHERE label = :name OR label = :name",
                parameters=[ParameterValue(name="name", value="alpha' OR '1'='1")],
            )
        )
    )

    assert finished[0].result is not None
    assert finished[0].result.rows == []


async def test_the_default_database_is_the_document_s(target: Target) -> None:
    finished = await _finished(
        target.adapter().open_query(
            _request("SELECT COUNT(*) FROM items", search_path=[DATABASE])
        )
    )

    assert finished[0].result is not None
    assert finished[0].result.rows == [["3"]]


async def test_a_server_warning_is_a_notice(target: Target) -> None:
    finished = await _finished(
        target.adapter().open_query(_request("SELECT CAST('12abc' AS SIGNED) AS n"))
    )

    assert finished[0].notices
    assert finished[0].result is not None
    assert finished[0].result.rows == [["12"]]


async def test_an_auto_commit_run_is_one_transaction(target: Target) -> None:
    adapter = target.adapter()
    label = f"run {uuid.uuid4().hex[:6]}"

    finished = await _finished(
        adapter.open_query(
            _request(
                f"INSERT INTO {ITEMS} (label) VALUES ('{label}'); SELECT no_such_column FROM {ITEMS}",
                mode="auto_commit",
            )
        )
    )
    after = await _finished(
        adapter.open_query(_request(f"SELECT COUNT(*) FROM {ITEMS} WHERE label = '{label}'"))
    )

    assert [one.status for one in finished] == ["succeeded", "failed"]
    assert finished[0].affected_rows == 1
    assert finished[1].diagnostic is not None
    assert finished[1].diagnostic.category == "missing_object"
    # The insert went with the failure.
    assert after[0].result is not None
    assert after[0].result.rows == [["0"]]


async def test_a_structure_change_runs_alone_and_names_what_changed(target: Target) -> None:
    adapter = target.adapter()

    together = await _finished(
        adapter.open_query(
            _request(f"CREATE TABLE `{DATABASE}`.made (a INT); SELECT 1", mode="auto_commit")
        )
    )
    alone = await _finished(
        adapter.open_query(_request(f"CREATE TABLE `{DATABASE}`.made (a INT)", mode="auto_commit"))
    )
    await run(target, f"DROP TABLE `{DATABASE}`.made")

    assert together[0].status == "failed"
    assert together[1].status == "not_run"
    assert alone[0].status == "succeeded"
    assert alone[0].effect is not None
    assert alone[0].effect.reload_node_ids == [ids.database_id(DATABASE)]


async def test_a_held_transaction_ends_as_it_is_told(target: Target) -> None:
    adapter = target.adapter()
    label = f"held {uuid.uuid4().hex[:6]}"

    async def count() -> str | None:
        finished = await _finished(
            adapter.open_query(_request(f"SELECT COUNT(*) FROM {ITEMS} WHERE label = '{label}'"))
        )
        assert finished[0].result is not None
        return finished[0].result.rows[0][0]

    held = await adapter.begin_transaction(TransactionContext())
    insert = held.execute(_request(f"INSERT INTO {ITEMS} (label) VALUES ('{label}')", mode="manual"))
    await _finished(insert)
    held.absorb(insert)
    # A failed statement leaves a MySQL transaction usable.
    broken = held.execute(_request(f"SELECT nothing FROM {ITEMS}", mode="manual"))
    await _finished(broken)
    held.absorb(broken)
    ddl = held.execute(_request(f"CREATE TABLE `{DATABASE}`.never (a INT)", mode="manual"))
    refused = await _finished(ddl)
    held.absorb(ddl)

    assert held.state().affected_rows == 1
    assert not held.state().broken
    assert refused[0].status == "failed"
    assert await count() == "0"
    await held.commit()
    assert await count() == "1"
    await run(target, f"DELETE FROM {ITEMS} WHERE label = '{label}'")


async def test_a_rolled_back_transaction_leaves_nothing(target: Target) -> None:
    adapter = target.adapter()
    held = await adapter.begin_transaction(TransactionContext(search_path=[DATABASE]))
    await _finished(held.execute(_request("DELETE FROM keyless", mode="manual")))
    await held.rollback()

    finished = await _finished(adapter.open_query(_request(f"SELECT COUNT(*) FROM `{DATABASE}`.keyless")))
    assert finished[0].result is not None
    assert finished[0].result.rows == [["3"]]
    with pytest.raises(AdapterError):
        await held.rehearse(_request("DROP TABLE keyless", mode="manual"))


async def test_a_long_statement_is_stopped_by_its_limit(target: Target) -> None:
    request = _request("SELECT SLEEP(5)").model_copy(
        update={"limits": LIMITS.model_copy(update={"statement_timeout_seconds": 1})}
    )

    finished = await _finished(target.adapter().open_query(request))

    assert finished[0].status == "timed_out"
    assert finished[0].duration_ms < 4000


async def test_stop_kills_what_is_running(target: Target) -> None:
    execution = target.adapter().open_query(
        _request("SELECT BENCHMARK(5000000000, MD5('x')); SELECT 1")
    )
    events = execution.events()
    collected: list[StatementFinished] = []

    async def consume() -> None:
        async for event in events:
            if isinstance(event, StatementFinished):
                collected.append(event)

    task = asyncio.create_task(consume())
    await asyncio.sleep(1)
    await execution.cancel()
    await asyncio.wait_for(task, 10)

    assert [one.status for one in collected] == ["cancelled", "not_run"]


# --- Explain, completion, generation -------------------------------------


async def test_a_plan_is_read_as_a_tree_and_as_text(target: Target) -> None:
    plan = await target.adapter().explain_query(
        ExplainRequest(text=f"SELECT * FROM {ITEMS} WHERE id = :id", parameters=[ParameterValue(name="id", value="1")])
    )

    assert plan.plan.kind == "query_block"
    labels = []

    def walk(node: object) -> None:
        labels.append(node.label)  # type: ignore[attr-defined]  # an ExplainNode
        for child in node.children:  # type: ignore[attr-defined]  # the same
            walk(child)

    walk(plan.plan)
    assert any("items" in label for label in labels)
    assert "table" in plan.raw.splitlines()[0]
    with pytest.raises(ValueError):
        await target.adapter().explain_query(ExplainRequest(text=f"DELETE FROM {ITEMS}"))


async def test_completion_reads_the_document_s_database(target: Target) -> None:
    metadata = await target.adapter().query_metadata(
        QueryMetadataRequest(search_path=[DATABASE], relations=[f"{DATABASE}.items"])
    )

    assert DATABASE in metadata.schemas
    assert {relation.name for relation in metadata.relations} >= {"items", "item_labels"}
    assert [column.name for column in metadata.columns[f"{DATABASE}.items"]][:2] == ["id", "label"]


async def test_a_generated_statement_quotes_every_name(target: Target) -> None:
    generated = await target.adapter().generate_query(
        GenerateQueryRequest(node_id=ids.relation_id(DATABASE, "items"))
    )

    assert generated.text.startswith("SELECT `id`, `label`, `100%`")
    assert f"FROM `{DATABASE}`.`items`" in generated.text
    finished = await _finished(target.adapter().open_query(_request(generated.text)))
    assert finished[0].status == "succeeded"
