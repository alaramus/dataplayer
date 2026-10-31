"""The server's reports, search by name, export and catalog actions (D289, D290)."""

import asyncio
import io
from collections.abc import AsyncIterator

import pytest

from app.adapters.catalog import ReportNode, TableNode
from app.adapters.content import ContentRequest, JsonContent
from app.adapters.database_ids import database_id, relation_id
from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.mongodb.reports import SECTION_ID
from app.adapters.mongodb.row_commands import OPERATIONS_REPORT_ID
from app.adapters.search import NodeSearchRequest, SearchBounds
from tests.adapters.mongodb_fixture import (
    DATABASE,
    adapter,
    build,
    raw_client,
    tear_down,
)
from tests.utils.services import MONGODB

NUMBERS = relation_id(DATABASE, "numbers")
SCRATCH = "dp_test_mongodb_scratch"


@pytest.fixture
async def server() -> AsyncIterator[None]:
    MONGODB.require()
    await build()
    yield
    await tear_down()
    client = raw_client()
    try:
        await client.drop_database(SCRATCH)
    finally:
        await client.close()


# --- Reports -----------------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_the_reports_sit_after_the_databases() -> None:
    top = await adapter().list_children(None)

    assert isinstance(top[-1], ReportNode)
    assert top[-1].id == SECTION_ID
    reports = await adapter().list_children(SECTION_ID)
    assert {node.id for node in reports} >= {OPERATIONS_REPORT_ID}
    assert [node.name for node in await adapter().path_to(OPERATIONS_REPORT_ID)] == ["Server", "Operations"]


@pytest.mark.usefixtures("server")
async def test_the_users_report_is_filtered_and_ordered_by_the_server() -> None:
    page = await adapter().fetch(
        FetchRequest(
            node_id=f"{SECTION_ID}/users",
            filters=[ScalarFilter(column="user", op="eq", value="root")],
            sort=[Sort(column="database")],
        )
    )
    names = [column.name for column in page.columns]

    assert names == ["user", "database", "roles", "mechanisms"]
    assert page.rows[0][:2] == ["root", "admin"]
    assert "root@admin" in (page.rows[0][2] or "")
    assert not page.update_supported
    assert not page.record_supported
    assert "create_relation" not in page.page_commands


@pytest.mark.usefixtures("server")
async def test_a_running_operation_is_listed_and_stopped() -> None:
    client = raw_client()
    slow = asyncio.create_task(
        client[DATABASE]["numbers"].find_one({"$where": "sleep(200) || false"})
    )
    try:
        await asyncio.sleep(0.5)
        page = await adapter().fetch(
            FetchRequest(
                node_id=OPERATIONS_REPORT_ID,
                filters=[ScalarFilter(column="namespace", op="eq", value=f"{DATABASE}.numbers")],
            )
        )
        assert page.rows, "the slow find is not among the operations"
        assert page.refresh_seconds == 5
        commands = adapter().row_commands(OPERATIONS_REPORT_ID)
        assert [command.name for command in commands] == ["kill_operation"]
        opid = page.rows[0][0] or ""
        answer = await adapter().run_row_command(OPERATIONS_REPORT_ID, "kill_operation", [opid])
        assert answer.done == 1
        with pytest.raises(Exception):  # noqa: B017, PT011  # the driver's own error for a killed operation
            await asyncio.wait_for(slow, 30)
    finally:
        slow.cancel()
        await client.close()
    with pytest.raises(ValueError):
        await adapter().run_row_command(OPERATIONS_REPORT_ID, "kill_operation", ["1; drop"])


@pytest.mark.usefixtures("server")
async def test_a_report_s_pipeline_is_its_definition() -> None:
    content = await adapter().read_content(
        ContentRequest(node_id=f"{SECTION_ID}/operations", representation="json")
    )

    assert isinstance(content, JsonContent)


# --- Search and export ---------------------------------------------------------


@pytest.mark.usefixtures("server")
async def test_databases_collections_and_reports_are_found_by_name() -> None:
    found = await adapter().search_nodes(NodeSearchRequest(query="numb"))
    assert [match.node.id for match in found.matches] == [NUMBERS]
    assert found.matches[0].parent_id == database_id(DATABASE)

    scoped = await adapter().search_nodes(NodeSearchRequest(node_id=database_id(DATABASE), query="logs web"))
    assert [match.node.name for match in scoped.matches] == ["logs.2026.web"]

    reports = await adapter().search_nodes(NodeSearchRequest(node_id=SECTION_ID, query="users"))
    assert [match.node.id for match in reports.matches] == [f"{SECTION_ID}/users"]


