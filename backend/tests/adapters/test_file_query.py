"""The file source running SQL: what it reads, what it refuses, what it says.

The refusals of D77 are tested through the capability, and the sandbox of D78
is tested behind them — by opening an engine directly and asking it for things
the parse would never have let through, because a defence that is only ever
reached through a check that already refused proves nothing.
"""

import os
import time
from pathlib import Path
from threading import Event

import anyio
import duckdb
import pytest

from app.adapters.explorer import query_readers, records
from app.adapters.explorer.query import (
    _FALLBACKS,
    ExplorerExecution,
    ExplorerQuery,
    _Engine,
    _safe_text,
    diagnostic_of,
    quoted,
)
from app.adapters.explorer.query_readers import FileReaders, Preparation
from app.adapters.explorer.readers import LogReader
from app.adapters.file.storage import LocalStorage
from app.adapters.protocol import AdapterError
from app.adapters.query import (
    ExplainRequest,
    GenerateQueryRequest,
    MaterialisedResult,
    ParameterValue,
    QueryEvent,
    QueryLimits,
    QueryMetadataRequest,
    QueryRequest,
    StatementFinished,
)

LIMITS = QueryLimits(
    statement_timeout_seconds=10,
    script_timeout_seconds=30,
    max_statements=100,
    max_statement_bytes=262_144,
    max_result_rows=1_000,
    max_result_bytes=33_554_432,
    max_cell_bytes=4_194_304,
    max_run_results=20,
    max_run_bytes=67_108_864,
    max_messages=1_000,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "sales.csv").write_text(
        "id,amount,region\n1,10.5,north\n2,20.25,south\n3,5,north\n", encoding="utf-8"
    )
    (tmp_path / "tabs.tsv").write_text("x\ty\n1\t2\n", encoding="utf-8")
    (tmp_path / "people.json").write_text(
        '[{"name":"ada","age":36}]', encoding="utf-8"
    )
    (tmp_path / "events.jsonl").write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")
    (tmp_path / "notes.txt").write_text("nothing tabular\n", encoding="utf-8")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q1.csv").write_text(
        "region,target\nnorth,10\nsouth,30\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def outside(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A file the connector's root has no business reaching."""
    folder = tmp_path_factory.mktemp("elsewhere")
    secret = folder / "secret.csv"
    secret.write_text("a\n1\n", encoding="utf-8")
    return secret


@pytest.fixture
def query(root: Path) -> ExplorerQuery:
    return ExplorerQuery(LocalStorage(root))


def _request(text: str, **kwargs: object) -> QueryRequest:
    return QueryRequest(text=text, mode="read", limits=LIMITS, **kwargs)  # type: ignore[arg-type]


async def _events(query: ExplorerQuery, text: str, **kwargs: object) -> list[QueryEvent]:
    return [event async for event in query.open(_request(text, **kwargs)).events()]


async def _finished(query: ExplorerQuery, text: str, **kwargs: object) -> StatementFinished:
    events = await _events(query, text, **kwargs)
    finished = [event for event in events if isinstance(event, StatementFinished)]
    assert len(finished) == 1
    return finished[0]


def _result(finished: StatementFinished) -> MaterialisedResult:
    assert finished.status == "succeeded", finished.diagnostic
    assert finished.result is not None
    return finished.result


# --- what the source says it is ---------------------------------------------


def test_the_profile_offers_reading_and_nothing_else(query: ExplorerQuery) -> None:
    profile = query.profile()

    assert profile.dialect == "duckdb"
    assert profile.statement_modes == ["read"]
    assert profile.parameter_syntax == "named_dollar"
    assert profile.supports_cancel is True


# --- reading -----------------------------------------------------------------


async def test_a_delimited_file_is_read_as_a_relation(query: ExplorerQuery) -> None:
    result = _result(await _finished(query, 'SELECT * FROM "sales.csv" ORDER BY id'))

    assert [column.name for column in result.columns] == ["id", "amount", "region"]
    assert result.rows[0] == ["1", "10.5", "north"]
    assert result.truncated is False


