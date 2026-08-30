import pytest
from pydantic import ValidationError

from app.adapters.export import EXPORT_BATCH_SIZE, ExportBatch, ExportRequest


def test_export_has_no_page_limit_or_offset() -> None:
    request = ExportRequest(
        node_id="public.projects",
        columns=["name"],
        filters=[],
        sort=[],
    )

    assert "limit" not in request.model_fields_set
    assert "offset" not in request.model_fields_set


def test_export_columns_must_be_distinct() -> None:
    with pytest.raises(ValidationError, match="unique"):
        ExportRequest(node_id="public.projects", columns=["name", "name"])


def test_export_batch_has_a_hard_row_bound() -> None:
    with pytest.raises(ValidationError):
        ExportBatch(rows=[["row"] for _ in range(EXPORT_BATCH_SIZE + 1)])
