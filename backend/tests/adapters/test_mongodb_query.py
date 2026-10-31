"""The query console of a MongoDB source: shell syntax as driver calls (D296).

Reading the text needs no server; running it needs the test MongoDB.
"""

import asyncio
import math
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from bson import Decimal128, Int64, ObjectId, Regex

from app.adapters.content import JsonObject, JsonScalar
from app.adapters.database_ids import database_id, relation_id
from app.adapters.mongodb.adapter import MongodbAdapter
from app.adapters.mongodb.query import collection_text
from app.adapters.mongodb.shell import prepare, read_script
from app.adapters.query import (
    GenerateQueryRequest,
    QueryExecution,
    QueryLimits,
    QueryMetadataRequest,
    QueryRequest,
    StatementFinished,
    SupportsExplain,
    SupportsGeneratedQuery,
    SupportsQuery,
    SupportsQueryMetadata,
    SupportsRehearsal,
    SupportsTransactions,
)
from tests.adapters.mongodb_fixture import (
    DATABASE,
    PEOPLE_IDS,
    adapter,
    build,
    raw_client,
    tear_down,
)
from tests.utils.services import MONGODB

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


@pytest.fixture(scope="module")
async def server() -> AsyncIterator[None]:
    MONGODB.require()
    await build()
    yield
    await tear_down()


def _request(text: str, mode: str = "read", **extra: object) -> QueryRequest:
    return QueryRequest(text=text, mode=mode, limits=LIMITS, search_path=[DATABASE], **extra)  # type: ignore[arg-type]  # the mode is one of three literals


async def _finished(execution: QueryExecution) -> list[StatementFinished]:
    return [event async for event in execution.events() if isinstance(event, StatementFinished)]


async def _one(text: str, mode: str = "read") -> StatementFinished:
    [finished] = await _finished(adapter().open_query(_request(text, mode)))
    return finished


# --- What the source says it does -------------------------------------------


def test_it_claims_the_console_and_nothing_it_cannot_keep() -> None:
    source = MongodbAdapter.__new__(MongodbAdapter)
    for capability in (SupportsQuery, SupportsQueryMetadata, SupportsGeneratedQuery):
        assert isinstance(source, capability)
    # A change is kept as it ends; there is nothing to roll back (D296).
    assert not isinstance(source, SupportsTransactions)
    assert not isinstance(source, SupportsRehearsal)
    # A plan is `.explain()` in the text, answered as a document.
    assert not isinstance(source, SupportsExplain)


def test_the_profile_says_javascript_and_no_parameters() -> None:
    profile = adapter().query_profile()

    assert profile.dialect == "mongodb"
    assert profile.editor_language == "javascript"
    assert profile.parameter_syntax == "none"
    assert profile.statement_modes == ["read", "auto_commit"]


# --- Reading the text ---------------------------------------------------------


def test_statements_end_where_their_chain_does() -> None:
    text = (
        "db.orders.find({ a: ';' })\n"
        "  .sort({ at: -1 })\n"
        "db.orders.countDocuments(); db.orders.drop()\n"
        "// a comment\n"
        "use shop\n"
        "show collections"
    )
    statements = prepare(text).statements

    assert [statement.text for statement in statements] == [
        "db.orders.find({ a: ';' })\n  .sort({ at: -1 })",
        "db.orders.countDocuments()",
        "db.orders.drop()",
        "use shop",
        "show collections",
    ]
    assert [text[one.start : one.end] for one in statements] == [one.text for one in statements]


