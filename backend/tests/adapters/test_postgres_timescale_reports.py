from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.adapters.content import ContentRequest
from app.adapters.features import FeatureState, SourceFeature
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.content import PostgresContent
from app.adapters.postgres.fetch import PostgresFetch
from app.adapters.postgres.metadata import PostgresGeneration, PostgresMetadata
from app.adapters.postgres.report_registry import resolve_report
from app.adapters.postgres.system_reports import SECTION_ID, SystemReport
from app.adapters.postgres.timescale.profile import TimescaleProfile
from app.adapters.postgres.timescale.reports import REPORTS, TIMESCALE_SECTION_ID
from app.adapters.protocol import NodeNotFound
from app.adapters.query import GenerateQueryRequest


def discovery(monkeypatch: pytest.MonkeyPatch, state: FeatureState) -> AsyncMock:
    probe = AsyncMock(return_value=TimescaleProfile(SourceFeature(
        code="timescaledb", title="TimescaleDB", state=state,
        installed_version=None if state == "absent" else "2.18.0",
        reason=None if state in {"available", "absent"} else "Inspection refused",
    )))
    monkeypatch.setattr("app.adapters.postgres.report_registry.discover", probe)
    monkeypatch.setattr("app.adapters.postgres.catalog.discover", probe)
    monkeypatch.setattr(
        "app.adapters.postgres.report_registry.require_report", AsyncMock(),
    )
    return probe


async def test_discovered_section_and_report_paths_agree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery(monkeypatch, "available")
    session = AsyncMock()
    catalog = PostgresCatalog(session)
    system = await catalog.list_children(SECTION_ID)
    assert system[-1].id == TIMESCALE_SECTION_ID
    reports = await catalog.list_children(TIMESCALE_SECTION_ID)
    assert [node.id for node in reports] == [report.node_id for report in REPORTS]
    for report in reports:
        path = await catalog.path_to(report.id)
        assert [node.id for node in path] == [
            SECTION_ID, TIMESCALE_SECTION_ID, report.id,
        ]
        assert path[-1] == report
        assert await catalog.list_children(report.id) == []
    session.query.assert_not_awaited()


@pytest.mark.parametrize("state", ["absent", "unavailable", "unsupported"])
async def test_missing_or_unusable_extension_hides_section_and_refuses_direct_reads(
    monkeypatch: pytest.MonkeyPatch, state: FeatureState,
) -> None:
    discovery(monkeypatch, state)
    session = AsyncMock()
    catalog = PostgresCatalog(session)
    assert TIMESCALE_SECTION_ID not in {
        node.id for node in await catalog.list_children(SECTION_ID)
    }
    error = NodeNotFound if state == "absent" else ValueError
    node_id = REPORTS[0].node_id
    with pytest.raises(error):
        await catalog.path_to(node_id)
    with pytest.raises(error):
        await catalog.list_children(TIMESCALE_SECTION_ID)
    with pytest.raises(error):
        await PostgresFetch(session).prepare(FetchRequest(node_id=node_id))
    with pytest.raises(error):
        await PostgresContent(session).read_content(ContentRequest(
            node_id=node_id, representation="sql",
        ))
    with pytest.raises(error):
        await PostgresGeneration(session, PostgresMetadata(session)).generate(
            GenerateQueryRequest(node_id=node_id, kind="select")
        )
    session.query.assert_not_awaited()
    session.describe.assert_not_awaited()


async def test_unknown_report_is_not_a_source_relation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = discovery(monkeypatch, "available")
    with pytest.raises(NodeNotFound):
        await resolve_report(AsyncMock(), f"{TIMESCALE_SECTION_ID}.forged")
    probe.assert_not_awaited()


@pytest.mark.parametrize("report", REPORTS, ids=lambda report: report.key)
async def test_sql_surfaces_use_the_registered_report(
    monkeypatch: pytest.MonkeyPatch, report: SystemReport,
) -> None:
    discovery(monkeypatch, "available")
    session = AsyncMock()
    content = await PostgresContent(session).read_content(ContentRequest(
        node_id=report.node_id, representation="sql",
    ))
    generated = await PostgresGeneration(session, PostgresMetadata(session)).generate(
        GenerateQueryRequest(node_id=report.node_id, kind="select")
    )
    assert "timescaledb_information." in generated.text.replace('"', "")
    assert content.kind == "sql"
    assert content.text == generated.text
    with pytest.raises(ValueError, match="report"):
        await PostgresGeneration(session, PostgresMetadata(session)).generate(
            GenerateQueryRequest(node_id=report.node_id, kind="name")
        )
    session.query.assert_not_awaited()


