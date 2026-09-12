import re
from pathlib import Path

from app.adapters.postgres.samples import (
    SCRIPT_DIRECTORY,
    script_paths,
    timescale_script_paths,
)
from app.core.db import engine
from app.seed_database import main


def test_schema_is_applied_before_its_data(tmp_path: Path) -> None:
    schema = tmp_path / "postgres_complex_schema.sql"
    data = tmp_path / "postgres_complex_data.sql"
    schema.write_text("CREATE SCHEMA demo_lab;", encoding="utf-8")
    data.write_text("INSERT INTO demo_lab.sample VALUES (1);", encoding="utf-8")

    assert script_paths(tmp_path) == (schema, data)


def test_development_start_runs_both_fixture_seeders() -> None:
    repository = Path(__file__).parents[2]
    script = (repository / "backend/scripts/prestart-dev.sh").read_text(
        encoding="utf-8"
    )

    database_seed = "python -m app.seed_database"
    storage_seed = "python -m app.seed_storage"
    assert database_seed in script
    assert storage_seed in script
    assert script.index(database_seed) < script.index(storage_seed)


def test_the_scripts_ship_with_the_driver_that_runs_them() -> None:
    """One copy of them, because a service started here is filled with it.

    They used to be mounted into the one-shot prestart container from the
    repository. A service somebody asks this server to start is filled with
    the same two files, so they are part of the application now — and a second
    copy of a three-hundred-line schema is a second copy that drifts.
    """
    for path in script_paths():
        assert path.is_file(), path
    assert SCRIPT_DIRECTORY.parent.name == "postgres"

    repository = Path(__file__).parents[2]
    override = (repository / "compose.override.yml").read_text(encoding="utf-8")
    assert "/app/sql" not in override


def test_the_timescale_scripts_ship_beside_them() -> None:
    """A database holding the extension is filled with two more files.

    They are not a separate demonstration: they add to the schema the first
    script created, so they come after it and ship in the same directory.
    """
    schema, settle = timescale_script_paths()

    assert schema.name == "timescale_schema.sql"
    assert settle.name == "timescale_settle.sql"
    for path in timescale_script_paths():
        assert path.is_file(), path


def test_what_cannot_run_inside_a_transaction_is_not_in_the_transaction() -> None:
    """The trap this pair of files exists to avoid.

    A script of several statements is one transaction to the driver whatever
    autocommit says, and refreshing a continuous aggregate or converting a
    chunk to the columnstore is a procedure that commits. Put in the first
    file, the refusal took the whole demonstration with it and the database
    was left with nothing.
    """
    schema, settle = (path.read_text(encoding="utf-8") for path in timescale_script_paths())

    assert "BEGIN;" in schema and "COMMIT;" in schema
    assert "BEGIN;" not in settle

    for procedure in ("refresh_continuous_aggregate", "convert_to_columnstore"):
        assert procedure in settle, procedure
        assert procedure not in schema, procedure
    # And the view is created empty, because creating it full refreshes it.
    assert "WITH NO DATA" in schema


def test_demo_project_codes_fit_the_schema_column() -> None:
    schema, data = (path.read_text(encoding="utf-8") for path in script_paths())

    code_width_match = re.search(r"code char\((\d+)\)", schema)
    assert code_width_match is not None
    code_width = int(code_width_match.group(1))
    project_codes = set(re.findall(r"'[A-Z]{2}-[A-Z0-9]+'", data))

    assert project_codes
    assert all(len(code) - 2 <= code_width for code in project_codes)


async def test_demo_fixtures_can_be_loaded_into_postgres() -> None:
    await main(SCRIPT_DIRECTORY)

    async with engine.connect() as connection:
        counts = {}
        queries = {
            "documents": "SELECT count(*) FROM demo_lab.documents",
            "measurements_2025": "SELECT count(*) FROM demo_lab.measurements_2025",
            "task_dependencies": "SELECT count(*) FROM demo_lab.task_dependencies",
            "tasks": "SELECT count(*) FROM demo_lab.tasks",
            "tasks_late": "SELECT count(*) FROM demo_lab.tasks_late",
            "task_tags": "SELECT count(*) FROM demo_lab.task_tags",
            "team_members": "SELECT count(*) FROM demo_lab.team_members",
        }
        for relation, query in queries.items():
            counts[relation] = (
                await connection.exec_driver_sql(query)
            ).scalar_one()

    assert counts == {
        "documents": 2,
        "measurements_2025": 2,
        "task_dependencies": 1,
        "tasks": 4,
        "tasks_late": 1,
        "task_tags": 2,
        "team_members": 3,
    }