def test_values_are_read_the_shell_s_way() -> None:
    [read] = read_script(
        """db.c.insertOne({
          plain: 'single', "quoted key": 1, 2: true, nested: { list: [1, -2.5, ], },
          id: ObjectId("650000000000000000000001"), at: ISODate("2024-01-02T03:04:05Z"),
          epoch: new Date(0), long: NumberLong("9007199254740993"), int: NumberInt(7),
          dec: NumberDecimal("1.10"), uid: UUID("12345678-1234-5678-1234-567812345678"),
          re: /^a\\/b/i, none: null, gone: undefined, nan: NaN, far: -Infinity, hex: 0xff,
        })"""
    )
    assert read.operation is not None
    document = read.operation.args[0]

    assert document["plain"] == "single"
    assert document["quoted key"] == 1
    assert document["2"] is True
    assert document["nested"] == {"list": [1, -2.5]}
    assert document["id"] == ObjectId("650000000000000000000001")
    assert document["at"] == datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert document["epoch"] == datetime(1970, 1, 1, tzinfo=UTC)
    assert document["long"] == Int64(9007199254740993) and isinstance(document["long"], Int64)
    assert document["int"] == 7
    assert document["dec"] == Decimal128("1.10")
    assert document["uid"] == uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert document["re"] == Regex("^a\\/b", "i")
    assert document["none"] is None and document["gone"] is None
    assert math.isnan(document["nan"]) and document["far"] == -math.inf
    assert document["hex"] == 255


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("db.c.find()", "read"),
        ("db.c.find().explain('executionStats')", "read"),
        ("db.c.explain().aggregate([{ $out: 'x' }])", "read"),
        ("db.c.aggregate([{ $match: {} }])", "read"),
        ("db.c.aggregate([{ $merge: { into: 'x' } }])", "dml"),
        ("db.c.insertMany([{}])", "dml"),
        ("db.c.findOneAndDelete({})", "dml"),
        ("db.c.createIndex({ a: 1 })", "ddl"),
        ("db.createCollection('x')", "ddl"),
        ("db.runCommand({ dbStats: 1 })", "read"),
        ("db.runCommand('ping')", "read"),
        ("db.runCommand({ delete: 'c', deletes: [] })", "dml"),
        ("db.runCommand({ compact: 'c' })", "maintenance"),
        ("db.runCommand({ collMod: 'c' })", "ddl"),
        ("use shop", "read"),
        ("show dbs", "read"),
    ],
)
def test_a_statement_is_classed_by_what_it_calls(text: str, kind: str) -> None:
    [statement] = prepare(text).statements

    assert statement.kind == kind
    assert statement.refused is None


@pytest.mark.parametrize(
    ("text", "refusal"),
    [
        ("db.c.foo()", "foo is not a method this console runs"),
        ("db.c.count()", "count is the old shell's; this console reads countDocuments"),
        ("db.c.find({ a: 'open })", "A string is not closed (line 1, column 16)"),
        ("db.c.find({ a: x })", "x is not a value this console reads"),
        ("db.c.find() junk", "The statement should end here"),
        ("var x = 1", "A statement here starts with db, use or show"),
        ("db.c.find(1)", "Filter: a document is expected"),
        ("db.c.updateOne({})", "updateOne: 2 to 3 arguments are expected"),
        ("db.c.find({ a: `${x}` })", "A template string with substitutions is not read here"),
        ("db.runCommand({ createUser: 'x', pwd: 'y', roles: [] })", "Users and roles are not administered"),
        ("db.adminCommand({ shutdown: 1 })", "shutdown is not run from the query editor"),
    ],
)
def test_what_the_console_does_not_read_is_refused_in_words(text: str, refusal: str) -> None:
    [statement] = prepare(text).statements

    assert statement.kind == "unknown"
    assert statement.refused is not None and refusal in statement.refused


def test_one_mistake_does_not_hide_the_statements_after_it() -> None:
    statements = prepare("db.c.find({ a: \n  b })\ndb.c.countDocuments()").statements

    assert [statement.kind for statement in statements] == ["unknown", "read"]
    assert statements[1].text == "db.c.countDocuments()"


def test_what_takes_something_away_is_asked_about_every_time() -> None:
    def marks(text: str) -> tuple[str, bool]:
        [statement] = prepare(text).statements
        return statement.risk, statement.destructive

    assert marks("db.c.drop()") == ("high", True)
    assert marks("db.dropDatabase()") == ("high", True)
    assert marks("db.c.dropIndex('a_1')") == ("high", True)
    assert marks("db.c.deleteMany({})") == ("high", False)
    assert marks("db.c.deleteMany({ a: 1 })") == ("low", False)
    assert marks("db.c.aggregate([{ $out: 'x' }])") == ("high", True)
    assert marks("db.c.renameCollection('d', true)") == ("high", True)
    assert marks("db.c.renameCollection('d')") == ("low", False)


