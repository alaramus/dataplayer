"""The reports a PostgreSQL connection publishes about itself (D55)."""

import pytest

from app.adapters.catalog import ReportNode
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.system_reports import (
    REPORTS,
    SECTION_ID,
    SystemReport,
)
from app.adapters.protocol import NodeNotFound
from tests.utils.database import working_postgres_options


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


async def test_the_root_offers_the_section_beside_the_schemas() -> None:
    nodes = await _adapter().list_children(None)

    section = next(node for node in nodes if node.id == SECTION_ID)
    assert isinstance(section, ReportNode)
    assert section.has_children is True
    assert section.representations == []
    assert section.description is not None
    # Beside the schemas, not instead of them.
    assert any(node.kind == "schema" for node in nodes)


async def test_the_section_lists_every_registered_report() -> None:
    nodes = await _adapter().list_children(SECTION_ID)

    assert [node.id for node in nodes] == [report.node_id for report in REPORTS]
    for node in nodes:
        assert isinstance(node, ReportNode)
        assert node.has_children is False
        assert [item.kind for item in node.representations] == ["table"]
        # A report is not a relation and answers no relation model.
        assert node.describable is False


async def test_a_report_says_where_it_lives() -> None:
    path = await _adapter().path_to(REPORTS[0].node_id)

    assert [node.id for node in path] == [SECTION_ID, REPORTS[0].node_id]


async def test_an_id_in_the_section_naming_no_report_is_gone() -> None:
    with pytest.raises(NodeNotFound):
        await _adapter().path_to(f"{SECTION_ID}.not_a_report")


@pytest.mark.parametrize("report", REPORTS, ids=lambda report: report.key)
async def test_every_report_reads(report: SystemReport) -> None:
    """Each statement runs, describes its columns and returns rows.

    Parameterised over the registry rather than written out, so a report added
    without a working statement fails here rather than when someone opens it.
    """
    result = await _adapter().fetch(FetchRequest(node_id=report.node_id, limit=5))

    assert result.columns
    assert result.rows
    assert all(len(row) == len(result.columns) for row in result.rows)


async def test_a_report_is_read_only_and_names_no_row() -> None:
    result = await _adapter().fetch(
        FetchRequest(node_id=f"{SECTION_ID}.settings", limit=5)
    )

    assert result.update_supported is False
    assert result.insert_supported is False
    assert result.delete_supported is False
    assert all(handle is None for handle in result.row_handles)
    assert not any(column.editable for column in result.columns)
    assert result.references == []


async def test_a_report_pages_sorts_and_filters_like_a_relation() -> None:
    """pg_settings always holds hundreds of rows, so this is not vacuous."""
    adapter = _adapter()
    node_id = f"{SECTION_ID}.settings"

    first = await adapter.fetch(
        FetchRequest(node_id=node_id, limit=5, sort=[Sort(column="name")])
    )
    second = await adapter.fetch(
        FetchRequest(node_id=node_id, limit=5, offset=5, sort=[Sort(column="name")])
    )
    descending = await adapter.fetch(
        FetchRequest(
            node_id=node_id, limit=5, sort=[Sort(column="name", descending=True)]
        )
    )

    assert first.has_more is True
    assert first.rows != second.rows
    assert first.rows != descending.rows

    name_at = [column.name for column in first.columns].index("name")
    filtered = await adapter.fetch(
        FetchRequest(
            node_id=node_id,
            limit=5,
            filters=[ScalarFilter(column="name", op="eq", value="max_connections")],
        )
    )
    assert [row[name_at] for row in filtered.rows] == ["max_connections"]


async def test_a_report_computes_what_no_relation_holds() -> None:
    """The three that are a query rather than a relation are why D55 exists."""
    result = await _adapter().fetch(
        FetchRequest(node_id=f"{SECTION_ID}.tablespaces", limit=10)
    )

    names = [column.name for column in result.columns]
    assert "size_bytes" in names
    assert "objects" in names
    values = {row[names.index("name")] for row in result.rows}
    assert "pg_default" in values


async def test_a_column_a_report_does_not_have_is_refused() -> None:
    """The identifier is checked against what the server described."""
    with pytest.raises(ValueError, match="nonsense"):
        await _adapter().fetch(
            FetchRequest(
                node_id=f"{SECTION_ID}.roles",
                limit=5,
                sort=[Sort(column="nonsense")],
            )
        )


async def test_a_report_id_naming_no_report_is_not_read_as_a_relation() -> None:
    with pytest.raises(ValueError, match="report"):
        await _adapter().fetch(FetchRequest(node_id=f"{SECTION_ID}.nope", limit=5))