async def test_the_engine_types_the_columns_of_a_delimited_file(
    query: ExplorerQuery,
) -> None:
    """The grid says every column is text (D51); SQL has to add them up."""
    result = _result(await _finished(query, 'SELECT * FROM "sales.csv"'))

    categories = {column.name: column.type.category for column in result.columns}
    assert categories == {"id": "number", "amount": "number", "region": "string"}


async def test_two_files_are_joined_across_a_folder(query: ExplorerQuery) -> None:
    result = _result(
        await _finished(
            query,
            'SELECT s.region, sum(s.amount) AS total, max(q.target) AS target'
            ' FROM "sales.csv" s JOIN "reports/q1.csv" q USING (region)'
            " GROUP BY s.region ORDER BY s.region",
        )
    )

    assert result.rows == [["north", "15.5", "10"], ["south", "20.25", "30"]]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("tabs.tsv", ["1", "2"]),
        ("people.json", ["ada", "36"]),
        ("events.jsonl", ["1"]),
    ],
)
async def test_every_readable_format_is_read(
    query: ExplorerQuery, name: str, expected: list[str]
) -> None:
    result = _result(await _finished(query, f"SELECT * FROM {quoted(name)}"))

    assert result.rows[0] == expected


async def test_a_parameter_is_bound(query: ExplorerQuery) -> None:
    result = _result(
        await _finished(
            query,
            'SELECT id FROM "sales.csv" WHERE amount > $cutoff ORDER BY id',
            parameters=[ParameterValue(name="cutoff", value="6")],
        )
    )

    assert result.rows == [["1"], ["2"]]


async def test_a_parameter_is_a_binding_and_not_text(query: ExplorerQuery) -> None:
    """The classic: the value cannot end the string it stands in."""
    result = _result(
        await _finished(
            query,
            'SELECT count(*) AS n FROM "sales.csv" WHERE region = $region',
            parameters=[
                ParameterValue(name="region", value="north' OR '1'='1")
            ],
        )
    )

    assert result.rows == [["0"]]


async def test_a_script_runs_in_order_and_stops_at_the_first_failure(
    query: ExplorerQuery,
) -> None:
    events = await _events(query, 'SELECT 1; SELECT nosuch FROM "sales.csv"; SELECT 3')

    finished = [event for event in events if isinstance(event, StatementFinished)]
    assert [event.status for event in finished] == ["succeeded", "failed", "not_run"]


# --- the one containment rule ------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["../secret.csv", "/etc/passwd", "C:/Windows/win.ini", "reports/../../secret.csv"],
)
async def test_a_name_that_leaves_the_root_is_refused(
    query: ExplorerQuery, name: str
) -> None:
    with pytest.raises(AdapterError) as refusal:
        await _events(query, f"SELECT * FROM {quoted(name)}")

    assert "no file called" in refusal.value.message


async def test_a_name_that_is_not_there_is_refused_before_anything_opens(
    query: ExplorerQuery,
) -> None:
    with pytest.raises(AdapterError) as refusal:
        await _events(query, 'SELECT * FROM "sales.csv" JOIN "nope.csv" ON true')

    assert refusal.value.message == (
        "There is no file called nope.csv in this connection"
    )


async def test_a_file_with_no_tabular_reader_is_refused(query: ExplorerQuery) -> None:
    with pytest.raises(AdapterError) as refusal:
        await _events(query, 'SELECT * FROM "notes.txt"')

    assert "CSV, TSV, Parquet, JSON, JSON lines and logs" in refusal.value.message


async def test_a_workbook_is_refused_with_its_own_reason(
    root: Path, query: ExplorerQuery
) -> None:
    (root / "book.xlsx").write_bytes(b"PK\x03\x04not really")

    with pytest.raises(AdapterError) as refusal:
        await _events(query, 'SELECT * FROM "book.xlsx"')

    assert "worksheet is not offered to SQL" in refusal.value.message


@pytest.mark.skipif(os.name != "posix", reason="Windows needs a privilege to link")
async def test_a_symbolic_link_out_of_the_root_is_refused(
    root: Path, outside: Path, query: ExplorerQuery
) -> None:
    (root / "linked.csv").symlink_to(outside)

    with pytest.raises(AdapterError) as refusal:
        await _events(query, 'SELECT * FROM "linked.csv"')

    assert "no file called" in refusal.value.message


