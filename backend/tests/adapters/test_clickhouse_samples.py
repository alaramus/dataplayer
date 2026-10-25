"""The lab a ClickHouse server started here may be filled with (D280)."""

from app.adapters.clickhouse.samples import SAMPLE_DATABASE, SCRIPT
from app.adapters.database_ids import database_id, relation_id
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import SupportsSampleData
from app.adapters.sample_scripts import statements_of
from tests.adapters.clickhouse_fixture import adapter, run
from tests.utils.services import CLICKHOUSE


def test_the_script_is_split_where_its_statements_end() -> None:
    statements = statements_of(SCRIPT.read_text(encoding="utf-8"))

    assert statements[0] == "DROP DATABASE IF EXISTS demo_lab SYNC"
    assert all(not statement.startswith("--") for statement in statements)
    assert all(";" not in statement for statement in statements)
    assert statements_of("SELECT 1;\n-- a note; here\nSELECT 'a;b';\n") == ["SELECT 1", "SELECT 'a;b'"]


async def test_a_server_is_filled_once_however_often_it_is_asked() -> None:
    CLICKHOUSE.require()
    source = adapter()
    assert isinstance(source, SupportsSampleData)
    try:
        first = await source.install_sample_data()
        again = await source.install_sample_data()

        assert first == again == f"{SAMPLE_DATABASE}: 7 tables"
        nodes = await source.list_children(database_id(SAMPLE_DATABASE))
        assert {"page_views", "path_totals", "project_rollup", "import_log"} <= {node.name for node in nodes}
        rollup = await source.fetch(
            FetchRequest(node_id=relation_id(SAMPLE_DATABASE, "project_rollup"), limit=10)
        )
        assert len(rollup.rows) == 5
        # Both materialized views were fed by the page views, once.
        [fed] = await source._session.query(
            "SELECT (SELECT sum(views) FROM demo_lab.daily_views) AS daily, "
            "(SELECT sum(views) FROM demo_lab.path_totals) AS paths"
        )
        assert int(fed["daily"]) == int(fed["paths"]) == 200_000
    finally:
        await run(f"DROP DATABASE IF EXISTS {SAMPLE_DATABASE}")