@pytest.mark.usefixtures("server")
async def test_every_name_is_listed_for_a_kept_list() -> None:
    names = [
        kept.node.id
        async for batch in adapter().enumerate_names(10_000, SearchBounds.within(10))
        for kept in batch.names
    ]

    assert database_id(DATABASE) in names
    assert NUMBERS in names


@pytest.mark.usefixtures("server")
async def test_every_matching_document_is_exported() -> None:
    rows = [
        row
        async for batch in adapter().export_rows(
            ExportRequest(
                node_id=NUMBERS,
                columns=["label", "_id"],
                filters=[ScalarFilter(column="n", op="eq", value="0")],
            )
        )
        for row in batch.rows
    ]

    assert len(rows) == 36
    assert rows[1] == ["row 007", "7"]
    with pytest.raises(ValueError):
        async for _ in adapter().export_rows(ExportRequest(node_id=NUMBERS, columns=["nope"])):
            pass


# --- Catalog actions -----------------------------------------------------------


class _Upload:
    def __init__(self, data: bytes, filename: str) -> None:
        self._body = io.BytesIO(data)
        self.filename = filename
        self.content_type = "text/csv"

    async def read(self, size: int) -> bytes:
        return self._body.read(size)


@pytest.mark.usefixtures("server")
async def test_a_database_is_made_with_its_first_collection_and_dropped() -> None:
    source = adapter()
    made = await source.action("create_database").perform(None, {"name": SCRATCH, "collection": "first"})
    assert made.created_node_id == relation_id(SCRATCH, "first")
    with pytest.raises(Exception, match="already exists"):
        await source.action("create_database").perform(None, {"name": SCRATCH, "collection": "x"})

    await source.action("create_collection").perform(database_id(SCRATCH), {"name": "second"})
    preview = await source.action("drop_database").preview(database_id(SCRATCH), {})
    assert preview.blocked
    await source.action("drop_database").perform(database_id(SCRATCH), {"cascade": True})
    assert SCRATCH not in [node.name for node in await source.list_children(None)]


@pytest.mark.usefixtures("server")
async def test_a_collection_is_renamed_moved_and_dropped() -> None:
    source = adapter()
    await source.action("create_database").perform(None, {"name": SCRATCH, "collection": "first"})

    renamed = await source.action("rename_relation").perform(NUMBERS, {"new_name": "figures"})
    assert renamed.replacement is not None
    figures = renamed.replacement.new_node_id
    moved = await source.action("move_relation").perform(figures, {"target_schema": database_id(SCRATCH)})
    assert moved.replacement is not None
    assert moved.replacement.new_node_id == relation_id(SCRATCH, "figures")
    model = await source.relation_model(relation_id(SCRATCH, "figures"))
    assert model.row_estimate == 250

    preview = await source.action("drop_relation").preview(relation_id(DATABASE, "people"), {})
    assert any("adults" in item for item in preview.items)
    await source.action("drop_relation").perform(relation_id(DATABASE, "people"), {})
    names = [node.name for node in await source.list_children(database_id(DATABASE))]
    assert "people" not in names


@pytest.mark.usefixtures("server")
async def test_a_csv_becomes_a_collection_of_text() -> None:
    source = adapter()
    answer = await source.action("load_csv").perform_with_file(
        database_id(DATABASE), {"name": "cities"}, _Upload(b"name,people\nRiga,600000\nOslo,\n", "cities.csv")
    )

    assert answer.created_node_id == relation_id(DATABASE, "cities")
    client = raw_client()
    try:
        documents = await client[DATABASE]["cities"].find({}, {"_id": 0}).to_list()
    finally:
        await client.close()
    assert documents == [{"name": "Riga", "people": "600000"}, {"name": "Oslo"}]


@pytest.mark.usefixtures("server")
async def test_the_model_is_written_out() -> None:
    download = await adapter().action("describe_model").download([NUMBERS], {"dialect": "dbml"})

    body = b"".join([chunk async for chunk in download.body])
    assert b"numbers" in body
    assert download.metadata.filename == "numbers.dbml"


@pytest.mark.usefixtures("server")
async def test_the_server_s_own_offer_only_their_model() -> None:
    offered = await adapter().available(relation_id("admin", "system.version"))

    assert [action.name for action in offered] == ["describe_model"]
    top = await adapter().available(None)
    assert [action.name for action in top] == ["create_database"]
    assert isinstance((await adapter().path_to(NUMBERS))[-1], TableNode)