async def test_a_write_mode_is_refused(query: ExplorerQuery) -> None:
    request = QueryRequest(text="SELECT 1", mode="auto_commit", limits=LIMITS)

    with pytest.raises(AdapterError) as refusal:
        [event async for event in query.open(request).events()]

    assert "runs nothing that writes" in refusal.value.message


async def test_a_schema_context_is_refused(query: ExplorerQuery) -> None:
    with pytest.raises(AdapterError) as refusal:
        await _events(query, "SELECT 1", search_path=["public"])

    assert "no schemas" in refusal.value.message


async def test_the_adapter_says_its_refusal_again_when_asked_directly(
    query: ExplorerQuery,
) -> None:
    """The route refuses these at admission; the source does not rely on it."""
    finished = await _finished(query, 'DELETE FROM "sales.csv"')

    assert finished.status == "failed"
    assert finished.diagnostic is not None
    assert finished.diagnostic.category == "read_only"
    assert "does not change them through SQL" in finished.diagnostic.message


# --- the sandbox behind the refusals -----------------------------------------


def _opened(root: Path, relations: dict[str, Path]) -> _Engine:
    engine = _Engine(LocalStorage(root).local_root())
    engine.open(relations)
    return engine


def test_the_engine_reads_the_files_it_was_given(root: Path) -> None:
    engine = _opened(root, {"sales.csv": root / "sales.csv"})
    try:
        assert engine.connection.execute(
            'SELECT count(*) FROM "sales.csv"'
        ).fetchall() == [(3,)]
    finally:
        engine.close()


def test_the_engine_cannot_read_a_file_outside_the_root(
    root: Path, outside: Path
) -> None:
    """Defence in depth: the parse already refuses a table function (D77)."""
    engine = _opened(root, {})
    try:
        with pytest.raises(duckdb.Error):
            engine.connection.execute(
                "SELECT * FROM read_csv(?)", [str(outside)]
            ).fetchall()
    finally:
        engine.close()


@pytest.mark.parametrize(
    "statement",
    [
        "SET enable_external_access=true",
        "SET allowed_directories=['/']",
        "RESET allowed_directories",
        "SET lock_configuration=false",
        "LOAD httpfs",
        "INSTALL httpfs",
    ],
)
def test_the_engine_will_not_let_its_own_door_be_reopened(
    root: Path, statement: str
) -> None:
    engine = _opened(root, {})
    try:
        with pytest.raises(duckdb.Error):
            engine.connection.execute(statement)
    finally:
        engine.close()


def test_the_engine_is_thrown_away_with_everything_in_it(root: Path) -> None:
    first = _opened(root, {"sales.csv": root / "sales.csv"})
    first.connection.execute("CREATE TABLE kept AS SELECT 1 AS a")
    first.close()

    second = _opened(root, {})
    try:
        with pytest.raises(duckdb.Error):
            second.connection.execute("SELECT * FROM kept").fetchall()
    finally:
        second.close()


# --- what a failure says -----------------------------------------------------


async def test_an_unknown_column_points_at_the_place_it_is_written(
    query: ExplorerQuery,
) -> None:
    finished = await _finished(query, 'SELECT nosuch FROM "sales.csv"')

    assert finished.status == "failed"
    assert finished.diagnostic is not None
    assert finished.diagnostic.category == "missing_object"
    assert finished.diagnostic.position == len("SELECT ")
    assert "nosuch" in finished.diagnostic.message


async def test_a_message_never_names_where_the_server_keeps_its_files(
    root: Path, outside: Path
) -> None:
    """The regression test for D78: an error is about the query, not the disk.

    The sandbox's own refusal quotes the path back, and that is exactly the
    sentence that must not cross. What crosses instead is the standard one for
    the category.
    """
    engine = _opened(root, {})
    try:
        with pytest.raises(duckdb.Error) as failure:
            engine.connection.execute(
                "SELECT * FROM read_csv(?)", [str(outside)]
            ).fetchall()
    finally:
        engine.close()

    # The engine's own words name the path, which is the point of the test.
    assert outside.name in str(failure.value)
    diagnostic = diagnostic_of(
        failure.value, root=root, cancelled=False, timed_out=False
    )
    assert diagnostic.message == _FALLBACKS["permission"]
    assert str(outside) not in diagnostic.message
    assert outside.parent.name not in diagnostic.message


