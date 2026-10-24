"""The reports a MySQL or MariaDB server publishes about itself (D55, D237).

Every report is read on both servers: they keep several of these answers in
different places, and a statement right for one is refused by the other.
"""

from collections.abc import AsyncIterator

import pytest

from app.adapters.catalog import ReportNode
from app.adapters.content import ContentRequest, SqlContent
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.mysql import ids
from app.adapters.mysql.reports import (
    PROCESSES_REPORT_ID,
    REPORTS,
    SECTION_ID,
    SystemReport,
    report_for,
)
from app.adapters.mysql.session import ServerProfile
from app.adapters.protocol import NodeNotFound
from tests.adapters.mysql_fixture import DATABASE, TARGETS, Target, build, tear_down


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    yield chosen
    await tear_down(chosen)


async def test_the_section_follows_the_databases(target: Target) -> None:
    nodes = await target.adapter().list_children(None)

    assert nodes[-1].id == SECTION_ID
    assert isinstance(nodes[-1], ReportNode)
    assert nodes[-1].has_children


async def test_the_section_lists_every_report(target: Target) -> None:
    nodes = await target.adapter().list_children(SECTION_ID)

    assert [node.id for node in nodes] == [report.node_id for report in REPORTS]
    assert all(isinstance(node, ReportNode) and not node.has_children for node in nodes)
    assert [item.kind for item in nodes[0].representations] == ["table", "sql"]


async def test_a_report_s_path_is_the_section_and_itself(target: Target) -> None:
    path = await target.adapter().path_to(PROCESSES_REPORT_ID)

    assert [node.id for node in path] == [SECTION_ID, PROCESSES_REPORT_ID]


async def test_a_report_that_is_not_there_is_not_found(target: Target) -> None:
    with pytest.raises(NodeNotFound):
        await target.adapter().path_to(f"{SECTION_ID}/nothing")


def test_a_database_named_like_the_section_is_still_a_database() -> None:
    """A backslash in a name is written as two, so no database id is a report's."""
    assert ids.database_id("\\system") != SECTION_ID
    assert ids.parse(ids.database_id("\\system")) == ("\\system", None)


@pytest.mark.parametrize("report", REPORTS, ids=lambda report: report.key)
async def test_every_report_reads_on_both_servers(target: Target, report: SystemReport) -> None:
    page = await target.adapter().fetch(FetchRequest(node_id=report.node_id, limit=5))

    assert page.columns
    assert page.update_supported is False
    assert page.insert_supported is False
    assert page.record_supported is False
    assert all(handle is None for handle in page.row_handles)


async def test_the_processes_report_lists_the_connection_reading_it(target: Target) -> None:
    page = await target.adapter().fetch(
        FetchRequest(
            node_id=PROCESSES_REPORT_ID,
            limit=50,
            filters=[ScalarFilter(column="command", op="eq", value="Query")],
        )
    )

    names = [column.name for column in page.columns]
    assert names[:2] == ["id", "user"]
    assert page.rows, "the read itself is a query being run"
    assert page.refresh_seconds == 5


async def test_a_report_pages_and_sorts_on_the_server(target: Target) -> None:
    variables = f"{SECTION_ID}/variables"
    first = await target.adapter().fetch(FetchRequest(node_id=variables, limit=3))
    second = await target.adapter().fetch(FetchRequest(node_id=variables, limit=3, offset=3))
    backwards = await target.adapter().fetch(
        FetchRequest(node_id=variables, limit=1, sort=[Sort(column="name", descending=True)])
    )

    names = [str(row[0]) for row in first.rows + second.rows]
    assert names == sorted(names)
    assert first.has_more
    assert str(backwards.rows[0][0]) > names[-1]


async def test_a_report_s_column_from_the_client_is_checked_first(target: Target) -> None:
    with pytest.raises(ValueError, match="no column"):
        await target.adapter().fetch(
            FetchRequest(node_id=PROCESSES_REPORT_ID, limit=1, sort=[Sort(column="pid")])
        )


async def test_a_report_is_not_made_into_a_relation(target: Target) -> None:
    report = await target.adapter().fetch(FetchRequest(node_id=PROCESSES_REPORT_ID, limit=1))
    relation = await target.adapter().fetch(
        FetchRequest(node_id=ids.relation_id(DATABASE, "items"), limit=1)
    )

    assert "create_relation" not in report.page_commands
    assert "create_relation" in relation.page_commands
    assert relation.refresh_seconds is None


async def test_a_report_s_statement_is_what_it_runs(target: Target) -> None:
    content = await target.adapter().read_content(
        ContentRequest(node_id=f"{SECTION_ID}/variables", representation="sql")
    )

    assert isinstance(content, SqlContent)
    assert content.text.startswith("SELECT")
    assert "\n            " not in content.text


async def test_a_node_in_the_section_that_is_no_report_is_refused(target: Target) -> None:
    with pytest.raises(ValueError):
        await target.adapter().fetch(FetchRequest(node_id=f"{SECTION_ID}/nothing", limit=1))


@pytest.mark.parametrize(
    ("profile", "table"),
    [
        (ServerProfile(flavour="mysql", version=(8, 4, 11), text="8.4.11"), "performance_schema"),
        (ServerProfile(flavour="mysql", version=(8, 0, 22), text="8.0.22"), "performance_schema"),
        (ServerProfile(flavour="mysql", version=(8, 0, 21), text="8.0.21"), "information_schema"),
        (ServerProfile(flavour="mariadb", version=(11, 4, 13), text="11.4.13"), "information_schema"),
    ],
)
def test_the_processes_come_from_where_the_server_keeps_them(
    profile: ServerProfile, table: str
) -> None:
    """MySQL warns on every read of the old list after 8.0.22, and has no new one before."""
    statement = report_for(PROCESSES_REPORT_ID).statement_for(profile)  # type: ignore[union-attr]  # the report exists

    assert f"FROM {table}." in statement
