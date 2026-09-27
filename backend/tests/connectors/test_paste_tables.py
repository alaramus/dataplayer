"""Tables pasted with their structure, and what their links bring (D182)."""

import uuid
from collections.abc import AsyncGenerator

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.fetch import FetchRequest
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.connectors.paste.models import PastePair, PasteRun, TablesChoice
from app.connectors.paste.registry import kind_named, open_kinds
from app.connectors.paste.tables import TablesCopy, TablesPreviewRequest, preview
from app.pipelines.models import Link
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import SCHEMA, make_schema, run
from tests.utils.transfers import transferred

PLACE = "paste_tables_test"
CUSTOMERS = f"{SCHEMA}.customers"
REGIONS = f"{SCHEMA}.regions"

ROWS = f"""
DROP SCHEMA IF EXISTS {PLACE} CASCADE;
CREATE SCHEMA {PLACE};
INSERT INTO {SCHEMA}.regions VALUES (1, 'north'), (2, 'south');
INSERT INTO {SCHEMA}.customers (region_id, region_code, name)
VALUES (1, 'north', 'Ann'), (2, 'south', 'Bob');
"""  # noqa: S608 -- module constants, never client input.


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        await run(ROWS)
        try:
            yield name
        finally:
            await run(f"DROP SCHEMA IF EXISTS {PLACE} CASCADE")


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


def _pair(ticked: list[str], choice: TablesChoice | None = None) -> TablesPreviewRequest:
    return TablesPreviewRequest(
        source_connector_id=uuid.uuid4(),
        source_node_ids=ticked,
        mode="copy",
        destination_node_id=PLACE,
        tables=choice or TablesChoice(),
    )


def _run(ticked: list[str], choice: TablesChoice | None = None) -> PasteRun:
    return PasteRun(
        source_connector_id=uuid.uuid4(),
        source_node_ids=ticked,
        mode="copy",
        destination_node_id=PLACE,
        kind="tables_copy",
        tables=choice,
    )


async def test_within_one_database_links_keep_their_originals(schema: str) -> None:
    del schema
    shown = await preview(_adapter(), _adapter(), _pair([CUSTOMERS]))

    assert shown.links == "keep" and shown.keep_allowed
    assert [(table.label, table.origin) for table in shown.tables] == [(CUSTOMERS, "ticked")]
    assert [(link.table, link.target) for link in shown.outside] == [(CUSTOMERS, REGIONS)]
    assert any(statement.title.startswith("Link") for statement in shown.statements)


async def test_copying_the_links_brings_the_tables_they_point_at(schema: str) -> None:
    del schema
    shown = await preview(
        _adapter(), _adapter(), _pair([CUSTOMERS], TablesChoice(links="copy"))
    )

    assert [(table.label, table.origin) for table in shown.tables] == [
        (CUSTOMERS, "ticked"),
        (REGIONS, "linked"),
    ]
    link = next(one for one in shown.statements if one.title.startswith("Link"))
    assert f'"{PLACE}"."regions"' in link.sql


async def test_dropped_links_bring_nothing_and_make_no_link(schema: str) -> None:
    del schema
    shown = await preview(
        _adapter(), _adapter(), _pair([CUSTOMERS], TablesChoice(links="drop"))
    )

    assert [table.label for table in shown.tables] == [CUSTOMERS]
    assert not any(statement.title.startswith("Link") for statement in shown.statements)


async def test_a_table_that_points_at_a_ticked_one_is_offered_and_joins_when_ticked(
    schema: str,
) -> None:
    del schema
    offered = await preview(_adapter(), _adapter(), _pair([REGIONS]))
    added = await preview(
        _adapter(), _adapter(), _pair([REGIONS], TablesChoice(also=[CUSTOMERS]))
    )

    assert [(one.label, one.chosen) for one in offered.pointing] == [(CUSTOMERS, False)]
    assert [(table.label, table.origin) for table in added.tables] == [
        (REGIONS, "ticked"),
        (CUSTOMERS, "added"),
    ]
    # Both are copied, so the link joins the copies.
    link = next(one for one in added.statements if one.title.startswith("Link"))
    assert f'"{PLACE}"."regions"' in link.sql


async def test_a_name_taken_in_the_place_is_offered_as_a_copy(schema: str) -> None:
    shown = await preview(
        _adapter(),
        _adapter(),
        _pair([REGIONS]).model_copy(update={"destination_node_id": schema}),
    )

    assert [table.name for table in shown.tables] == ["regions_copy"]
    assert shown.problems == []


async def test_the_copy_runs_as_one_transfer_and_says_what_arrived(schema: str) -> None:
    del schema
    kind = TablesCopy()

    done = await transferred(
        kind, _adapter(), _adapter(), _run([CUSTOMERS], TablesChoice(links="copy"))
    )

    assert [(item.name, item.outcome, item.rows) for item in done.items] == [
        (CUSTOMERS, "done", 2),
        (REGIONS, "done", 2),
    ]
    assert kind.told(done) == f"2 tables copied into {PLACE} with 4 rows"
    page = await _adapter().fetch(FetchRequest(node_id=f"{PLACE}.customers", limit=10))
    assert len(page.rows) == 2


async def test_a_refused_plan_is_refused_before_a_job_starts(schema: str) -> None:
    with pytest.raises(ActionRefused) as refused:
        await TablesCopy().plan(
            _adapter(),
            _adapter(),
            _run([REGIONS], TablesChoice(names={REGIONS: "regions"})).model_copy(
                update={"destination_node_id": schema}
            ),
        )

    assert refused.value.reason == "conflict"
    assert refused.value.message == f"{schema}.regions is already there"


async def test_the_offer_says_what_cannot_be_copied(schema: str) -> None:
    kind = TablesCopy()
    pair = PastePair(
        source_connector_id=uuid.uuid4(),
        source_node_ids=[f"{schema}.events"],
        mode="copy",
        destination_node_id=PLACE,
    )

    partitioned = await kind.offer(_adapter(), _adapter(), pair)
    nowhere = await kind.offer(
        _adapter(),
        _adapter(),
        pair.model_copy(update={"source_node_ids": [REGIONS], "destination_node_id": None}),
    )

    assert partitioned.reason == f"{schema}.events: partitioned tables are not copied yet"
    # The schema is chosen in the window, so none needs to be selected.
    assert nowhere.available


def test_a_copy_of_tables_is_not_something_a_pipeline_runs() -> None:
    adapter = _adapter()

    assert TablesCopy().serves(adapter, adapter)
    assert "tables_copy" not in [
        kind.name for kind in open_kinds(adapter, "own", adapter, "own")
    ]
    assert not kind_named("tables_copy").pipelines
    with pytest.raises(ValueError, match="run from the catalog"):
        Link.model_validate(
            {
                "id": str(uuid.uuid4()),
                "source": {"card_id": str(uuid.uuid4()), "node_id": "a.b"},
                "target": {"card_id": str(uuid.uuid4()), "node_id": "c"},
                "kind": "tables_copy",
                "title": "Copy tables",
            }
        )