def test_the_root_is_taken_out_of_a_message_that_carries_it(root: Path) -> None:
    """Both spellings of it: Windows writes one and the engine writes the other."""
    for form in (str(root), root.as_posix()):
        assert _safe_text(f'no file matched "{form}/sales.csv"', root, "fallback") == (
            'no file matched "…/sales.csv"'
        )


# --- ceilings ----------------------------------------------------------------


async def test_a_result_is_truncated_at_the_ceiling_by_one_extra_row(
    query: ExplorerQuery,
) -> None:
    limits = LIMITS.model_copy(update={"max_result_rows": 2})
    request = QueryRequest(
        text='SELECT * FROM "sales.csv" ORDER BY id', mode="read", limits=limits
    )

    events = [event async for event in query.open(request).events()]
    finished = [event for event in events if isinstance(event, StatementFinished)][0]

    result = _result(finished)
    assert len(result.rows) == 2
    assert result.truncated is True


async def test_a_cell_larger_than_one_cell_may_be_is_a_publication_failure(
    query: ExplorerQuery,
) -> None:
    limits = LIMITS.model_copy(update={"max_cell_bytes": 4})
    request = QueryRequest(
        text="SELECT repeat('x', 100) AS wide", mode="read", limits=limits
    )

    events = [event async for event in query.open(request).events()]
    finished = [event for event in events if isinstance(event, StatementFinished)][0]

    # The statement ran; publishing what it produced is what failed (D64).
    assert finished.status == "succeeded"
    assert finished.result is None
    assert finished.diagnostic is not None
    assert finished.diagnostic.code == "result_too_large"


# --- stopping ----------------------------------------------------------------


# A statement with no end in sight, written without a table function so the
# parse admits it: counting twenty million rows of a recursive CTE takes well
# over half a minute, and every test below stops it long before that.
ENDLESS = (
    "WITH RECURSIVE r(n) AS ("
    "  SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 20000000"
    ") SELECT count(*) FROM r"
)


async def test_a_statement_that_runs_too_long_is_timed_out(query: ExplorerQuery) -> None:
    limits = LIMITS.model_copy(update={"statement_timeout_seconds": 1})
    request = QueryRequest(text=ENDLESS, mode="read", limits=limits)
    began = time.monotonic()

    events = [event async for event in query.open(request).events()]

    finished = [event for event in events if isinstance(event, StatementFinished)][0]
    assert finished.status == "timed_out"
    assert finished.diagnostic is not None
    assert finished.diagnostic.category == "timeout"
    assert time.monotonic() - began < 20


async def test_cancelling_stops_a_statement_that_is_running(
    query: ExplorerQuery,
) -> None:
    """The interrupt reaches the thread; a cancelled task never would."""
    execution: ExplorerExecution = query.open(_request(ENDLESS))
    finished: list[StatementFinished] = []

    async def read() -> None:
        async for event in execution.events():
            if isinstance(event, StatementFinished):
                finished.append(event)

    began = time.monotonic()
    async with anyio.create_task_group() as group:
        group.start_soon(read)
        await anyio.sleep(0.5)
        await execution.cancel()

    assert [event.status for event in finished] == ["cancelled"]
    assert time.monotonic() - began < 20


async def test_cancelling_a_run_that_has_not_opened_yet_is_harmless(
    query: ExplorerQuery,
) -> None:
    execution: ExplorerExecution = query.open(_request("SELECT 1"))

    await execution.cancel()

    events = [event async for event in execution.events()]
    finished = [event for event in events if isinstance(event, StatementFinished)][0]
    assert finished.status == "cancelled"


# --- what the editor is told -------------------------------------------------


