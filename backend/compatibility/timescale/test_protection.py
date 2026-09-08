import pytest

from app.adapters.content import ContentRequest
from app.adapters.fetch import FetchRequest
from app.adapters.update import InsertRowRequest
from compatibility.timescale.source import TimescaleSource


@pytest.mark.parametrize("node_id", ["lab.metrics", "lab.empty_metrics", "lab.hourly"])
async def test_specialized_relations_refuse_direct_insert_and_reconstructed_ddl(
    source: TimescaleSource, node_id: str,
) -> None:
    adapter = source.adapter()
    before = await adapter.fetch(FetchRequest(node_id=node_id, limit=100))
    with pytest.raises(ValueError, match="TimescaleDB.*read-only"):
        await adapter.insert_row(InsertRowRequest(node_id=node_id))
    with pytest.raises(ValueError, match="reconstructed DDL is unavailable"):
        await adapter.read_content(ContentRequest(node_id=node_id, representation="sql"))
    after = await adapter.fetch(FetchRequest(node_id=node_id, limit=100))
    assert sorted(before.rows) == sorted(after.rows)
    assert not after.insert_supported and not after.update_supported and not after.delete_supported


async def test_internal_chunks_and_materializations_refuse_direct_operations(
    source: TimescaleSource,
) -> None:
    identities = await source.session().query(
        "SELECT chunk_schema AS schema_name, chunk_name AS relation_name "
        "FROM timescaledb_information.chunks "
        "WHERE hypertable_schema = 'lab' AND hypertable_name = 'metrics' "
        "UNION ALL "
        "SELECT materialization_hypertable_schema, materialization_hypertable_name "
        "FROM timescaledb_information.continuous_aggregates "
        "WHERE view_schema = 'lab' AND view_name = 'hourly'",
    )
    assert len(identities) >= 4
    adapter = source.adapter()
    for identity in identities:
        node_id = f"{identity['schema_name']}.{identity['relation_name']}"
        with pytest.raises(ValueError, match="read-only"):
            await adapter.insert_row(InsertRowRequest(node_id=node_id))
        with pytest.raises(ValueError, match="reconstructed DDL is unavailable"):
            await adapter.read_content(ContentRequest(node_id=node_id, representation="sql"))
