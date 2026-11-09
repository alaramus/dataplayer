"""CQL in the query console and cqlsh in a terminal (D343, D344)."""

from collections.abc import AsyncIterator

import pytest
from pydantic import SecretStr

from app.adapters.cassandra.adapter import CassandraAdapter
from app.adapters.cassandra.console import CREDENTIALS_VARIABLE, credentials
from app.adapters.cassandra.options import CassandraNoPassword, CassandraUserPassword
from app.adapters.cassandra.statements import object_of, prepare
from app.adapters.protocol import AdapterError
from app.adapters.query import (
    GenerateQueryRequest,
    ParameterValue,
    QueryEvent,
    QueryLimits,
    QueryMetadataRequest,
    QueryRequest,
    StatementFinished,
    SupportsGeneratedQuery,
    SupportsQuery,
    SupportsQueryMetadata,
)
from app.adapters.terminal import SupportsConsoleProgram
from tests.adapters.cassandra_fixture import KEYSPACE, TARGETS, Target, build, tear_down

LIMITS = QueryLimits(
    statement_timeout_seconds=30,
    script_timeout_seconds=60,
    max_statements=50,
    max_statement_bytes=100_000,
    max_result_rows=1000,
    max_result_bytes=10_000_000,
    max_cell_bytes=1_000_000,
    max_run_results=20,
    max_run_bytes=20_000_000,
    max_messages=100,
)


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    yield chosen
    await tear_down(chosen)


async def _run(
    adapter: CassandraAdapter,
    text: str,
    *,
    mode: str = "auto_commit",
    keyspace: str | None = KEYSPACE,
    parameters: list[ParameterValue] | None = None,
    limits: QueryLimits = LIMITS,
) -> list[StatementFinished]:
    execution = adapter.open_query(
        QueryRequest.model_validate(
            {
                "text": text,
                "mode": mode,
                "search_path": [keyspace] if keyspace else [],
                "parameters": [parameter.model_dump() for parameter in parameters or []],
                "limits": limits.model_dump(),
            }
        )
    )
    events: list[QueryEvent] = [event async for event in execution.events()]
    return [event for event in events if isinstance(event, StatementFinished)]


def _adapter() -> CassandraAdapter:
    return CassandraAdapter(
        CassandraUserPassword(host="127.0.0.1", port=1, user="u", password=SecretStr("p"))
    )


# --- What the console is told -----------------------------------------------


def test_it_offers_a_console_and_a_terminal() -> None:
    adapter = _adapter()

    assert isinstance(adapter, SupportsQuery)
    assert isinstance(adapter, SupportsQueryMetadata)
    assert isinstance(adapter, SupportsGeneratedQuery)
    assert isinstance(adapter, SupportsConsoleProgram)
    profile = adapter.query_profile()
    assert profile.dialect == "cql"
    assert profile.parameter_syntax == "named_colon"
    assert profile.statement_modes == ["read", "auto_commit"]


def test_a_semicolon_inside_a_string_a_name_a_body_or_a_comment_ends_nothing() -> None:
    script = prepare(
        "SELECT 'a;b' FROM t; -- c;d\n"
        'SELECT "x;y" FROM t /* ; */;\n'
        "CREATE FUNCTION f (a int) RETURNS NULL ON NULL INPUT RETURNS int "
        "LANGUAGE java AS $$ return a; $$;"
    )

    assert [statement.text for statement in script.statements] == [
        "SELECT 'a;b' FROM t",
        'SELECT "x;y" FROM t',
        "CREATE FUNCTION f (a int) RETURNS NULL ON NULL INPUT RETURNS int "
        "LANGUAGE java AS $$ return a; $$",
    ]


def test_a_batch_is_one_statement() -> None:
    script = prepare(
        "BEGIN BATCH INSERT INTO t (a) VALUES (1); UPDATE t SET b = 2 WHERE a = 1; APPLY BATCH;"
        " SELECT * FROM t"
    )

    assert [statement.kind for statement in script.statements] == ["dml", "read"]
    assert script.statements[0].text.endswith("APPLY BATCH")


def test_statements_are_classed_by_their_first_words() -> None:
    kinds = [
        (statement.kind, statement.destructive, statement.refused is not None)
        for statement in prepare(
            "SELECT * FROM t; DESCRIBE TABLES; LIST ROLES; INSERT INTO t (a) VALUES (1);"
            " TRUNCATE t; DROP TABLE t; CREATE TABLE u (a int PRIMARY KEY); USE ks;"
            " CONSISTENCY QUORUM; COPY t TO 'x.csv'; FROBNICATE"
        ).statements
    ]

    assert kinds == [
        ("read", False, False),
        ("read", False, False),
        ("read", False, False),
        ("dml", False, False),
        ("ddl", True, False),
        ("ddl", True, False),
        ("ddl", False, False),
        ("session", False, False),
        ("unknown", False, True),
        ("unknown", False, True),
        ("unknown", False, True),
    ]


