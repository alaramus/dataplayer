"""A table pasted into a folder as a CSV file (D165, D168)."""

import asyncio
import shutil
import uuid
from pathlib import Path

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.export import ExportRequest
from app.adapters.file.storage import LocalStorage
from app.connectors import downloads
from app.connectors.paste import relation_csv
from app.connectors.paste.models import PastePair, PasteRun
from app.connectors.paste.relation_csv import RelationCsv
from app.connectors.paste.transfer import Transfer, TransferStopped
from tests.utils.paste_sources import Explorer, Table
from tests.utils.transfers import Recorder, planned, transferred


@pytest.fixture
def folder(tmp_path: Path) -> tuple[Explorer, Path]:
    (tmp_path / "incoming").mkdir()
    return Explorer(LocalStorage(tmp_path)), tmp_path / "incoming"


def pair(**changes: object) -> PastePair:
    return PastePair.model_validate(
        {
            "source_connector_id": str(uuid.uuid4()),
            "source_node_ids": ["public.people"],
            "destination_node_id": "incoming",
            "mode": "copy",
            **changes,
        }
    )


def run(**changes: object) -> PasteRun:
    return PasteRun.model_validate(
        {**pair().model_dump(mode="json"), "kind": "relation_csv", **changes}
    )


async def test_the_offer_suggests_a_name_and_says_it_converts(
    folder: tuple[Explorer, Path],
) -> None:
    destination, incoming = folder

    fresh = await RelationCsv().offer(Table(), destination, pair())
    (incoming / "people.csv").write_bytes(b"old")
    taken = await RelationCsv().offer(Table(), destination, pair())

    assert fresh.available and fresh.converts and fresh.can_replace
    assert fresh.suggested_name == "people.csv"
    assert not fresh.name_conflict
    assert taken.available and taken.name_conflict


async def test_the_offer_names_what_cannot_be_saved(
    folder: tuple[Explorer, Path],
) -> None:
    destination, incoming = folder
    (incoming / "note.txt").write_bytes(b"not a folder")
    kind = RelationCsv()

    two = await kind.offer(
        Table(), destination, pair(source_node_ids=["public.people", "public.other"])
    )
    gone = await kind.offer(Table(), destination, pair(source_node_ids=["public.gone"]))
    into_file = await kind.offer(
        Table(), destination, pair(destination_node_id="incoming/note.txt")
    )

    assert two.reason == "Copy one table at a time"
    assert gone.reason == "The copied table no longer exists"
    assert into_file.reason == "Choose a destination folder"
    assert not any(offer.available for offer in (two, gone, into_file))


async def test_only_a_relation_can_be_put_on_the_clipboard() -> None:
    kind = RelationCsv()

    table = await kind.supply(Table(), ["public.people"])
    schema = await kind.supply(Table(), ["public"])
    both = await kind.supply(Table(), ["public.people", "public.people"])

    assert table.available
    assert schema.reason == "Copy a table or a view"
    assert both.reason == "Copy one table at a time"


async def test_the_file_holds_the_same_bytes_as_the_download(
    folder: tuple[Explorer, Path],
) -> None:
    destination, incoming = folder

    done = await transferred(RelationCsv(), Table(), destination, run())

    downloaded, row_count = await downloads.stream_csv_export(
        title="people",
        columns=["id", "name"],
        batches=Table().export_rows(
            ExportRequest(node_id="public.people", columns=["id", "name"])
        ),
    )
    try:
        assert (incoming / "people.csv").read_bytes() == downloaded.read_bytes()
    finally:
        shutil.rmtree(downloaded.parent)
    assert row_count == 3
    [item] = done.items
    assert (item.outcome, item.rows, item.published_as) == ("done", 3, "people.csv")
    # No total is known before the rows are read, so none is claimed.
    assert done.bytes_total is None
    assert done.bytes_done == (incoming / "people.csv").stat().st_size
    assert RelationCsv().told(done) == "people.csv saved in incoming with 3 rows"


async def test_a_typed_name_ends_in_csv(folder: tuple[Explorer, Path]) -> None:
    destination, incoming = folder
    kind = RelationCsv()

    await transferred(kind, Table(), destination, run(name="export"))
    await transferred(kind, Table(), destination, run(name="export.tsv"))
    await transferred(kind, Table(), destination, run(name="Report.CSV"))
    with pytest.raises(ActionRefused, match="plain name"):
        await kind.plan(Table(), destination, run(name="../escape"))

    assert sorted(path.name for path in incoming.iterdir()) == [
        "Report.CSV",
        "export.csv",
        "export.tsv.csv",
    ]


async def test_a_taken_name_is_refused_kept_or_replaced(
    folder: tuple[Explorer, Path],
) -> None:
    destination, incoming = folder
    existing = incoming / "people.csv"
    existing.write_bytes(b"old")
    kind = RelationCsv()

    # Refused before anything starts, so Paste can ask what to do.
    with pytest.raises(ActionRefused, match="already there") as refused:
        await kind.plan(Table(), destination, run())
    assert refused.value.reason == "conflict"
    assert existing.read_bytes() == b"old"

    kept = await transferred(kind, Table(), destination, run(conflict="rename"))
    assert kept.items[0].published_as == "people (1).csv"
    assert existing.read_bytes() == b"old"

    await transferred(kind, Table(), destination, run(conflict="replace"))
    assert existing.read_bytes() == (incoming / "people (1).csv").read_bytes()


async def test_the_ceiling_publishes_nothing_and_closes_the_stream(
    folder: tuple[Explorer, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination, incoming = folder
    monkeypatch.setattr(relation_csv, "MAX_TRANSFER_BYTES", 20)
    table = Table()

    done = await transferred(RelationCsv(), table, destination, run())

    [item] = done.items
    assert (item.outcome, item.message) == ("failed", "The table exceeds 10 GB as CSV")
    assert list(incoming.iterdir()) == []
    assert table.closed
    assert RelationCsv().told(done) == (
        "people.csv was not saved: The table exceeds 10 GB as CSV"
    )


async def test_a_source_failing_halfway_leaves_no_file(
    folder: tuple[Explorer, Path],
) -> None:
    destination, incoming = folder

    with pytest.raises(TransferStopped, match="The source went away"):
        await transferred(RelationCsv(), Table(fail_at_batch=1), destination, run())

    assert list(incoming.iterdir()) == []


async def test_stop_while_writing_leaves_no_file_and_closes_the_stream(
    folder: tuple[Explorer, Path],
) -> None:
    destination, incoming = folder
    table = Table()
    prepared = await planned(RelationCsv(), table, destination, run())
    writing = asyncio.Event()

    async def after_a_piece(done: Transfer) -> None:
        # After the first rows rather than the header: the source's stream is
        # open by then, and a Stop must close it.
        if done.items[0].rows:
            writing.set()
            await asyncio.sleep(10)

    recorder = Recorder(on_progress=after_a_piece)
    recorder.transfer = prepared
    task = asyncio.create_task(RelationCsv().transfer(table, destination, prepared, recorder))
    await asyncio.wait_for(writing.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert prepared.items[0].outcome == "stopped"
    assert list(incoming.iterdir()) == []
    assert table.closed
