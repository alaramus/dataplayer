"""Rows past one request's ceiling, carried as a job a block at a time (D43, D166)."""

import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest

from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.connectors import imports
from app.connectors.paste.models import PasteColumn, PasteRun
from app.connectors.paste.rows import RowsIntoRelation, RowsNewRelation
from app.connectors.paste.transfer import Transfer, TransferStopped
from app.transfers.run import as_job
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import run

SCHEMA = "rows_job_test"
MANY = 12_345


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    await run(
        f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE; CREATE SCHEMA {SCHEMA};"  # noqa: S608 -- fixed test schema.
        f"CREATE TABLE {SCHEMA}.many AS SELECT n AS id, 'row ' || n AS label"
        f"  FROM generate_series(1, {MANY}) AS n;"
        f"CREATE TABLE {SCHEMA}.few AS SELECT n AS id FROM generate_series(1, 10) AS n;"
        f"CREATE TABLE {SCHEMA}.target (id integer, label text);"
        f"CREATE TABLE {SCHEMA}.picky (id integer CHECK (id < 7000), label text)"
    )
    yield SCHEMA
    await run(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")


class Report:
    """Counts what a kind reports, and nothing else."""

    def __init__(self) -> None:
        self.progressed_times = 0

    async def in_thread[T](self, work: Callable[[], T]) -> T:
        return work()

    async def progressed(self) -> None:
        self.progressed_times += 1

    async def removing(self) -> None:
        return None


def _transfer(kind: Any, **extra: Any) -> Transfer:
    return Transfer(
        kind=kind.name,
        title="t",
        doing="d",
        done="done",
        mode="copy",
        conflict="refuse",
        source_connector_id=uuid.uuid4(),
        source_label="s",
        destination_connector_id=uuid.uuid4(),
        destination_label="d",
        place_label="p",
        **extra,
    )


async def _count(table: str) -> int:
    page = await _adapter().fetch(
        imports.FetchRequest(node_id=f"{SCHEMA}.{table}", limit=1)
    )
    return page.total or 0


async def test_more_rows_than_one_request_carries_is_a_job(schema: str) -> None:
    source = _adapter()
    kind = RowsIntoRelation()

    def request(node: str) -> PasteRun:
        return PasteRun(
            kind=kind.name, mode="copy", source_connector_id=uuid.uuid4(), source_node_ids=[f"{schema}.{node}"],
            target_node_id=f"{schema}.target", columns=[PasteColumn(source="id", target="id")],
        )

    assert await as_job(kind, source, request("many")) is True
    assert await as_job(kind, source, request("few")) is False


async def test_every_row_arrives_into_a_table_a_block_at_a_time(schema: str) -> None:
    kind = RowsIntoRelation()
    transfer = _transfer(
        kind,
        items=[{"node_id": f"{schema}.many", "name": "target"}],
        columns=[PasteColumn(source="id", target="id"), PasteColumn(source="label", target="label")],
        target_node_id=f"{schema}.target",
    )
    report = Report()

    await kind.transfer(_adapter(), _adapter(), transfer, report)

    assert transfer.items[0].outcome == "done"
    assert transfer.items[0].rows == MANY
    assert report.progressed_times >= 3
    rows = await _adapter().fetch(imports.FetchRequest(node_id=f"{schema}.target", limit=1, offset=MANY - 1))
    assert len(rows.rows) == 1
    assert "12345" in kind.told(transfer)


async def test_a_refused_block_stops_it_and_what_arrived_stays(schema: str) -> None:
    kind = RowsIntoRelation()
    transfer = _transfer(
        kind,
        items=[{"node_id": f"{schema}.many", "name": "picky"}],
        columns=[PasteColumn(source="id", target="id")],
        target_node_id=f"{schema}.picky",
    )

    with pytest.raises(TransferStopped):
        await kind.transfer(_adapter(), _adapter(), transfer, Report())

    # The first block of 5000 arrived; the second broke the check.
    assert transfer.items[0].outcome == "failed"
    assert transfer.items[0].rows == imports.IMPORT_CEILING
    left = await _adapter().fetch(
        imports.FetchRequest(node_id=f"{schema}.picky", limit=1, offset=imports.IMPORT_CEILING - 1)
    )
    assert len(left.rows) == 1


async def test_a_new_table_is_made_and_filled(schema: str) -> None:
    kind = RowsNewRelation()
    transfer = _transfer(
        kind,
        items=[{"node_id": f"{schema}.many", "name": "copied"}],
        name="copied",
        destination_node_id=schema,
        columns=[PasteColumn(source="id", target="id", type_code="integer")],
    )

    await kind.transfer(_adapter(), _adapter(), transfer, Report())

    item = transfer.items[0]
    assert item.outcome == "done" and item.rows == MANY
    assert item.published_id == f"{schema}.copied"


async def test_a_new_table_that_cannot_be_filled_is_taken_back(schema: str) -> None:
    kind = RowsNewRelation()
    transfer = _transfer(
        kind,
        items=[{"node_id": f"{schema}.many", "name": "half"}],
        name="half",
        destination_node_id=schema,
        # "row 1" is no integer: refused in the first block.
        columns=[PasteColumn(source="label", target="n", type_code="integer")],
    )

    with pytest.raises(TransferStopped):
        await kind.transfer(_adapter(), _adapter(), transfer, Report())

    names = [node.name for node in await _adapter().list_children(schema)]
    assert "half" not in names