def test_named_markers_are_the_parameters() -> None:
    script = prepare('SELECT * FROM t WHERE a = :Id AND b = :"Mixed" AND c = :id')

    assert script.parameters == ["id", "Mixed"]


def test_a_structure_change_names_what_it_changes() -> None:
    assert object_of("CREATE TABLE IF NOT EXISTS shop.items (a int PRIMARY KEY)") == (
        "CREATE",
        "TABLE",
        "shop",
        "items",
    )
    assert object_of('ALTER TABLE "Odd" ADD b int') == ("ALTER", "TABLE", None, "Odd")
    assert object_of("CREATE INDEX i ON shop.items (b)") == ("CREATE", "INDEX", "shop", "items")
    assert object_of("TRUNCATE shop.items") == ("TRUNCATE", "TABLE", "shop", "items")
    assert object_of("DROP KEYSPACE shop")[:2] == ("DROP", "KEYSPACE")


# --- cqlsh -------------------------------------------------------------------


async def test_cqlsh_is_signed_in_without_an_argument() -> None:
    options = CassandraUserPassword(
        host="db", port=9043, user="ann%x", password=SecretStr("p$1 'q"), keyspace="shop"
    )

    program = await CassandraAdapter(options).console_program()

    assert program.image == "cassandra:5.0"
    assert all("p$1" not in argument for argument in program.argv)
    assert program.environment["CQLSH_HOST"] == "db"
    assert program.environment["CQLSH_PORT"] == "9043"
    assert program.environment[CREDENTIALS_VARIABLE] == (
        "[plain_text_auth]\nusername = ann%%x\npassword = p$1 'q\n"
    )
    assert "unset DP_CREDENTIALS" in program.argv[-1]
    assert "p$1" not in repr(program)


async def test_cqlsh_without_a_password_writes_no_credentials() -> None:
    program = await CassandraAdapter(CassandraNoPassword(host="db")).console_program()

    assert CREDENTIALS_VARIABLE not in program.environment
    assert "--credentials" not in program.argv[-1]


def test_a_line_break_cannot_reach_the_credentials_file() -> None:
    with pytest.raises(AdapterError):
        credentials(
            CassandraUserPassword(host="db", user="ann", password=SecretStr("a\n[x]"))
        )


# --- Running -------------------------------------------------------------------


async def test_a_select_comes_back_as_a_result(target: Target) -> None:
    [finished] = await _run(target.adapter(), "SELECT p, word FROM many WHERE p IN (1, 2)")

    assert finished.status == "succeeded"
    assert finished.result is not None
    assert [column.name for column in finished.result.columns] == ["p", "word"]
    assert sorted(finished.result.rows) == [["1", "w1"], ["2", "w2"]]
    assert finished.result.columns[0].type.category == "number"


async def test_a_result_past_the_ceiling_is_truncated(target: Target) -> None:
    [finished] = await _run(
        target.adapter(), "SELECT p FROM many", limits=LIMITS.model_copy(update={"max_result_rows": 7})
    )

    assert finished.result is not None
    assert len(finished.result.rows) == 7
    assert finished.result.truncated


async def test_several_reads_run_together(target: Target) -> None:
    finished = await _run(
        target.adapter(), "SELECT p FROM many WHERE p = 1; SELECT p FROM many WHERE p = 2"
    )

    assert [event.status for event in finished] == ["succeeded", "succeeded"]


async def test_a_read_refuses_a_change(target: Target) -> None:
    [finished] = await _run(
        target.adapter(), "INSERT INTO many (p, v) VALUES (9999, 1)", mode="read"
    )

    assert finished.status == "failed"
    assert finished.diagnostic is not None and finished.diagnostic.category == "read_only"


async def test_a_change_runs_alone(target: Target) -> None:
    finished = await _run(
        target.adapter(),
        "SELECT p FROM many WHERE p = 1; INSERT INTO many (p, v) VALUES (9999, 1)",
    )

    assert [event.status for event in finished] == ["succeeded", "failed"]
    assert finished[1].diagnostic is not None
    assert "BATCH" in finished[1].diagnostic.message


async def test_a_batch_of_changes_runs(target: Target) -> None:
    adapter = target.adapter()

    [finished] = await _run(
        adapter,
        "BEGIN BATCH INSERT INTO many (p, v, word) VALUES (5001, 1, 'b1');"
        " INSERT INTO many (p, v, word) VALUES (5002, 2, 'b2'); APPLY BATCH",
    )
    [read] = await _run(adapter, "SELECT word FROM many WHERE p IN (5001, 5002)")

    assert finished.status == "succeeded"
    assert read.result is not None
    assert sorted(read.result.rows) == [["b1"], ["b2"]]
    await _run(adapter, "DELETE FROM many WHERE p IN (5001, 5002)")


