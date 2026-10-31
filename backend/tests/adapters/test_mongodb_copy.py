"""Collections copied, a database backed up, the server measured, the lab made (D291–D294)."""

import uuid
from collections.abc import AsyncIterator

import pytest
from bson import Decimal128, Int64, ObjectId

from app.adapters.database_ids import database_id, relation_id
from app.adapters.metrics import SupportsMetrics
from app.adapters.mongodb.samples import SAMPLE_DATABASE
from app.adapters.protocol import SupportsBackup, SupportsSampleData
from app.adapters.table_copy import CopyLoad, TableCopyRequest, TableCopyTarget
from tests.adapters.mongodb_fixture import (
    DATABASE,
    adapter,
    build,
    options,
    raw_client,
    tear_down,
)
from tests.utils.services import MONGODB

TARGET = "dp_test_mongodb_copies"


@pytest.fixture
async def server() -> AsyncIterator[None]:
    MONGODB.require()
    await build()
    client = raw_client()
    try:
        await client.drop_database(TARGET)
        await client[TARGET].create_collection("already")
    finally:
        await client.close()
    yield
    await tear_down()
    client = raw_client()
    try:
        await client.drop_database(TARGET)
        await client.drop_database(SAMPLE_DATABASE)
    finally:
        await client.close()


def test_it_claims_what_slice_six_brings() -> None:
    source = adapter()

    assert isinstance(source, SupportsBackup)
    assert isinstance(source, SupportsMetrics)
    assert isinstance(source, SupportsSampleData)
    assert source.table_copy_dialect == "mongodb"


# --- Copies ----------------------------------------------------------------------


async def _copy(names: dict[str, str], *, rows: bool = True) -> None:
    source = adapter()
    tables = await source.describe_for_copy([relation_id(DATABASE, name) for name in names])
    request = TableCopyRequest(
        dialect="mongodb",
        place_node_id=database_id(TARGET),
        same_database=True,
        tables=[TableCopyTarget(table=table, name=names[table.name]) for table in tables],
        rows=rows,
    )
    async with source.reading_tables() as reading:

        def rows_of(load: CopyLoad) -> AsyncIterator[bytes]:
            return reading.rows(load.node_id, load.columns)

        async def arrived(load: CopyLoad, count: int, size: int) -> None:
            pass

        await adapter().carry_table_copy(request, rows_of, arrived)


@pytest.mark.usefixtures("server")
async def test_a_collection_is_copied_with_its_documents_options_and_indexes() -> None:
    await _copy({"people": "people", "books": "books", "numbers": "figures"})

    client = raw_client()
    try:
        copied = await client[TARGET]["people"].find().sort("_id", 1).to_list()
        original = await client[DATABASE]["people"].find().sort("_id", 1).to_list()
        assert copied == original
        assert isinstance(copied[0]["big"], Int64)
        assert isinstance(copied[0]["price"], Decimal128)
        assert isinstance(copied[0]["_id"], ObjectId)
        indexes = {index["name"]: index for index in await (await client[TARGET]["people"].list_indexes()).to_list()}
        assert indexes["people_name"]["unique"]
        books = await (await client[TARGET].list_collections(filter={"name": "books"})).to_list()
        assert "validator" in books[0]["options"]
        assert await client[TARGET]["figures"].count_documents({}) == 250
    finally:
        await client.close()


@pytest.mark.usefixtures("server")
async def test_a_plan_says_what_it_would_do_and_what_it_cannot() -> None:
    source = adapter()
    tables = await source.describe_for_copy(
        [relation_id(DATABASE, "people"), relation_id(DATABASE, "adults")]
    )
    assert tables[1].refusal is not None
    assert await source.free_table_names(database_id(TARGET), ["already", "fresh"]) == ["already_copy", "fresh"]

    plan = await source.plan_table_copy(
        TableCopyRequest(
            dialect="mongodb",
            place_node_id=database_id(TARGET),
            same_database=True,
            tables=[
                TableCopyTarget(table=tables[0], name="already"),
                TableCopyTarget(table=tables[1], name="adults"),
            ],
        )
    )
    assert {problem.kind for problem in plan.problems} == {"conflict", "invalid"}

    plan = await source.plan_table_copy(
        TableCopyRequest(
            dialect="mongodb",
            place_node_id=database_id(TARGET),
            same_database=True,
            tables=[TableCopyTarget(table=tables[0], name="people")],
        )
    )
    assert plan.problems == []
    assert plan.statements[0].sql.startswith('db.getSiblingDB("dp_test_mongodb_copies").createCollection("people"')
    assert any("createIndex" in statement.sql and statement.stage == "after" for statement in plan.statements)


