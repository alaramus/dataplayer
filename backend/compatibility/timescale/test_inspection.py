import asyncio

import pytest

from app.adapters.export import ExportRequest
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.postgres.timescale.reports import REPORTS
from compatibility.timescale.source import TimescaleSource


async def test_discovery_is_per_database_and_ordinary_tables_keep_their_workflow(
    source: TimescaleSource,
) -> None:
    plain = source.adapter(database="plain_fixture")
    installed = (await source.adapter().source_features()).features[0]
    absent = (await plain.source_features()).features[0]
    assert installed.state == "available" and installed.installed_version == source.version
    assert absent.state == "absent" and absent.installed_version is None
    assert (await plain.relation_model("public.ordinary")).specialization is None
    for adapter in (plain, source.adapter()):
        rows = await adapter.fetch(FetchRequest(node_id="public.ordinary", limit=2))
        assert len(rows.rows) == 2 and rows.has_more
        assert rows.update_supported and rows.insert_supported and rows.delete_supported
    assert (await plain.backup_availability()).available
    assert not (await source.adapter().backup_availability()).available


@pytest.mark.parametrize(("node_id", "kind"), [
    ("lab.metrics", "timescale_hypertable"),
    ("lab.integer_metrics", "timescale_hypertable"),
    ("lab.empty_metrics", "timescale_hypertable"),
    ("lab.hourly", "timescale_continuous_aggregate"),
])
async def test_catalog_path_model_and_summary_agree(
    source: TimescaleSource, node_id: str, kind: str,
) -> None:
    adapter = source.adapter()
    nodes = await adapter.list_children("lab")
    node = next(node for node in nodes if node.id == node_id)
    path = await adapter.path_to(node_id)
    model = await adapter.relation_model(node_id)
    summary = await adapter.node_summary(node_id)
    assert node.specialization is not None and node.specialization.kind == kind
    assert path[-1] == node
    assert model.specialization == node.specialization
    assert summary.contents is not None and summary.contents.kind == "relation"
    assert summary.contents.specialization == node.specialization
    assert summary.contents.timescale is not None
    assert summary.contents.timescale.kind != "unavailable"
    assert summary.size_bytes is None and summary.contents.row_estimate is None
    assert summary.contents.analyzed_at is None and summary.contents.vacuumed_at is None
    assert summary.related_views


@pytest.mark.parametrize(("name", "sort_column", "expected_count"), [
    ("metrics", "observed_at", 72), ("integer_metrics", "tick", 8),
])
async def test_mixed_storage_reads_and_exports_without_physical_row_handles(
    source: TimescaleSource, name: str, sort_column: str, expected_count: int,
) -> None:
    chunks = await source.session().query(
        "SELECT chunks.is_compressed, access.amname "
        "FROM timescaledb_information.chunks AS chunks "
        "JOIN pg_catalog.pg_namespace AS namespace ON namespace.nspname = chunks.chunk_schema "
        "JOIN pg_catalog.pg_class AS relation "
        "ON relation.relnamespace = namespace.oid AND relation.relname = chunks.chunk_name "
        "JOIN pg_catalog.pg_am AS access ON access.oid = relation.relam "
        "WHERE chunks.hypertable_schema = 'lab' AND chunks.hypertable_name = %s",
        (name,),
    )
    assert {chunk["is_compressed"] for chunk in chunks} == {True, False}
    assert {chunk["amname"] for chunk in chunks if chunk["is_compressed"]} == {source.storage}
    adapter = source.adapter(user="fixture_reader")
    node_id = f"lab.{name}"
    result = await adapter.fetch(FetchRequest(
        node_id=node_id, sort=[Sort(column=sort_column)], limit=100,
    ))
    assert len(result.rows) == expected_count and not result.has_more
    assert result.row_handles == [None] * expected_count
    assert not result.update_supported and not result.insert_supported and not result.delete_supported
    names = [column.name for column in result.columns]
    exact_column = "value" if name == "metrics" else "tick"
    assert result.rows[0][names.index(exact_column)] == "9007199254740993"
    exported = [
        row async for batch in adapter.export_rows(ExportRequest(
            node_id=node_id, columns=names, sort=[Sort(column=sort_column)],
        )) for row in batch.rows
    ]
    assert exported == result.rows


