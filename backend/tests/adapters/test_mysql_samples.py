"""The lab a MySQL or MariaDB server started here may be filled with (D245)."""

import pytest

from app.adapters.fetch import FetchRequest
from app.adapters.mysql import ids
from app.adapters.mysql.samples import SAMPLE_DATABASE, SCRIPT, statements_of
from app.adapters.protocol import SupportsSampleData
from tests.adapters.mysql_fixture import TARGETS, Target, run


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour)
def target(request: pytest.FixtureRequest) -> Target:
    chosen: Target = request.param
    chosen.server.require()
    return chosen


def test_the_script_is_split_where_its_statements_end() -> None:
    statements = statements_of(SCRIPT.read_text(encoding="utf-8"))

    assert statements[0] == "DROP DATABASE IF EXISTS demo_lab"
    assert all(not statement.startswith("--") for statement in statements)
    assert any(statement.startswith("CREATE TRIGGER") for statement in statements)
    assert statements_of("SELECT 1;\n-- a note; here\nSELECT 'a;b';\n") == ["SELECT 1", "SELECT 'a;b'"]


async def test_a_server_is_filled_once_however_often_it_is_asked(target: Target) -> None:
    source = target.adapter()
    assert isinstance(source, SupportsSampleData)
    try:
        first = await source.install_sample_data()
        again = await source.install_sample_data()

        assert first == again == f"{SAMPLE_DATABASE}: 14 tables"
        nodes = await source.list_children(ids.database_id(SAMPLE_DATABASE))
        assert {"tasks", "project_rollup", "import_log", "measurements"} <= {node.name for node in nodes}
        model = await source.relation_model(ids.relation_id(SAMPLE_DATABASE, "tasks"))
        assert len([one for one in model.constraints if one.kind == "foreign_key"]) == 2
        rollup = await source.fetch(
            FetchRequest(node_id=ids.relation_id(SAMPLE_DATABASE, "project_rollup"), limit=10)
        )
        assert len(rollup.rows) == 5
    finally:
        await run(target, f"DROP DATABASE IF EXISTS {SAMPLE_DATABASE}")