async def test_the_relations_offered_are_the_files_sql_can_read(
    query: ExplorerQuery,
) -> None:
    metadata = await query.metadata(QueryMetadataRequest())

    names = {relation.name for relation in metadata.relations}
    assert names == {
        "sales.csv",
        "tabs.tsv",
        "people.json",
        "events.jsonl",
        "reports/q1.csv",
    }
    assert metadata.schemas == []
    assert metadata.complete is True


async def test_the_columns_of_a_named_relation_are_the_engine_s(
    query: ExplorerQuery,
) -> None:
    metadata = await query.metadata(
        QueryMetadataRequest(relations=["sales.csv", "notes.txt"])
    )

    assert [(column.name, column.type_sql) for column in metadata.columns["sales.csv"]] == [
        ("id", "BIGINT"),
        ("amount", "DOUBLE"),
        ("region", "VARCHAR"),
    ]
    assert "notes.txt" not in metadata.columns


async def test_the_source_writes_the_statement_for_one_of_its_nodes(
    query: ExplorerQuery,
) -> None:
    generated = await query.generate(GenerateQueryRequest(node_id="reports/q1.csv"))

    assert generated.text == 'SELECT *\nFROM "reports/q1.csv"\nLIMIT 100'


async def test_a_name_with_a_quote_in_it_is_quoted(query: ExplorerQuery) -> None:
    generated = await query.generate(
        GenerateQueryRequest(node_id='we"ird.csv', kind="name")
    )

    assert generated.text == '"we""ird.csv"'


async def test_the_columns_of_a_node_are_written_as_a_list(query: ExplorerQuery) -> None:
    generated = await query.generate(
        GenerateQueryRequest(node_id="sales.csv", kind="columns")
    )

    assert generated.text == '"id", "amount", "region"'


# --- explain -----------------------------------------------------------------


async def test_a_statement_is_planned_without_being_run(query: ExplorerQuery) -> None:
    plan = await query.explain(
        ExplainRequest(text='SELECT region, count(*) FROM "sales.csv" GROUP BY region')
    )

    assert plan.plan.kind != ""
    assert plan.raw != ""
    assert _walked(plan.plan) > 1


def _walked(node: object) -> int:
    children = getattr(node, "children", [])
    return 1 + sum(_walked(child) for child in children)


async def test_explain_refuses_what_run_refuses(query: ExplorerQuery) -> None:
    with pytest.raises(ValueError, match="table function"):
        await query.explain(ExplainRequest(text="SELECT * FROM read_csv('x.csv')"))


# --- logs use the grid's projection, over the whole bounded input (D96) ------


@pytest.mark.parametrize(
    "text",
    [
        "2026-09-04 12:00:00.123 UTC [42] ERROR:  failed\n"
        "  at handler()\n2026-09-04 12:00:01.123 UTC [42] LOG:  recovered\n",
        "arbitrary text\n\nlast line\n",
        '{"id":10000000000000001,"level":"INFO","extra":{"n":1.234567890123456789}}\n'
        '{"id":2,"level":null,"flag":true}\n',
    ],
)
async def test_sql_log_columns_and_values_match_the_grid(
    root: Path, query: ExplorerQuery, text: str,
) -> None:
    path = root / "server.log"
    path.write_text(text, encoding="utf-8")
    expected = LogReader().read(path, 100, 0)

    result = _result(await _finished(query, 'SELECT * FROM "server.log"'))

    assert [column.name for column in result.columns] == [column.name for column in expected.columns]
    assert all(column.type.sql == "VARCHAR" for column in result.columns)
    assert result.rows == expected.rows
    assert result.truncated is False


async def test_log_aggregates_read_beyond_the_grid_page_and_join_other_files(
    root: Path, query: ExplorerQuery,
) -> None:
    (root / "server.log").write_text(
        "2026-09-04 12:00:00 INFO north\n" * 125
        + "2026-09-04 12:00:01 ERROR south\n" * 26,
        encoding="utf-8",
    )
    result = _result(await _finished(
        query,
        'SELECT l.level, count(*) AS n, max(q.target) AS target FROM "server.log" l '
        'JOIN "reports/q1.csv" q ON l.message = q.region GROUP BY l.level ORDER BY l.level',
    ))

    assert result.rows == [["ERROR", "26", "30"], ["INFO", "125", "10"]]


