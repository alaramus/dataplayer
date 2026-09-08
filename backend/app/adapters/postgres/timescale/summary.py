"""Report navigation from an already classified relation (D121)."""

from app.adapters.fetch import ScalarFilter
from app.adapters.postgres.catalog import report_node
from app.adapters.postgres.timescale.reports import BY_ID, TIMESCALE_SECTION_ID
from app.adapters.relation import RelationModel
from app.adapters.summary import RelatedView


def related_views(model: RelationModel) -> list[RelatedView]:
    specialization = model.specialization
    if specialization is None or model.schema_name is None:
        return []
    if specialization.kind == "timescale_hypertable":
        keys: tuple[str, ...] = ("chunks", "dimensions", "jobs")
        schema_column, name_column = "hypertable_schema", "hypertable_name"
    else:
        keys = ("continuous_aggregates",)
        schema_column, name_column = "view_schema", "view_name"
    return [
        RelatedView(
            node=report_node(BY_ID[f"{TIMESCALE_SECTION_ID}.{key}"]),
            filters=[
                ScalarFilter(column=schema_column, op="eq", value=model.schema_name),
                ScalarFilter(column=name_column, op="eq", value=model.name),
            ],
        )
        for key in keys
    ]
