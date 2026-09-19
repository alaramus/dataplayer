"""The example references a development stack draws (D106).

Nothing here needs a database: what can go wrong without anybody noticing is
an example that names a sample file or a fixture relation which has since been
renamed, and both halves of that are readable from this repository.
"""

from pathlib import Path

from app.adapters.explorer.samples import write_samples
from app.adapters.postgres.samples import SCRIPT_DIRECTORY, script_paths
from app.seed_references import EXAMPLES


def test_every_example_joins_two_ends() -> None:
    assert EXAMPLES
    for example in EXAMPLES:
        assert len(example.ends) == 2
        assert example.about


def test_every_file_end_names_a_sample_that_is_written(tmp_path: Path) -> None:
    write_samples(tmp_path)
    written = {path.name for path in tmp_path.rglob("*")}

    named = {
        end.node_id
        for example in EXAMPLES
        for end in example.ends
        if end.adapter_type == "file"
    }

    assert named
    assert named <= written


def test_every_database_end_names_a_relation_the_fixture_creates() -> None:
    fixture = "\n".join(
        path.read_text(encoding="utf-8") for path in script_paths(SCRIPT_DIRECTORY)
    )

    ends = [
        end
        for example in EXAMPLES
        for end in example.ends
        if end.adapter_type == "postgres"
    ]

    assert ends
    for end in ends:
        schema, _, relation = end.node_id.partition(".")
        assert f"CREATE SCHEMA {schema}" in fixture or f"SCHEMA IF NOT EXISTS {schema}" in fixture
        assert f"CREATE TABLE {relation}" in fixture
        assert end.column in fixture