async def test_all_public_reports_open_and_chunk_pages_keep_schema_scope(source: TimescaleSource) -> None:
    adapter = source.adapter(user="fixture_reader")
    for report in REPORTS:
        result = await adapter.fetch(FetchRequest(node_id=report.node_id, limit=2))
        assert result.rows, report.key
        assert not result.update_supported
    chunks = next(report for report in REPORTS if report.key.endswith(".chunks"))
    filters = [
        ScalarFilter(column="hypertable_schema", op="eq", value="lab"),
        ScalarFilter(column="hypertable_name", op="eq", value="metrics"),
    ]
    first = await adapter.fetch(FetchRequest(node_id=chunks.node_id, filters=filters, limit=1))
    second = await adapter.fetch(FetchRequest(node_id=chunks.node_id, filters=filters, limit=1, offset=1))
    assert len(first.rows) == len(second.rows) == 1
    assert first.has_more and second.has_more
    assert first.rows != second.rows
    names = [column.name for column in first.columns]
    assert first.rows[0][names.index("hypertable_schema")] == "lab"
    other = await adapter.fetch(FetchRequest(
        node_id=chunks.node_id,
        filters=[
            ScalarFilter(column="hypertable_schema", op="eq", value="other"),
            ScalarFilter(column="hypertable_name", op="eq", value="metrics"),
        ],
        limit=100,
    ))
    assert len(other.rows) == 2 and not other.has_more
    assert all(row[names.index("hypertable_schema")] == "other" for row in other.rows)


async def test_statistics_use_public_functions_and_preserve_partial_permission_failure(
    source: TimescaleSource,
) -> None:
    full = await source.adapter(user="fixture_reader").node_summary("lab.metrics")
    assert full.contents is not None and full.contents.kind == "relation"
    statistics = full.contents.timescale_statistics
    assert statistics is not None and statistics.size.kind == "size"
    assert statistics.size.total_bytes is not None
    assert int(statistics.size.total_bytes) > 0
    assert statistics.compression.kind == "compression"
    assert statistics.compression.number_compressed_chunks == "1"
    limited = await source.adapter(user="fixture_no_stats").node_summary("lab.metrics")
    assert limited.contents is not None and limited.contents.kind == "relation"
    assert limited.contents.timescale is not None and limited.contents.timescale.kind == "hypertable"
    refused = limited.contents.timescale_statistics
    assert refused is not None and refused.size.kind == refused.compression.kind == "unavailable"
    assert limited.related_views == full.related_views
    assert "fixture-only" not in limited.model_dump_json()


async def test_missing_metadata_permission_is_not_absence(source: TimescaleSource) -> None:
    feature = (await source.adapter(user="fixture_no_metadata").source_features()).features[0]
    assert feature.state == "unavailable"
    assert feature.installed_version == source.version
    assert feature.reason and "fixture-only" not in feature.reason


async def test_recorded_policy_run_has_public_statistics(source: TimescaleSource) -> None:
    session = source.session()
    jobs = await session.query(
        "SELECT job_id FROM timescaledb_information.jobs "
        "WHERE hypertable_schema = 'lab' AND hypertable_name = 'metrics' "
        "AND proc_name = 'policy_retention'",
    )
    assert len(jobs) == 1
    job_id = jobs[0]["job_id"]
    try:
        await session.query(
            "SELECT alter_job(%s, scheduled => true, next_start => now())", (job_id,),
        )
        async with asyncio.timeout(30):
            for _ in range(120):
                if await session.query(
                    "SELECT job_id FROM timescaledb_information.job_stats "
                    "WHERE job_id = %s AND total_successes > 0", (job_id,),
                ):
                    break
                await asyncio.sleep(0.25)
            else:
                pytest.fail("The fixture policy did not record a successful run")
    finally:
        await session.query("SELECT alter_job(%s, scheduled => false)", (job_id,))
    report = next(report for report in REPORTS if report.public_view == "job_stats")
    result = await source.adapter(user="fixture_reader").fetch(FetchRequest(
        node_id=report.node_id,
        filters=[
            ScalarFilter(column="hypertable_schema", op="eq", value="lab"),
            ScalarFilter(column="hypertable_name", op="eq", value="metrics"),
        ],
    ))
    assert len(result.rows) == 1
    row = dict(zip((column.name for column in result.columns), result.rows[0], strict=True))
    assert row["job_status"] == "Paused"
    assert row["last_run_status"] == "Success"
    assert row["total_runs"] is not None and int(row["total_runs"]) >= 1
    assert row["total_successes"] is not None and int(row["total_successes"]) >= 1
    assert row["total_failures"] == "0"
    assert row["next_start"] is None
