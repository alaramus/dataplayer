"""The lab as a DuckDB file, opened through the source as a person would (D402)."""

from pathlib import Path

from app.adapters.catalog import SchemaNode, TableNode
from app.adapters.duckdb.adapter import DuckdbAdapter
from app.adapters.duckdb.options import DuckdbOptions
from app.adapters.duckdb.samples import SAMPLE_FILE, write_sample_database
from app.adapters.fetch import FetchRequest


async def test_the_lab_opens_with_its_schemas_tables_keys_and_rows(tmp_path: Path) -> None:
    write_sample_database(tmp_path / SAMPLE_FILE)
    adapter = DuckdbAdapter(DuckdbOptions(path=SAMPLE_FILE), tmp_path)

    check = await adapter.check_connection()
    schemas = [node.name for node in await adapter.list_children(None) if isinstance(node, SchemaNode)]
    relations = await adapter.list_children("main")
    page = await adapter.fetch(FetchRequest(node_id="main.tasks", limit=50))
    model = await adapter.relation_model("main.tasks")

    assert check.ok, check
    assert schemas == ["archive", "main"]
    tables = {node.name for node in relations if isinstance(node, TableNode)}
    assert tables >= {"organizations", "app_users", "teams", "projects", "tasks", "ledger", "import_log"}
    assert "project_rollup" in {node.name for node in relations}
    assert page.has_more is True and page.update_supported is True
    assert {constraint.kind for constraint in model.constraints} >= {"primary_key", "foreign_key", "check"}


def test_writing_it_again_replaces_the_file(tmp_path: Path) -> None:
    path = tmp_path / SAMPLE_FILE
    path.write_bytes(b"not a database")

    write_sample_database(path)
    write_sample_database(path)

    assert path.read_bytes()[8:12] == b"DUCK"
    assert sorted(file.name for file in tmp_path.iterdir()) == [SAMPLE_FILE]