async def test_parameters_are_bound_by_their_columns_type(target: Target) -> None:
    [finished] = await _run(
        target.adapter(),
        "SELECT word FROM many WHERE p = :p",
        parameters=[ParameterValue(name="p", value="42")],
    )

    assert finished.result is not None
    assert finished.result.rows == [["w42"]]


async def test_a_parameter_the_column_cannot_hold_is_said(target: Target) -> None:
    [finished] = await _run(
        target.adapter(),
        "SELECT word FROM many WHERE p = :p",
        parameters=[ParameterValue(name="p", value="forty")],
    )

    assert finished.status == "failed"
    assert finished.diagnostic is not None
    assert ":p is not a value of type int" in finished.diagnostic.message


async def test_a_collection_parameter_is_json(target: Target) -> None:
    adapter = target.adapter()

    [written] = await _run(
        adapter,
        "UPDATE items SET tags = :tags WHERE shop = 'south' AND id = 3 AND at = '2024-01-01T00:00:00Z'",
        parameters=[ParameterValue(name="tags", value='["x", "y"]')],
    )
    [read] = await _run(adapter, "SELECT tags FROM items WHERE shop = 'south'")

    assert written.status == "succeeded", written.diagnostic
    assert read.result is not None and read.result.rows == [['["x","y"]']]


async def test_the_servers_refusal_is_its_own_sentence(target: Target) -> None:
    [finished] = await _run(target.adapter(), "SELECT * FROM no_such_table")

    assert finished.status == "failed"
    assert finished.diagnostic is not None
    assert finished.diagnostic.category == "missing_object"
    assert "no_such_table" in finished.diagnostic.message


async def test_a_syntax_error_is_one(target: Target) -> None:
    [finished] = await _run(target.adapter(), "SELECT FROM WHERE")

    assert finished.diagnostic is not None and finished.diagnostic.category == "syntax"


async def test_a_cqlsh_command_is_refused_with_the_reason(target: Target) -> None:
    [finished] = await _run(target.adapter(), "TRACING ON")

    assert finished.status == "failed"
    assert finished.diagnostic is not None and "cqlsh" in finished.diagnostic.message


async def test_use_changes_the_keyspace_of_the_run_only(target: Target) -> None:
    adapter = target.adapter()

    finished = await _run(adapter, "USE system; SELECT key FROM local", keyspace=KEYSPACE)
    [later] = await _run(adapter, "SELECT p FROM many WHERE p = 1", keyspace=KEYSPACE)

    assert [event.status for event in finished] == ["succeeded", "succeeded"]
    assert later.status == "succeeded"


async def test_a_missing_keyspace_is_said(target: Target) -> None:
    with pytest.raises(AdapterError):
        await _run(target.adapter(), "SELECT * FROM t", keyspace="no_such_keyspace")


async def test_a_new_table_reloads_its_keyspace(target: Target) -> None:
    adapter = target.adapter()

    [made] = await _run(adapter, "CREATE TABLE made_here (a int PRIMARY KEY)")
    [altered] = await _run(adapter, "ALTER TABLE made_here ADD b text")
    [dropped] = await _run(adapter, "DROP TABLE made_here")

    assert made.effect is not None and made.effect.reload_node_ids == [KEYSPACE]
    assert altered.effect is not None
    assert altered.effect.relation_node_ids == [f"{KEYSPACE}.made_here"]
    assert dropped.effect is not None and dropped.effect.reload_node_ids == [KEYSPACE]


async def test_describe_runs_on_the_server(target: Target) -> None:
    [finished] = await _run(target.adapter(), "DESCRIBE TABLE many")

    assert finished.result is not None
    assert any("CREATE TABLE" in (cell or "") for row in finished.result.rows for cell in row)


# --- Completion ---------------------------------------------------------------


async def test_completion_knows_the_keyspaces_relations_and_columns(target: Target) -> None:
    metadata = await target.adapter().query_metadata(
        QueryMetadataRequest(search_path=[KEYSPACE], relations=[f"{KEYSPACE}.many"])
    )

    assert KEYSPACE in metadata.schemas
    assert {relation.name for relation in metadata.relations} >= {"items", "many"}
    assert [column.name for column in metadata.columns[f"{KEYSPACE}.many"]] == ["p", "v", "word"]


async def test_a_select_is_written_for_a_table(target: Target) -> None:
    generated = await target.adapter().generate_query(
        GenerateQueryRequest(node_id=f"{KEYSPACE}.OddName")
    )

    assert generated.text == f'SELECT "x y"\nFROM "{KEYSPACE}"."OddName"\nLIMIT 100'
