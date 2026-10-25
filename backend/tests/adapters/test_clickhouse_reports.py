"""The System section of a ClickHouse source, and stopping what it shows (D275)."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.adapters.catalog import ReportNode
from app.adapters.clickhouse.reports import (
    MUTATIONS_REPORT_ID,
    PROCESSES_REPORT_ID,
    REPORTS,
    SECTION_ID,
)
from app.adapters.clickhouse.session import quoted_name
from app.adapters.content import ContentRequest, SqlContent
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.row_commands import UnknownRowCommand
from tests.adapters.clickhouse_fixture import DATABASE, adapter, build, run, tear_down
from tests.utils.services import CLICKHOUSE

DB = quoted_name(DATABASE)


@pytest.fixture(scope="module")
async def server() -> AsyncIterator[None]:
    CLICKHOUSE.require()
    await build()
    yield
    await tear_down()


@pytest.mark.usefixtures("server")
async def test_the_section_follows_the_databases_and_holds_every_report() -> None:
    source = adapter()

    top = await source.list_children(None)
    section = await source.list_children(SECTION_ID)

    assert top[-1].id == SECTION_ID and isinstance(top[-1], ReportNode)
    assert [node.id for node in section] == [report.node_id for report in REPORTS]
    assert [node.name for node in await source.path_to(PROCESSES_REPORT_ID)] == ["System", "Processes"]


@pytest.mark.usefixtures("server")
async def test_every_report_reads_as_a_page() -> None:
    source = adapter()
    for report in REPORTS:
        page = await source.fetch(FetchRequest(node_id=report.node_id, limit=5))

        assert page.columns, report.key
        assert not page.update_supported and not page.insert_supported
        assert not page.record_supported
        assert "create_relation" not in page.page_commands


@pytest.mark.usefixtures("server")
async def test_a_report_pages_sorts_and_filters_on_the_server() -> None:
    source = adapter()
    tables = f"{SECTION_ID}/tables"

    sized = await source.fetch(
        FetchRequest(
            node_id=tables,
            sort=[Sort(column="rows", descending=True)],
            filters=[ScalarFilter(column="database", op="eq", value=DATABASE)],
        )
    )
    names = [column.name for column in sized.columns]
    rows = [dict(zip(names, row, strict=True)) for row in sized.rows]

    assert {row["table"] for row in rows} >= {"items", "dupes"}
    counts = [int(row["rows"] or 0) for row in rows]
    assert counts == sorted(counts, reverse=True)
    processes = await source.fetch(FetchRequest(node_id=PROCESSES_REPORT_ID))
    assert processes.refresh_seconds == 5


@pytest.mark.usefixtures("server")
async def test_a_report_shows_the_statement_it_runs() -> None:
    content = await adapter().read_content(
        ContentRequest(node_id=MUTATIONS_REPORT_ID, representation="sql")
    )

    assert isinstance(content, SqlContent)
    assert content.text.startswith("SELECT toString(cityHash64(database, table, mutation_id)) AS id")


@pytest.mark.usefixtures("server")
async def test_a_running_query_is_cancelled_from_processes() -> None:
    source = adapter()
    long = asyncio.ensure_future(run("SELECT count() FROM numbers(100000000000) SETTINGS max_threads = 1"))
    try:
        query_id = None
        for _ in range(50):
            page = await source.fetch(
                FetchRequest(
                    node_id=PROCESSES_REPORT_ID,
                    filters=[ScalarFilter(column="query", op="contains", value="numbers(100000000000)")],
                )
            )
            names = [column.name for column in page.columns]
            found = [
                dict(zip(names, row, strict=True))
                for row in page.rows
                if "FROM processes" not in (row[names.index("query")] or "")
                and "system.processes" not in (row[names.index("query")] or "")
            ]
            if found:
                query_id = found[0]["id"]
                break
            await asyncio.sleep(0.1)
        assert query_id is not None
        assert [command.name for command in source.row_commands(PROCESSES_REPORT_ID)] == ["kill_query"]

        result = await source.run_row_command(PROCESSES_REPORT_ID, "kill_query", [query_id])

        assert result.done == 1
        with pytest.raises(AssertionError):
            await asyncio.wait_for(long, 10)
    finally:
        long.cancel()


@pytest.mark.usefixtures("server")
async def test_a_stuck_mutation_is_stopped_and_stops_holding_the_table() -> None:
    source = adapter()
    await run(
        f"CREATE TABLE {DB}.stuck (id UInt32, v String) ENGINE = MergeTree ORDER BY id",
        f"INSERT INTO {DB}.stuck VALUES (1, 'abc')",
        # Not waited for, so it stays failing in the background.
        f"ALTER TABLE {DB}.stuck UPDATE v = toString(toInt32(v)) WHERE 1",
    )
    page = await source.fetch(
        FetchRequest(
            node_id=MUTATIONS_REPORT_ID,
            filters=[ScalarFilter(column="table", op="eq", value="stuck")],
        )
    )
    names = [column.name for column in page.columns]
    [row] = [dict(zip(names, row, strict=True)) for row in page.rows]

    result = await source.run_row_command(MUTATIONS_REPORT_ID, "kill_mutation", [str(row["id"])])

    assert result.done == 1
    # Nothing is left in front of the next mutation.
    await run(f"ALTER TABLE {DB}.stuck UPDATE v = 'x' WHERE 1 SETTINGS mutations_sync = 1")
    with pytest.raises(ValueError, match="does not name"):
        await source.run_row_command(MUTATIONS_REPORT_ID, "kill_mutation", ["1; DROP"])
    with pytest.raises(UnknownRowCommand):
        await source.run_row_command(PROCESSES_REPORT_ID, "kill_mutation", ["1"])