@pytest.mark.parametrize("report", REPORTS, ids=lambda report: report.key)
async def test_report_page_and_export_keep_outer_identity_order(
    monkeypatch: pytest.MonkeyPatch, report: SystemReport,
) -> None:
    discovery(monkeypatch, "available")
    session = AsyncMock()
    columns = list(report.stable_order)
    session.describe.return_value = [(name, 25) for name in columns]
    session.query.return_value = [{
        "oid": 25, "sql_type": "text", "type_name": "text",
        "type_category": "S", "element_sql": None, "element_name": None,
        "element_category": None,
    }]
    fetch = PostgresFetch(session)
    request = FetchRequest(
        node_id=report.node_id, limit=7, offset=14,
        sort=[Sort(column=columns[-1], descending=True)],
        filters=[ScalarFilter(column=columns[0], op="eq", value="a'; DROP TABLE x")],
    )
    prepared = await fetch.prepare(request)
    statement, params = fetch._build(
        prepared.source, prepared.info.columns, prepared.request, prepared.info,
    )
    outer_order = f'ORDER BY "{columns[-1]}" DESC, ' + ", ".join(
        f'"{column}" ASC' for column in columns
    )
    assert statement.as_string().endswith(f"{outer_order} LIMIT %s OFFSET %s")
    assert params == ["a'; DROP TABLE x", 8, 14]
    exported, export_params, _ = fetch.build_export(prepared, [columns[-1]])
    assert exported.as_string().endswith(outer_order)
    assert export_params == ["a'; DROP TABLE x"]
    assert "DROP TABLE" not in statement.as_string()
    assert "ctid" not in statement.as_string()
    assert "xmin" not in statement.as_string()
    assert prepared.info.row_identity == "none"
    assert not prepared.info.update_supported
    assert not prepared.info.insert_supported
    assert not prepared.info.delete_supported
    with pytest.raises(ValueError, match="Unknown"):
        await fetch.prepare(FetchRequest(
            node_id=report.node_id, sort=[Sort(column="forged")],
        ))


async def test_chunk_boundaries_keep_integer_precision_and_distinct_time_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery(monkeypatch, "available")
    report = next(report for report in REPORTS if report.key.endswith(".chunks"))
    session = AsyncMock()
    session.describe.return_value = [
        ("chunk_schema", 25), ("chunk_name", 25),
        ("range_start_integer", 20), ("range_end_integer", 20),
        ("range_start", 1184), ("range_end", 1184),
    ]
    exact = 9007199254740993
    start = datetime(2026, 9, 8, tzinfo=UTC)
    type_rows = [
            {"oid": 25, "sql_type": "text", "type_name": "text", "type_category": "S"},
            {"oid": 20, "sql_type": "bigint", "type_name": "int8", "type_category": "N"},
            {"oid": 1184, "sql_type": "timestamp with time zone",
             "type_name": "timestamptz", "type_category": "D"},
    ]
    session.query.side_effect = [
        type_rows,
        [
            {"chunk_schema": "a", "chunk_name": "same",
             "range_start_integer": exact, "range_end_integer": exact + 10,
             "range_start": None, "range_end": None},
            {"chunk_schema": "b", "chunk_name": "same",
             "range_start_integer": None, "range_end_integer": None,
             "range_start": start, "range_end": start},
        ],
    ]
    fetch = PostgresFetch(session)
    result = await fetch.fetch(FetchRequest(
        node_id=report.node_id, limit=2,
        sort=[Sort(column="range_start_integer")],
    ))
    assert result.rows == [
        ["a", "same", str(exact), str(exact + 10), None, None],
        ["b", "same", None, None, start.isoformat(), start.isoformat()],
    ]
    statement, params = session.query.await_args.args
    assert params == (3, 0)
    assert '"range_start_integer"::text' not in statement
    assert statement.endswith(
        'ORDER BY "range_start_integer" ASC, "chunk_schema" ASC, "chunk_name" ASC '
        'LIMIT %s OFFSET %s'
    )
    assert result.row_handles == [None, None]
    session.query.side_effect = [type_rows]
    prepared = await fetch.prepare(FetchRequest(
        node_id=report.node_id, limit=2,
        filters=[ScalarFilter(column="range_start_integer", op="gte", value=str(exact))],
    ))
    _, filter_params = fetch._build(
        prepared.source, prepared.info.columns, prepared.request, prepared.info,
    )
    assert filter_params == [Decimal(exact), 3, 0]
