from collections.abc import AsyncGenerator

import pytest

from app.adapters.export import EXPORT_BATCH_SIZE, ExportRequest
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


async def test_export_uses_bounded_batches_beyond_the_fetch_ceiling(schema: str) -> None:
    await run(
        f"CREATE TABLE {schema}.export_values ("  # noqa: S608 -- schema is fixture-owned.
        "id integer PRIMARY KEY, label text NOT NULL)"
    )
    await run(
        f"INSERT INTO {schema}.export_values "  # noqa: S608 -- schema is fixture-owned.
        "SELECT value, 'row-' || value FROM generate_series(1, 1201) AS value"
    )

    batches = [
        batch
        async for batch in _adapter().export_rows(
            ExportRequest.model_validate(
                {
                    "node_id": f"{schema}.export_values",
                    "columns": ["label", "id"],
                    "filters": [{"column": "id", "op": "gte", "value": "2"}],
                    "sort": [{"column": "id", "descending": True}],
                }
            )
        )
    ]

    assert [len(batch.rows) for batch in batches] == [
        EXPORT_BATCH_SIZE,
        EXPORT_BATCH_SIZE,
        200,
    ]
    rows = [row for batch in batches for row in batch.rows]
    assert rows[0] == ["row-1201", "1201"]
    assert rows[-1] == ["row-2", "2"]


async def test_export_rejects_a_column_before_opening_the_stream(schema: str) -> None:
    statement = (  # noqa: S608 -- schema is fixture-owned.
        f"CREATE TABLE {schema}.export_values (id integer)"
    )
    await run(statement)

    with pytest.raises(ValueError, match="missing"):
        async for _ in _adapter().export_rows(
            ExportRequest(node_id=f"{schema}.export_values", columns=["missing"])
        ):
            pass
