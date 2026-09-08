import pytest

from app.adapters.column_changes import AddColumnRequest
from app.adapters.content import ContentRequest
from app.adapters.fetch import FetchRequest
from app.adapters.update import (
    CellEdit,
    DeleteRowsRequest,
    InsertRowRequest,
    InsertRowsRequest,
    RowEdit,
    UpdateCellRequest,
    UpdateCellsRequest,
)
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
        with pytest.raises(ValueError, match='"_timescaledb_internal" belongs to the server'):
            await adapter.insert_row(InsertRowRequest(node_id=node_id))
        with pytest.raises(ValueError, match="reconstructed DDL is unavailable"):
            await adapter.read_content(ContentRequest(node_id=node_id, representation="sql"))


@pytest.mark.parametrize("node_id", ["lab.metrics", "lab.empty_metrics", "lab.hourly"])
async def test_structured_writes_refuse_before_interpreting_forged_row_handles(
    source: TimescaleSource, node_id: str,
) -> None:
    adapter = source.adapter()
    before = await adapter.fetch(FetchRequest(node_id=node_id, limit=100))
    model = await adapter.relation_model(node_id)
    column = model.columns[0].name
    reason = "TimescaleDB.*read-only"
    with pytest.raises(ValueError, match=reason):
        await adapter.update_cell(UpdateCellRequest(
            node_id=node_id, row_handle="forged", column=column, value=None,
        ))
    with pytest.raises(ValueError, match=reason):
        await adapter.update_cells(UpdateCellsRequest(
            node_id=node_id,
            rows=[RowEdit(row_handle="forged", cells=[CellEdit(column=column, value=None)])],
        ))
    with pytest.raises(ValueError, match=reason):
        await adapter.delete_rows(DeleteRowsRequest(node_id=node_id, row_handles=["forged"]))
    with pytest.raises(ValueError, match=reason):
        await adapter.insert_rows(InsertRowsRequest(
            node_id=node_id, columns=[column], rows=[[None]],
        ))
    with pytest.raises(ValueError, match=reason):
        await adapter.add_column(AddColumnRequest(
            node_id=node_id, name="refused_column", type_code="text",
        ))
    assert not model.column_changes_supported
    assert not model.index_changes_supported
    assert not model.constraint_changes_supported
    assert await adapter.relation_model(node_id) == model
    after = await adapter.fetch(FetchRequest(node_id=node_id, limit=100))
    assert sorted(after.rows) == sorted(before.rows)