async def test_every_statement_reads_the_same_log_snapshot(root: Path, query: ExplorerQuery) -> None:
    path = root / "server.log"
    path.write_text("first\n", encoding="utf-8")
    execution = query.open(_request(
        'SELECT count(*) FROM "server.log"; SELECT count(*) FROM "server.log"'
    ))
    results: list[MaterialisedResult] = []
    async for event in execution.events():
        if isinstance(event, StatementFinished):
            results.append(_result(event))
            path.write_text("first\nsecond\n", encoding="utf-8")

    assert [result.rows for result in results] == [[["1"]], [["1"]]]
    assert _result(await _finished(query, 'SELECT count(*) FROM "server.log"')).rows == [["2"]]


async def test_an_empty_log_has_a_schema_and_no_rows(root: Path, query: ExplorerQuery) -> None:
    (root / "server.log").write_bytes(b"")
    result = _result(await _finished(query, 'SELECT count(line_no) FROM "server.log"'))
    assert result.rows == [["0"]]


async def test_log_metadata_generated_sql_and_explain_use_the_same_columns(
    root: Path, query: ExplorerQuery,
) -> None:
    (root / "server.log").write_text("2026-09-04 12:00:00 INFO ready\n", encoding="utf-8")
    metadata = await query.metadata(QueryMetadataRequest(relations=["server.log"]))
    assert "server.log" in {relation.name for relation in metadata.relations}
    assert [(column.name, column.type_sql) for column in metadata.columns["server.log"]] == [
        ("time", "VARCHAR"), ("level", "VARCHAR"), ("message", "VARCHAR"),
    ]
    generated = await query.generate(GenerateQueryRequest(node_id="server.log"))
    assert generated.text == 'SELECT *\nFROM "server.log"\nLIMIT 100'
    assert _result(await _finished(query, generated.text)).rows[0][-1] == "ready"
    plan = await query.explain(ExplainRequest(text=generated.text))
    assert "ARROW_SCAN" in plan.raw


@pytest.mark.parametrize(
    ("ceiling", "value", "reason"),
    [
        ("MAX_LOG_BYTES", 4, "byte limit"),
        ("MAX_LOG_ROWS", 2, "row limit"),
        ("MAX_LOG_CELLS", 5, "cell limit"),
        ("MAX_LOG_CELL_BYTES", 2, "cell size limit"),
    ],
)
async def test_log_input_limits_refuse_aggregates_instead_of_truncating(
    root: Path, query: ExplorerQuery, monkeypatch: pytest.MonkeyPatch,
    ceiling: str, value: int, reason: str,
) -> None:
    (root / "server.log").write_text("one\ntwo\nthree\n", encoding="utf-8")
    monkeypatch.setattr(query_readers, ceiling, value)
    execution = query.open(_request('SELECT count(*) FROM "server.log"'))
    with pytest.raises(AdapterError, match=reason):
        _ = [event async for event in execution.events()]
    with pytest.raises(AdapterError, match="not open"):
        _ = execution._engine.connection


@pytest.mark.parametrize(
    ("ceiling", "value"),
    [("MAX_LOG_BYTES", 12), ("MAX_LOG_ROWS", 3), ("MAX_LOG_CELLS", 6)],
)
async def test_log_input_budget_is_shared_by_all_logs_in_a_run(
    root: Path, query: ExplorerQuery, monkeypatch: pytest.MonkeyPatch, ceiling: str, value: int,
) -> None:
    for name in ("a.log", "b.log"):
        (root / name).write_bytes(b"one\ntwo\n")
    monkeypatch.setattr(query_readers, ceiling, value)
    assert _result(await _finished(query, 'SELECT count(*) FROM "a.log"')).rows == [["2"]]
    with pytest.raises(AdapterError, match="SQL input"):
        await _events(query, 'SELECT count(*) FROM "a.log" JOIN "b.log" ON true')


