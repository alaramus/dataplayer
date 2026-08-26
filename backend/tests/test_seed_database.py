import re
from pathlib import Path

from app.core.db import engine
from app.seed_database import fixture_paths, main


def test_schema_is_applied_before_its_data(tmp_path: Path) -> None:
    schema = tmp_path / "postgres_complex_schema.sql"
    data = tmp_path / "postgres_complex_data.sql"
    schema.write_text("CREATE SCHEMA demo_lab;", encoding="utf-8")
    data.write_text("INSERT INTO demo_lab.sample VALUES (1);", encoding="utf-8")

    assert fixture_paths(tmp_path) == (schema, data)


def test_development_start_runs_both_fixture_seeders() -> None:
    repository = Path(__file__).parents[2]
    script = (repository / "backend/scripts/prestart-dev.sh").read_text(
        encoding="utf-8"
    )

    database_seed = "python -m app.seed_database /app/sql"
    storage_seed = "python -m app.seed_storage"
    assert database_seed in script
    assert storage_seed in script
    assert script.index(database_seed) < script.index(storage_seed)


def test_development_prestart_mounts_sql_fixtures_read_only() -> None:
    repository = Path(__file__).parents[2]
    override = (repository / "compose.override.yml").read_text(encoding="utf-8")

    assert "./sql:/app/sql:ro" in override


def test_demo_project_codes_fit_the_schema_column() -> None:
    repository = Path(__file__).parents[2]
    schema = (repository / "sql/postgres_complex_schema.sql").read_text(
        encoding="utf-8"
    )
    data = (repository / "sql/postgres_complex_data.sql").read_text(encoding="utf-8")

    code_width_match = re.search(r"code char\((\d+)\)", schema)
    assert code_width_match is not None
    code_width = int(code_width_match.group(1))
    project_codes = set(re.findall(r"'[A-Z]{2}-[A-Z0-9]+'", data))

    assert project_codes
    assert all(len(code) - 2 <= code_width for code in project_codes)


async def test_demo_fixtures_can_be_loaded_into_postgres() -> None:
    repository = Path(__file__).parents[2]

    await main(repository / "sql")

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
