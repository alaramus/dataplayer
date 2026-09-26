"""Tables pasted into a folder as CSV files, one each (D165, D168, D171)."""

import asyncio
import shutil
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import redis.asyncio as redis

from app.adapters.actions import ActionRefused
from app.adapters.export import ExportRequest
from app.adapters.file.storage import LocalStorage
from app.adapters.redis import export as redis_export
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.keyspace import folder_id, key_id
from app.connectors import downloads
from app.connectors.paste import relation_csv
from app.connectors.paste.models import PastePair, PasteRun
from app.connectors.paste.relation_csv import RelationCsv
from app.connectors.paste.transfer import Transfer, TransferStopped
from tests.utils.keyspace import chosen_database, empty_keyspace, redis_options
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

    twice = await kind.offer(
        Table(), destination, pair(source_node_ids=["public.people", "public.people"])
    )
    gone = await kind.offer(
        Table(), destination, pair(source_node_ids=["public.people", "public.gone"])
    )
    into_file = await kind.offer(
        Table(), destination, pair(destination_node_id="incoming/note.txt")
    )

    assert twice.reason == "The selection contains a table twice"
    assert gone.reason == "The copied table no longer exists"
    assert into_file.reason == "Choose a destination folder"
    assert not any(offer.available for offer in (twice, gone, into_file))


async def test_only_a_relation_can_be_put_on_the_clipboard() -> None:
    kind = RelationCsv()

    table = await kind.supply(Table(), ["public.people"])
    several = await kind.supply(Table(), ["public.people", "public.pets"])
    schema = await kind.supply(Table(), ["public.people", "public"])
    too_many = await kind.supply(
        Table(), [f"public.t{number}" for number in range(relation_csv.MAX_TABLES + 1)]
    )

    assert table.available and several.available
    assert schema.reason == "Copy a table or a view"
    assert too_many.reason == "Save at most 100 tables at a time"


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
    prepared = await planned(RelationCsv(), table, destination, run())

    with pytest.raises(TransferStopped) as stopped:
        await RelationCsv().transfer(table, destination, prepared, Recorder())

    [item] = prepared.items
    assert (item.outcome, item.message) == (
        "failed",
        "people.csv was not saved: the tables exceed 10 GB as CSV",
    )
    assert list(incoming.iterdir()) == []
    assert table.closed
    assert RelationCsv().told(prepared, stopped.value.message) == (
        "people.csv was not saved: the tables exceed 10 GB as CSV"
    )


async def test_a_source_failing_halfway_leaves_no_file(
    folder: tuple[Explorer, Path],
) -> None:
    destination, incoming = folder

    done = await transferred(RelationCsv(), Table(fail_at_batch=1), destination, run())

    [item] = done.items
    assert (item.outcome, item.message) == (
        "failed",
        "people.csv was not saved: the source went away",
    )
    assert list(incoming.iterdir()) == []


# --- several at once (D171) -------------------------------------------------


async def test_several_are_one_transfer_and_one_file_each(
    folder: tuple[Explorer, Path],
) -> None:
    destination, incoming = folder
    request = run(source_node_ids=["public.people", "public.pets"])

    offer = await RelationCsv().offer(Table(), destination, pair(**{
        "source_node_ids": ["public.people", "public.pets"],
    }))
    done = await transferred(RelationCsv(), Table(), destination, request)

    # Named after each, so no window asks for a name.
    assert offer.available and offer.workflow == "run"
    assert offer.suggested_name is None
    assert done.name is None
    assert sorted(path.name for path in incoming.iterdir()) == ["people.csv", "pets.csv"]
    assert (incoming / "pets.csv").read_bytes() == (
        b'\xef\xbb\xbf"id","species"\r\n"1","cat"\r\n'
    )
    assert [(item.name, item.published_as, item.rows) for item in done.items] == [
        ("people", "people.csv", 3),
        ("pets", "pets.csv", 1),
    ]
    assert RelationCsv().told(done) == "2 files saved in incoming"


async def test_two_of_one_name_are_both_kept(folder: tuple[Explorer, Path]) -> None:
    destination, incoming = folder

    done = await transferred(
        RelationCsv(),
        Table(),
        destination,
        run(source_node_ids=["public.people", "sales.people"]),
    )

    assert [item.published_as for item in done.items] == ["people.csv", "people (1).csv"]
    assert sorted(path.name for path in incoming.iterdir()) == [
        "people (1).csv",
        "people.csv",
    ]