async def test_sparse_json_log_cells_are_bounded_before_the_table_is_built(
    root: Path, query: ExplorerQuery, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (root / "server.log").write_text('{"a":1}\n{"b":2}\n{"c":3}\n', encoding="utf-8")
    monkeypatch.setattr(query_readers, "MAX_LOG_CELLS", 8)
    with pytest.raises(AdapterError, match="cell limit"):
        await _events(query, 'SELECT count(*) FROM "server.log"')


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ('{"a":1}\n{"a":2}\nbroken\n', "Line 3 is not valid JSON"),
        ('{"a":"\\ud800"}\n', "cannot be represented in UTF-8"),
        ('{}\n', "no columns"),
    ],
)
async def test_unreadable_json_logs_have_a_safe_refusal(
    root: Path, query: ExplorerQuery, text: str, reason: str,
) -> None:
    (root / "server.log").write_text(text, encoding="utf-8")
    with pytest.raises(AdapterError, match=reason) as failure:
        await _events(query, 'SELECT * FROM "server.log"')
    assert str(root) not in failure.value.message


async def test_json_log_projection_keeps_the_grid_source_size_limit(
    root: Path, query: ExplorerQuery, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (root / "server.log").write_bytes(b'{"a":1}\n{"a":2}\n')
    monkeypatch.setattr(records, "MAX_RECORD_BYTES", 12)
    with pytest.raises(AdapterError, match="cannot be projected as one table"):
        await _events(query, 'SELECT count(*) FROM "server.log"')


async def test_binary_bytes_cannot_be_read_by_renaming_a_file_to_log(
    root: Path, query: ExplorerQuery,
) -> None:
    (root / "server.log").write_bytes(b"binary\x00content")
    with pytest.raises(AdapterError, match="binary data"):
        await _events(query, 'SELECT * FROM "server.log"')


async def test_explain_obeys_log_input_limits_and_metadata_omits_unreadable_columns(
    root: Path, query: ExplorerQuery, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (root / "server.log").write_bytes(b"one\ntwo\n")
    monkeypatch.setattr(query_readers, "MAX_LOG_ROWS", 1)
    metadata = await query.metadata(QueryMetadataRequest(relations=["server.log"]))
    assert "server.log" not in metadata.columns
    with pytest.raises(AdapterError, match="row limit"):
        await query.explain(ExplainRequest(text='SELECT count(*) FROM "server.log"'))


async def test_a_run_can_be_cancelled_while_loading_a_log(
    root: Path, query: ExplorerQuery, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (root / "server.log").write_bytes(b"one\n")
    entered = Event()
    resume = Event()
    snapshot = FileReaders._snapshot

    def waiting_snapshot(readers: FileReaders, path: Path) -> bytes:
        entered.set()
        assert resume.wait(5)
        return snapshot(readers, path)

    monkeypatch.setattr(FileReaders, "_snapshot", waiting_snapshot)
    execution = query.open(_request('SELECT count(*) FROM "server.log"; SELECT 1'))
    finished: list[StatementFinished] = []

    async def read() -> None:
        async for event in execution.events():
            if isinstance(event, StatementFinished):
                finished.append(event)

    async with anyio.create_task_group() as group:
        group.start_soon(read)
        try:
            assert await anyio.to_thread.run_sync(entered.wait, 5)
            await execution.cancel()
        finally:
            resume.set()
    assert [event.status for event in finished] == ["cancelled", "not_run"]
    with pytest.raises(AdapterError, match="not open"):
        _ = execution._engine.connection


async def test_preparation_timeout_settles_the_run_and_closes_the_engine(
    root: Path, query: ExplorerQuery, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (root / "server.log").write_bytes(b"one\n")
    snapshot = FileReaders._snapshot

    def expired_snapshot(readers: FileReaders, path: Path) -> bytes:
        readers._checkpoint = Preparation(time.monotonic() - 1).check
        return snapshot(readers, path)

    monkeypatch.setattr(FileReaders, "_snapshot", expired_snapshot)
    execution = query.open(_request('SELECT count(*) FROM "server.log"; SELECT 1'))
    events = [event async for event in execution.events()]
    assert [event.status for event in events if isinstance(event, StatementFinished)] == [
        "timed_out", "not_run",
    ]
    with pytest.raises(AdapterError, match="not open"):
        _ = execution._engine.connection