def test_a_collection_is_named_the_way_the_shell_can_reach_it() -> None:
    assert collection_text("shop", "orders", "shop") == "db.orders"
    assert collection_text("shop", "page views", "shop") == 'db.getCollection("page views")'
    assert collection_text("shop", "stats", "shop") == 'db.getCollection("stats")'
    assert collection_text("lab", "orders", "shop") == 'db.getSiblingDB("lab").orders'


# --- Running it ---------------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_a_find_answers_with_the_fields_of_its_documents() -> None:
    finished = await _one("db.people.find({}, { tags: 0 }).sort({ name: -1 }).limit(2)")

    assert finished.status == "succeeded"
    assert finished.result is not None
    names = [column.name for column in finished.result.columns]
    assert names[0] == "_id" and "tags" not in names
    by_name = dict(zip(names, zip(*finished.result.rows, strict=True), strict=True))
    assert by_name["name"] == ("Cy", "Bob")
    assert finished.row_count == 2


@pytest.mark.usefixtures("server")
async def test_values_written_in_the_text_reach_the_server_as_their_types() -> None:
    finished = await _one(
        f'db.people.find({{ _id: ObjectId("{PEOPLE_IDS[0]}"), big: NumberLong("9007199254740993") }})'
    )

    assert finished.result is not None
    assert len(finished.result.rows) == 1


@pytest.mark.usefixtures("server")
async def test_counts_distinct_values_and_pipelines_are_rows() -> None:
    count = await _one("db.numbers.countDocuments({ n: 0 })")
    distinct = await _one("db.numbers.distinct('n')")
    grouped = await _one("db.numbers.aggregate([{ $group: { _id: '$n', c: { $sum: 1 } } }, { $sort: { _id: 1 } }])")

    assert count.result is not None and count.result.rows == [["36"]]
    assert distinct.result is not None and [row[0] for row in distinct.result.rows] == [str(n) for n in range(7)]
    assert grouped.result is not None and grouped.result.rows[0] == ["0", "36"]


@pytest.mark.usefixtures("server")
async def test_a_command_and_a_plan_answer_with_one_document() -> None:
    stats = await _one("db.runCommand({ dbStats: 1 })")
    plan = await _one("db.numbers.find({ n: 1 }).explain()")

    for finished in (stats, plan):
        assert finished.status == "succeeded"
        assert finished.result is not None
        assert finished.result.columns == [] and finished.result.rows == []
        assert isinstance(finished.result.document, JsonObject)
        assert finished.row_count is None
    assert stats.result is not None and isinstance(stats.result.document, JsonObject)
    db_field = next(entry for entry in stats.result.document.entries if entry.name == "db")
    assert db_field.value == JsonScalar(kind="string", value=DATABASE)


@pytest.mark.usefixtures("server")
async def test_a_long_result_is_cut_and_says_so() -> None:
    limits = LIMITS.model_copy(update={"max_result_rows": 5})
    [finished] = await _finished(
        adapter().open_query(
            QueryRequest(text="db.numbers.find()", mode="read", limits=limits, search_path=[DATABASE])
        )
    )

    assert finished.result is not None
    assert finished.result.truncated
    assert len(finished.result.rows) == 5


@pytest.mark.usefixtures("server")
async def test_a_read_cannot_write() -> None:
    finished = await _one("db.scratch.insertOne({ a: 1 })", mode="read")

    assert finished.status == "failed"
    assert finished.diagnostic is not None and finished.diagnostic.category == "read_only"
    client = raw_client()
    try:
        assert await client[DATABASE]["scratch"].count_documents({}) == 0
    finally:
        await client.close()


@pytest.mark.usefixtures("server")
async def test_a_change_runs_alone_and_says_what_it_did() -> None:
    inserted = await _one("db.scratch.insertMany([{ a: 1 }, { a: 2 }, { a: 3 }])", mode="auto_commit")
    updated = await _one("db.scratch.updateMany({ a: { $gte: 2 } }, { $set: { b: true } })", mode="auto_commit")
    deleted = await _one("db.scratch.deleteOne({ a: 1 })", mode="auto_commit")
    together = await _finished(
        adapter().open_query(_request("db.scratch.find()\ndb.scratch.drop()", "auto_commit"))
    )

    assert inserted.affected_rows == 3
    assert inserted.result is not None and isinstance(inserted.result.document, JsonObject)
    assert updated.affected_rows == 2
    assert deleted.affected_rows == 1
    assert together[1].status == "failed"
    assert together[1].diagnostic is not None
    assert "run it on its own" in together[1].diagnostic.message