@pytest.mark.usefixtures("server")
async def test_a_failed_copy_leaves_nothing_behind() -> None:
    source = adapter()
    [table] = await source.describe_for_copy([relation_id(DATABASE, "people")])
    # An index that cannot be built over these documents: unique over a field
    # two of them lack, which the index reads as two nulls.
    broken = table.model_copy(
        update={"indexes": [*table.indexes, table.indexes[0].model_copy(update={"name": "clash", "body": '{"key":{"address":{"$numberInt":"1"}},"unique":true}'})]}
    )
    request = TableCopyRequest(
        dialect="mongodb",
        place_node_id=database_id(TARGET),
        same_database=True,
        tables=[TableCopyTarget(table=broken, name="people")],
    )
    async with source.reading_tables() as reading:

        def rows_of(load: CopyLoad) -> AsyncIterator[bytes]:
            return reading.rows(load.node_id, load.columns)

        async def arrived(load: CopyLoad, count: int, size: int) -> None:
            pass

        with pytest.raises(ValueError):
            await adapter().carry_table_copy(request, rows_of, arrived)
    client = raw_client()
    try:
        names = await client[TARGET].list_collection_names()
    finally:
        await client.close()
    assert "people" not in names


# --- Backups ---------------------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_a_backup_is_mongodump_with_the_password_out_of_its_arguments() -> None:
    source = adapter(database=DATABASE)

    assert (await source.backup_availability()).available
    program = await source.backup_program(into="/data/users/x/backups/a.archive.gz")
    assert program.image == "mongo:8.0"
    assert "mongodump" in program.argv[2]
    # The test server's password is also a word of the script, so it is the
    # address carrying it that must not be an argument.
    assert all(":" + options().password.get_secret_value() + "@" not in part for part in program.argv)
    assert options().password.get_secret_value() in program.environment["DP_MONGODB_URI"]
    restore = await source.restore_program(from_file="/data/users/a.gz")
    assert "--drop" in restore.argv[2]
    assert restore.argv[4] == DATABASE
    check = await source.restore_inventory_program(from_file="/data/users/a.gz")
    assert "--dryRun" in check.argv[2]

    no_database = await adapter().backup_availability()
    assert not no_database.available
    through = await adapter(database=DATABASE, ssh_tunnel=str(uuid.uuid4())).backup_availability()
    assert not through.available


def test_an_archive_is_judged_by_what_it_holds() -> None:
    source = adapter(database="shop")

    assert source.restore_archive_reason(b"\x1f\x8b\x08\x00") is None
    assert source.restore_archive_reason(b"CREATE TABLE") is not None
    source.validate_restore_inventory(
        [
            "2026-10-31T00:00:00 archive prelude `shop.orders`",
            "2026-10-31T00:00:00 dry run completed",
            "dataplayer-whole",
        ]
    )
    with pytest.raises(ValueError, match="other|database"):
        source.validate_restore_inventory(["archive prelude `blog.posts`", "dataplayer-whole"])
    with pytest.raises(ValueError, match="whole"):
        source.validate_restore_inventory(["archive prelude `shop.orders`"])


# --- Metrics and the lab --------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_the_server_is_measured() -> None:
    samples = await adapter(database=DATABASE).metric_samples()
    named = {(sample.metric, sample.field): sample for sample in samples}

    assert named[("sessions", "connections")].value >= 1
    assert named[("operations", "query")].counter
    assert named[("database", "documents")].value >= 255
    assert adapter().metric_presets()[0].key == "mongodb-server"


@pytest.mark.usefixtures("server")
async def test_the_lab_is_made_and_the_same_every_time() -> None:
    said = await adapter().install_sample_data()

    assert said.startswith(f"{SAMPLE_DATABASE}: ")
    nodes = {node.name: node for node in await adapter().list_children(database_id(SAMPLE_DATABASE))}
    assert {"customers", "products", "orders", "page_views", "order_totals"} <= set(nodes)
    model = await adapter().relation_model(relation_id(SAMPLE_DATABASE, "customers"))
    assert "vip" in {column.name for column in model.columns}
    client = raw_client()
    try:
        first = await client[SAMPLE_DATABASE]["orders"].find_one({"number": 1})
        await adapter().install_sample_data()
        again = await client[SAMPLE_DATABASE]["orders"].find_one({"number": 1})
    finally:
        await client.close()
    assert first is not None and again is not None
    assert {key: value for key, value in first.items() if key != "_id"} == {
        key: value for key, value in again.items() if key != "_id"
    }


@pytest.mark.usefixtures("server")
async def test_a_time_series_is_listed_once_and_without_its_buckets_count() -> None:
    await adapter().install_sample_data()

    nodes = {node.name: node for node in await adapter().list_children(database_id(SAMPLE_DATABASE))}

    assert not any(name.startswith("system.buckets.") for name in nodes)
    assert getattr(nodes["page_views"], "row_count_estimate", 0) is None
    assert getattr(nodes["orders"], "row_count_estimate", 0) == 2000