async def test_a_taken_name_asks_once_for_all_of_them(
    folder: tuple[Explorer, Path],
) -> None:
    destination, incoming = folder
    (incoming / "people.csv").write_bytes(b"old")
    both = ["public.people", "public.pets"]
    kind = RelationCsv()

    offer = await kind.offer(Table(), destination, pair(source_node_ids=both))
    with pytest.raises(ActionRefused, match="people.csv is already there"):
        await kind.plan(Table(), destination, run(source_node_ids=both))
    kept = await transferred(
        kind, Table(), destination, run(source_node_ids=both, conflict="rename")
    )

    assert (offer.available, offer.name_conflict, offer.can_replace) == (False, True, True)
    assert offer.reason == "people.csv is already there"
    assert [item.published_as for item in kept.items] == ["people (1).csv", "pets.csv"]
    assert (incoming / "people.csv").read_bytes() == b"old"


async def test_one_failing_does_not_stop_the_next(
    folder: tuple[Explorer, Path],
) -> None:
    destination, incoming = folder

    done = await transferred(
        RelationCsv(),
        Table(fail_at_batch=0, failing="public.people"),
        destination,
        run(source_node_ids=["public.people", "public.pets"]),
    )

    assert [item.outcome for item in done.items] == ["failed", "done"]
    assert [path.name for path in incoming.iterdir()] == ["pets.csv"]
    assert RelationCsv().told(done) == "1 of 2 files saved in incoming; 1 failed"


async def test_the_ceiling_is_for_all_of_them_together(
    folder: tuple[Explorer, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination, incoming = folder
    # people.csv alone is 52 bytes; the second file crosses the ceiling.
    monkeypatch.setattr(relation_csv, "MAX_TRANSFER_BYTES", 60)
    prepared = await planned(
        RelationCsv(),
        Table(),
        destination,
        run(source_node_ids=["public.people", "sales.people", "public.pets"]),
    )

    with pytest.raises(TransferStopped) as stopped:
        await RelationCsv().transfer(Table(), destination, prepared, Recorder())

    assert [item.outcome for item in prepared.items] == ["done", "failed", "pending"]
    assert [path.name for path in incoming.iterdir()] == ["people.csv"]
    assert RelationCsv().told(prepared, stopped.value.message) == (
        "1 of 3 files saved in incoming; 1 failed, 1 not attempted. "
        "The tables exceed 10 GB as CSV"
    )


# --- from Redis (D171) --------------------------------------------------------


@pytest.fixture
async def keyspace() -> AsyncGenerator[RedisAdapter]:
    async for _ in empty_keyspace():
        yield RedisAdapter(redis_options())


async def test_redis_keys_are_named_after_themselves(
    folder: tuple[Explorer, Path], keyspace: RedisAdapter
) -> None:
    destination, incoming = folder
    database = chosen_database()
    options = redis_options()
    client = redis.Redis(host=options.host, port=options.port, db=options.database)
    try:
        await client.set("session:42:token", "abc")
        await client.rpush("queue", "a", "b")
    finally:
        await client.aclose()
    ticked = [key_id(database, "session:42:token"), key_id(database, "queue")]

    single = await RelationCsv().offer(
        keyspace, destination, pair(source_node_ids=ticked[:1])
    )
    done = await transferred(RelationCsv(), keyspace, destination, run(source_node_ids=ticked))

    # A colon is not a file name on every system.
    assert single.suggested_name == "session-42-token.csv"
    assert [item.published_as for item in done.items] == ["session-42-token.csv", "queue.csv"]
    assert (incoming / "queue.csv").read_bytes() == (
        b'\xef\xbb\xbf"index","value"\r\n"0","a"\r\n"1","b"\r\n'
    )


async def test_a_redis_folder_past_the_ceiling_is_refused(
    folder: tuple[Explorer, Path],
    keyspace: RedisAdapter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination, incoming = folder
    options = redis_options()
    client = redis.Redis(host=options.host, port=options.port, db=options.database)
    try:
        for number in range(3):
            await client.set(f"user:{number}", "x")
    finally:
        await client.aclose()
    monkeypatch.setattr(redis_export, "SCAN_CEILING", 2)

    done = await transferred(
        RelationCsv(),
        keyspace,
        destination,
        run(source_node_ids=[folder_id(chosen_database(), "user:")]),
    )

    [item] = done.items
    assert (item.outcome, item.message) == (
        "failed",
        "user.csv was not saved: this folder holds more keys than can be listed",
    )
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
