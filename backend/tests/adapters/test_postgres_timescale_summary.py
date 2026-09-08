from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.adapters.postgres.summary import PostgresSummaries
from app.adapters.postgres.timescale.reports import BY_ID, TIMESCALE_SECTION_ID
from app.adapters.postgres.timescale.summary import related_views
from app.adapters.relation import RelationModel
from app.adapters.specializations import TimescaleContinuousAggregate, TimescaleHypertable
from app.adapters.summary import NodeSummary, RelatedView
from app.adapters.timescale_metadata import (
    HypertableFacts,
    TimescaleSize,
    TimescaleStatistics,
    UnavailableTimescaleFacts,
)


def model() -> RelationModel:
    return RelationModel(
        node_id="odd.schema.table'name", schema_name="odd.schema", name="table'name",
        kind="table", specialization=TimescaleHypertable(),
    )


async def test_summary_links_survive_unavailable_optional_metadata() -> None:
    relation = AsyncMock()
    relation.relation_model.return_value = model()
    session = AsyncMock()
    session.query.return_value = []
    summary = await PostgresSummaries(session, relation).node_summary(model().node_id)
    assert [view.node.name for view in summary.related_views] == [
        "Chunks", "Dimensions", "Policies and jobs",
    ]
    for view in summary.related_views:
        assert view.node.id in BY_ID
        assert view.node.has_children is False
        assert view.node.describable is False
        assert [filter_.model_dump() for filter_ in view.filters] == [
            {"column": "hypertable_schema", "op": "eq", "value": "odd.schema"},
            {"column": "hypertable_name", "op": "eq", "value": "table'name"},
        ]
    session.query.assert_awaited_once()
    assert summary.size_bytes is None
    assert summary.contents is not None and summary.contents.kind == "relation"
    assert summary.contents.timescale is not None
    assert summary.contents.timescale.kind == "unavailable"
    assert summary.contents.analyzed_at is None


async def test_summary_includes_optional_statistics_without_replacing_other_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = HypertableFacts(num_dimensions=1, num_chunks="2", compression_enabled=True)
    statistics = TimescaleStatistics(
        size=TimescaleSize(table_bytes="1024", index_bytes="0", toast_bytes="0", total_bytes="1024"),
        compression=UnavailableTimescaleFacts(reason="Statistics unavailable"),
    )
    monkeypatch.setattr("app.adapters.postgres.summary.inspect_details", AsyncMock(return_value=facts))
    inspect = AsyncMock(return_value=statistics)
    monkeypatch.setattr("app.adapters.postgres.summary.inspect_statistics", inspect)
    relation = AsyncMock()
    relation.relation_model.return_value = model()
    session = AsyncMock()
    summary = await PostgresSummaries(session, relation).node_summary(model().node_id)
    assert summary.contents is not None and summary.contents.kind == "relation"
    assert summary.contents.timescale == facts
    assert summary.contents.timescale_statistics == statistics
    assert len(summary.related_views) == 3
    inspect.assert_awaited_once_with(session, model(), facts)
    session.query.assert_not_awaited()


def test_aggregate_link_filters_the_logical_view_not_a_guessed_materialization() -> None:
    aggregate = model().model_copy(update={
        "kind": "view", "specialization": TimescaleContinuousAggregate(),
    })
    views = related_views(aggregate)
    assert len(views) == 1
    assert views[0].node.id == f"{TIMESCALE_SECTION_ID}.continuous_aggregates"
    assert [filter_.column for filter_ in views[0].filters] == ["view_schema", "view_name"]


def test_ordinary_and_older_summaries_have_no_related_reports() -> None:
    assert related_views(model().model_copy(update={"specialization": None})) == []
    assert NodeSummary(node_id="notes", name="notes", kind="file").related_views == []


def test_related_view_rejects_sql_fragments_and_excessive_filters() -> None:
    view = related_views(model())[0]
    with pytest.raises(ValidationError):
        RelatedView.model_validate({
            "node": view.node, "filters": [{"column": "x", "op": "sql", "value": "1=1"}],
        })
    with pytest.raises(ValidationError):
        RelatedView(node=view.node, filters=view.filters * 9)