@pytest.mark.usefixtures("server")
async def test_a_structure_change_names_what_to_read_again() -> None:
    created = await _one("db.createCollection('made_here')", mode="auto_commit")
    indexed = await _one("db.made_here.createIndex({ a: 1 }, { name: 'a_here' })", mode="auto_commit")
    dropped = await _one("db.made_here.drop()", mode="auto_commit")

    assert created.effect is not None and database_id(DATABASE) in created.effect.reload_node_ids
    assert indexed.command_tag is not None and "a_here" in indexed.command_tag
    assert indexed.effect is not None
    assert indexed.effect.relation_node_ids == [relation_id(DATABASE, "made_here")]
    assert dropped.status == "succeeded"


@pytest.mark.usefixtures("server")
async def test_use_switches_the_database_for_what_follows() -> None:
    [switched, counted] = await _finished(
        adapter().open_query(
            QueryRequest(
                text=f"use {DATABASE}\ndb.numbers.estimatedDocumentCount()", mode="read", limits=LIMITS
            )
        )
    )

    assert switched.status == "succeeded" and switched.command_tag is not None
    assert counted.result is not None and counted.result.rows == [["250"]]


@pytest.mark.usefixtures("server")
async def test_a_connection_with_no_database_asks_for_one() -> None:
    [finished] = await _finished(
        adapter(database="").open_query(QueryRequest(text="db.numbers.find()", mode="read", limits=LIMITS))
    )

    assert finished.status == "failed"
    assert finished.diagnostic is not None and finished.diagnostic.code == "dp_no_database"


@pytest.mark.usefixtures("server")
async def test_a_failure_carries_the_server_s_sentence() -> None:
    finished = await _one("db.numbers.find({ n: { $nope: 1 } })")
    duplicate = await _one(f'db.people.insertOne({{ _id: ObjectId("{PEOPLE_IDS[0]}") }})', mode="auto_commit")

    assert finished.status == "failed"
    assert finished.diagnostic is not None and "$nope" in finished.diagnostic.message
    assert duplicate.diagnostic is not None and duplicate.diagnostic.code == "11000"
    assert duplicate.diagnostic.category == "data"


@pytest.mark.usefixtures("server")
async def test_an_option_the_call_does_not_take_is_refused() -> None:
    finished = await _one("db.numbers.find({}, {}, { nonsense: 1 })")

    assert finished.status == "failed"
    assert finished.diagnostic is not None and "nonsense" in finished.diagnostic.message


@pytest.mark.usefixtures("server")
async def test_a_statement_is_stopped_by_its_time_and_by_stop() -> None:
    source = adapter()
    slow = "db.numbers.find({ $where: 'sleep(100) || true' })"
    limits = LIMITS.model_copy(update={"statement_timeout_seconds": 1})

    [timed] = await _finished(
        source.open_query(QueryRequest(text=slow, mode="read", limits=limits, search_path=[DATABASE]))
    )
    execution = source.open_query(_request(slow))
    collected = asyncio.ensure_future(_finished(execution))
    await asyncio.sleep(1)
    await execution.cancel()
    [cancelled] = await collected

    assert timed.status == "timed_out"
    assert cancelled.status == "cancelled"


@pytest.mark.usefixtures("server")
async def test_completion_lists_databases_and_collections() -> None:
    metadata = await adapter().query_metadata(QueryMetadataRequest(search_path=[DATABASE]))

    assert DATABASE in metadata.schemas
    assert {"people", "numbers"} <= {relation.name for relation in metadata.relations}
    assert metadata.complete is False


@pytest.mark.usefixtures("server")
async def test_a_generated_query_is_one_the_console_reads() -> None:
    source = adapter(database=DATABASE)
    node = relation_id(DATABASE, "people")
    select = await source.generate_query(GenerateQueryRequest(node_id=node))
    columns = await source.generate_query(GenerateQueryRequest(node_id=node, kind="columns"))

    assert select.text == "db.people.find({}).limit(100)"
    assert "name: 1" in columns.text
    [statement] = prepare(select.text).statements
    assert statement.kind == "read" and statement.refused is None
