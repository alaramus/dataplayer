"""The lab as a SQLite file, opened through the source as a person would (D261)."""

from pathlib import Path

from app.adapters.catalog import TableNode
from app.adapters.fetch import FetchRequest
from app.adapters.sqlite.adapter import SqliteAdapter
from app.adapters.sqlite.options import SqliteOptions
from app.adapters.sqlite.samples import SAMPLE_FILE, write_sample_database


async def test_the_lab_opens_with_its_tables_keys_and_rows(tmp_path: Path) -> None:
    write_sample_database(tmp_path / SAMPLE_FILE)
    adapter = SqliteAdapter(SqliteOptions(path=SAMPLE_FILE), tmp_path)

    check = await adapter.check_connection()
    relations = await adapter.list_children("main")
    page = await adapter.fetch(FetchRequest(node_id="main.tasks", limit=50))
    model = await adapter.relation_model("main.tasks")

    assert check.ok, check
    tables = {node.name for node in relations if isinstance(node, TableNode)}
    assert tables >= {"organizations", "app_users", "teams", "projects", "tasks", "import_log"}
    assert {node.name for node in relations} >= {"project_rollup", "task_search"}
    assert page.has_more is True
    # The trigger trimmed what the script wrote with spaces before it.
    title = [column.name for column in page.columns].index("title")
    assert not str(page.rows[0][title]).startswith(" ")
    assert {constraint.kind for constraint in model.constraints} >= {"primary_key", "foreign_key", "check"}


def test_writing_it_again_replaces_the_file(tmp_path: Path) -> None:
    path = tmp_path / SAMPLE_FILE
    path.write_bytes(b"not a database")

    write_sample_database(path)
    write_sample_database(path)

    assert path.read_bytes().startswith(b"SQLite format 3\x00")
    assert sorted(file.name for file in tmp_path.iterdir()) == [SAMPLE_FILE]
