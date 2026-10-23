"""Every row of a MySQL page, streamed as the page reads it (D45)."""

from collections.abc import AsyncIterator

import pytest

from app.adapters.export import ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest, ScalarFilter, Sort
from app.adapters.mysql import ids
from app.adapters.mysql.reports import SECTION_ID
from tests.adapters.mysql_fixture import DATABASE, TARGETS, Target, build, tear_down

ITEMS = ids.relation_id(DATABASE, "items")


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    yield chosen
    await tear_down(chosen)


async def _rows(batches: AsyncIterator[ExportBatch]) -> list[list[str | None]]:
    return [row async for batch in batches for row in batch.rows]


async def test_an_export_is_the_page_s_rows_without_the_page(target: Target) -> None:
    adapter = target.adapter()
    sort = [Sort(column="label", descending=True)]

    exported = await _rows(
        adapter.export_rows(ExportRequest(node_id=ITEMS, columns=["label", "amount"], sort=sort))
    )
    page = await adapter.fetch(FetchRequest(node_id=ITEMS, limit=10, sort=sort))

    assert exported == [[row[1], row[3]] for row in page.rows]
    assert exported[0] == ["under_score", "1.0000000000"]


async def test_an_export_keeps_the_filter(target: Target) -> None:
    exported = await _rows(
        target.adapter().export_rows(
            ExportRequest(
                node_id=ITEMS,
                columns=["label"],
                filters=[ScalarFilter(column="label", op="contains", value="%")],
            )
        )
    )

    assert exported == [["50% off"]]


async def test_an_unknown_column_is_refused_before_anything_runs(target: Target) -> None:
    with pytest.raises(ValueError, match="Unknown export column"):
        await _rows(
            target.adapter().export_rows(ExportRequest(node_id=ITEMS, columns=["label", "nope"]))
        )


async def test_a_report_exports_like_a_page(target: Target) -> None:
    exported = await _rows(
        target.adapter().export_rows(
            ExportRequest(node_id=f"{SECTION_ID}/engines", columns=["engine"])
        )
    )

    engines = [str(row[0]) for row in exported]
    assert "InnoDB" in engines
    # Ordered by the server's collation, which ignores case.
    assert engines == sorted(engines, key=str.casefold)
