"""Files and folders copied and moved across explorer storages (D161, D163, D168, D169)."""

import asyncio
import shutil
import uuid
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.explorer.storage import Entry, Place
from app.adapters.file.storage import LocalStorage
from app.connectors.paste import files
from app.connectors.paste.files import FileCopy, FileMove, inspect_files
from app.connectors.paste.models import PastePair, PasteRun
from app.connectors.paste.transfer import Transfer, TransferStopped
from app.core.translation import in_language
from tests.utils.paste_sources import Explorer
from tests.utils.transfers import Recorder, planned, transferred

Sides = tuple[LocalStorage, LocalStorage, Path, Path]


@pytest.fixture
def sides(tmp_path: Path) -> Sides:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "report.csv").write_bytes(b"id,name\n1,Ada\n")
    (left / "tree" / "deep" / "empty").mkdir(parents=True)
    (left / "tree" / "a.txt").write_bytes(b"a")
    (left / "tree" / "deep" / "b.txt").write_bytes(b"bb")
    (left / "tree" / "c.txt").write_bytes(b"ccc")
    (right / "incoming").mkdir()
    return LocalStorage(left), LocalStorage(right), left, right


def run(**changes: object) -> PasteRun:
    return PasteRun.model_validate(
        {
            "source_connector_id": str(uuid.uuid4()),
            "source_node_ids": ["report.csv"],
            "destination_node_id": "incoming",
            "mode": "copy",
            "kind": "file_copy",
            **changes,
        }
    )


def moving(**changes: object) -> PasteRun:
    return run(mode="move", kind="file_move", **changes)


def explorers(sides: Sides) -> tuple[Explorer, Explorer]:
    return Explorer(sides[0]), Explorer(sides[1])


def outcomes(done: Transfer) -> list[tuple[str, str, str | None]]:
    return [(item.name, item.outcome, item.message) for item in done.items]


def tree_of(folder: Path) -> list[str]:
    return sorted(path.relative_to(folder).as_posix() for path in folder.rglob("*"))


def as_links(monkeypatch: pytest.MonkeyPatch, storage: LocalStorage, *names: str) -> None:
    """The storage says these are links: Windows makes none without privileges."""
    entries, entry = storage.entries, storage.entry

    def marked(found: Entry) -> Entry:
        return replace(found, is_link=True) if found.name in names else found

    def listed(place: Place) -> list[Entry]:
        return [marked(found) for found in entries(place)]

    def one(place: Place) -> Entry | None:
        found = entry(place)
        return None if found is None else marked(found)

    monkeypatch.setattr(storage, "entries", listed)
    monkeypatch.setattr(storage, "entry", one)


async def _stopped_at(
    kind: FileCopy | FileMove,
    source: Explorer,
    destination: Explorer,
    prepared: Transfer,
    path: str,
) -> list[str]:
    """Carry it out and stop it inside `path`; the outcomes then."""
    halfway = asyncio.Event()

    async def after_a_piece(done: Transfer) -> None:
        if done.current == path and done.bytes_done > 0:
            halfway.set()
            await asyncio.sleep(10)

    recorder = Recorder(on_progress=after_a_piece)
    recorder.transfer = prepared
    task = asyncio.create_task(kind.transfer(source, destination, prepared, recorder))
    await asyncio.wait_for(halfway.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    return [item.outcome for item in prepared.items]


# --- files ------------------------------------------------------------------


async def test_copy_preserves_source_and_publishes_complete_file(sides: Sides) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides

    done = await transferred(FileCopy(), source, destination, run())

    assert outcomes(done) == [("report.csv", "done", None)]
    assert done.bytes_total == done.bytes_done == 14
    assert (done.files_total, done.files_done, done.published) == (1, 1, 1)
    assert (right / "incoming" / "report.csv").read_bytes() == (
        left / "report.csv"
    ).read_bytes()
    assert FileCopy().told(done) == "Copied 1 file to incoming"


async def test_what_a_copy_says_is_in_the_language_asked_for(sides: Sides) -> None:
    """The sentence is whole in Russian, the count after a colon (D226)."""
    source, destination = explorers(sides)

    done = await transferred(FileCopy(), source, destination, run())

    assert in_language("ru", lambda: FileCopy().told(done)) == (
        "Скопировано в incoming, файлов: 1"
    )


async def test_a_taken_name_requires_an_explicit_choice(sides: Sides) -> None:
    source, destination = explorers(sides)
    _, _, _, right = sides
    target = right / "incoming" / "report.csv"
    target.write_bytes(b"previous")

    problem, replaceable = inspect_files(sides[0], sides[1], ["report.csv"], "incoming")
    assert problem is not None
    assert (problem.reason, replaceable) == ("conflict", True)
    # Refused before anything starts, so Paste can ask what to do.
    with pytest.raises(ActionRefused, match="already there"):
        await FileCopy().plan(source, destination, run())
    assert target.read_bytes() == b"previous"

    kept = await transferred(FileCopy(), source, destination, run(conflict="rename"))
    assert kept.items[0].published_as == "report (1).csv"
    assert (right / "incoming" / "report (1).csv").read_bytes() == b"id,name\n1,Ada\n"


def test_a_missing_file_or_a_ticked_link_is_unavailable(
    sides: Sides, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, destination, _, _ = sides
    assert inspect_files(source, destination, ["gone"], "incoming")[0] is not None
    as_links(monkeypatch, source, "report.csv")

    problem, _ = inspect_files(source, destination, ["report.csv"], "incoming")

    assert problem is not None
    assert problem.message == "Copy files and folders, not links"


async def test_a_folder_under_the_same_name_is_not_replaced(sides: Sides) -> None:
    source, destination = explorers(sides)
    (sides[3] / "incoming" / "report.csv").mkdir()

    with pytest.raises(ActionRefused, match="is a folder here"):
        await FileCopy().plan(source, destination, run(conflict="replace"))
    assert (sides[3] / "incoming" / "report.csv").is_dir()


async def test_copy_works_in_the_reverse_direction(sides: Sides) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    (right / "incoming" / "reply.txt").write_bytes(b"answer")

    done = await transferred(
        FileCopy(),
        destination,
        source,
        run(source_node_ids=["incoming/reply.txt"], destination_node_id=None),
    )

    assert outcomes(done) == [("reply.txt", "done", None)]
    assert (left / "reply.txt").read_bytes() == b"answer"


async def test_a_batch_with_duplicate_names_is_refused_before_anything_starts(
    sides: Sides,
) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    (left / "other").mkdir()
    (left / "other" / "report.csv").write_bytes(b"different")
    choice = ["report.csv", "other/report.csv"]

    assert inspect_files(sides[0], sides[1], choice, "incoming")[0] is not None
    with pytest.raises(ActionRefused, match="same name"):
        await FileCopy().plan(source, destination, run(source_node_ids=choice))
    assert list((right / "incoming").iterdir()) == []


async def test_the_ceilings_refuse_before_anything_starts(
    sides: Sides, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, destination = explorers(sides)
    _, _, _, right = sides

    monkeypatch.setattr(files, "MAX_TRANSFER_BYTES", 4)
    with pytest.raises(ActionRefused, match="exceeds 10 GB"):
        await FileCopy().plan(source, destination, run())
    with pytest.raises(ActionRefused, match="exceeds 10 GB"):
        await FileCopy().plan(source, destination, run(source_node_ids=["tree"]))
    monkeypatch.setattr(files, "MAX_TRANSFER_BYTES", 1024)
    # The tree holds five entries below it and is one itself.
    monkeypatch.setattr(files, "MAX_TRANSFER_ENTRIES", 5)
    with pytest.raises(ActionRefused, match="more than 10,000 files and folders"):
        await FileCopy().plan(source, destination, run(source_node_ids=["tree"]))
    monkeypatch.setattr(files, "MAX_TRANSFER_ENTRIES", 6)
    await FileCopy().plan(source, destination, run(source_node_ids=["tree"]))

    assert list((right / "incoming").iterdir()) == []


def test_the_ceilings_are_ten_thousand_entries_and_ten_gigabytes() -> None:
    assert files.MAX_TRANSFER_ENTRIES == 10_000
    assert files.MAX_TRANSFER_BYTES == 10 * 1024**3


async def test_one_file_failing_is_its_own_outcome(sides: Sides) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    (left / "second.txt").write_bytes(b"two")
    (left / "third.txt").write_bytes(b"three")
    request = run(source_node_ids=["report.csv", "second.txt", "third.txt"])
    prepared = await planned(FileCopy(), source, destination, request)
    # Gone between Paste and its turn.
    (left / "second.txt").unlink()

    recorder = Recorder()
    recorder.transfer = prepared
    await FileCopy().transfer(source, destination, prepared, recorder)

    assert outcomes(prepared) == [
        ("report.csv", "done", None),
        ("second.txt", "failed", "second.txt no longer exists"),
        ("third.txt", "done", None),
    ]
    assert tree_of(right / "incoming") == ["report.csv", "third.txt"]
    assert FileCopy().told(prepared) == "Copied 2 of 3 files to incoming; 1 failed"


async def test_a_file_that_changes_while_it_is_copied_leaves_nothing(
    sides: Sides, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, destination = explorers(sides)
    _, _, _, right = sides
    versions = iter(["before", "after", "after"])
    monkeypatch.setattr(sides[0], "version", lambda _place: next(versions))

    done = await transferred(FileCopy(), source, destination, run())

    assert outcomes(done) == [
        ("report.csv", "failed", "report.csv changed while it was being copied")
    ]
    assert list((right / "incoming").iterdir()) == []


async def test_stop_inside_a_file_keeps_what_arrived_and_leaves_nothing_of_the_rest(
    sides: Sides, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    monkeypatch.setattr(files, "PIECE_BYTES", 4)
    (left / "large.bin").write_bytes(b"0123456789" * 10)
    request = run(source_node_ids=["report.csv", "large.bin"])
    prepared = await planned(FileCopy(), source, destination, request)

    halfway = await _stopped_at(FileCopy(), source, destination, prepared, "large.bin")

    assert halfway == ["done", "stopped"]
    assert tree_of(right / "incoming") == ["report.csv"]
    assert FileCopy().told(prepared) == (
        "Copied 1 of 2 files to incoming; stopped, 1 not attempted"
    )


async def test_a_destination_folder_that_goes_away_ends_the_transfer(sides: Sides) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    (left / "second.txt").write_bytes(b"two")
    (left / "third.txt").write_bytes(b"three")
    request = run(source_node_ids=["report.csv", "second.txt", "third.txt"])
    prepared = await planned(FileCopy(), source, destination, request)

    async def remove_the_folder(done: Transfer) -> None:
        if done.published == 1 and (right / "incoming").exists():
            shutil.rmtree(right / "incoming")

    recorder = Recorder(on_progress=remove_the_folder)
    recorder.transfer = prepared
    with pytest.raises(TransferStopped) as stopped:
        await FileCopy().transfer(source, destination, prepared, recorder)

    assert stopped.value.message == "The destination folder is no longer there"
    assert [item.outcome for item in prepared.items] == ["done", "pending", "pending"]
    assert FileCopy().told(prepared, stopped.value.message) == (
        "Copied 1 of 3 files to incoming; 2 not attempted. "
        "The destination folder is no longer there"
    )


async def test_the_kinds_say_what_they_do_to_the_source(sides: Sides) -> None:
    source, destination = explorers(sides)
    pair = PastePair.model_validate(
        {
            "source_connector_id": str(uuid.uuid4()),
            "source_node_ids": ["report.csv"],
            "destination_node_id": "incoming",
            "mode": "copy",
        }
    )

    copy = await FileCopy().offer(source, destination, pair)
    move = await FileMove().offer(source, destination, pair)

    assert copy.available and copy.can_replace and not copy.changes_source
    assert move.available and not move.can_replace and move.changes_source
    assert not copy.converts


async def test_supply_takes_files_and_folders_but_not_a_link(
    sides: Sides, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = sides[0]

    both = await FileCopy().supply(Explorer(source), ["report.csv", "tree"])
    as_links(monkeypatch, source, "report.csv")
    link = await FileCopy().supply(Explorer(source), ["report.csv"])

    assert both.available
    assert link.reason == "Copy files and folders, not links"


# --- folders ----------------------------------------------------------------


async def test_a_folder_arrives_whole_with_its_empty_folders(sides: Sides) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides

    done = await transferred(FileCopy(), source, destination, run(source_node_ids=["tree"]))

    [item] = done.items
    assert (item.is_folder, item.files, item.arrived, item.outcome) == (True, 3, 3, "done")
    assert tree_of(right / "incoming" / "tree") == tree_of(left / "tree")
    assert (right / "incoming" / "tree" / "deep" / "b.txt").read_bytes() == b"bb"
    assert (done.bytes_total, done.bytes_done) == (6, 6)
    assert FileCopy().told(done) == "Copied 3 files to incoming"


async def test_a_link_inside_a_folder_is_skipped_and_listed(
    sides: Sides, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, destination = explorers(sides)
    _, _, _, right = sides
    as_links(monkeypatch, sides[0], "b.txt")

    done = await transferred(FileCopy(), source, destination, run(source_node_ids=["tree"]))

    [item] = done.items
    assert (item.files, item.arrived, item.skipped, item.outcome) == (2, 2, 1, "done")
    assert [(problem.path, problem.message) for problem in done.problems] == [
        ("tree/deep/b.txt", "tree/deep/b.txt is a link and was skipped")
    ]
    assert not (right / "incoming" / "tree" / "deep" / "b.txt").exists()
    assert FileCopy().told(done) == "Copied 2 files to incoming; 1 link skipped"


async def test_a_taken_folder_name_offers_keep_both_and_never_replace(sides: Sides) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    (right / "incoming" / "tree").mkdir()
    (right / "incoming" / "tree" / "old.txt").write_bytes(b"old")
    pair = PastePair.model_validate(
        {
            "source_connector_id": str(uuid.uuid4()),
            "source_node_ids": ["tree"],
            "destination_node_id": "incoming",
            "mode": "copy",
        }
    )

    offer = await FileCopy().offer(source, destination, pair)
    with pytest.raises(ActionRefused, match="kept rather than replaced"):
        await FileCopy().plan(
            source, destination, run(source_node_ids=["tree"], conflict="replace")
        )
    kept = await transferred(
        FileCopy(), source, destination, run(source_node_ids=["tree"], conflict="rename")
    )

    assert (offer.available, offer.name_conflict, offer.can_replace) == (False, True, False)
    assert kept.items[0].published_as == "tree (1)"
    assert tree_of(right / "incoming" / "tree") == ["old.txt"]
    assert tree_of(right / "incoming" / "tree (1)") == tree_of(left / "tree")


async def test_a_folder_is_not_pasted_into_itself_on_this_disk(tmp_path: Path) -> None:
    (tmp_path / "tree" / "inside").mkdir(parents=True)
    whole = Explorer(LocalStorage(tmp_path))
    below = Explorer(LocalStorage(tmp_path / "tree"))

    with pytest.raises(ActionRefused, match="tree cannot be put inside itself"):
        await FileCopy().plan(
            whole, below, run(source_node_ids=["tree"], destination_node_id="inside")
        )


async def test_a_move_removes_its_sources_only_once_everything_arrived(sides: Sides) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    recorder = Recorder()

    done = await transferred(
        FileMove(),
        source,
        destination,
        moving(source_node_ids=["tree", "report.csv"]),
        recorder,
    )

    assert recorder.removing_seen
    assert [item.outcome for item in done.items] == ["done", "done"]
    assert not (left / "tree").exists()
    assert not (left / "report.csv").exists()
    assert tree_of(right / "incoming") == [
        "report.csv",
        "tree",
        "tree/a.txt",
        "tree/c.txt",
        "tree/deep",
        "tree/deep/b.txt",
        "tree/deep/empty",
    ]
    assert FileMove().told(done) == "Moved 4 files to incoming"


async def test_a_moved_folder_keeps_what_did_not_arrive(
    sides: Sides, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, destination = explorers(sides)
    _, _, left, _ = sides
    opened = sides[0].open

    def failing(place: Place) -> BinaryIO:
        if place.name == "b.txt":
            raise PermissionError("unreadable")
        return opened(place)

    monkeypatch.setattr(sides[0], "open", failing)

    done = await transferred(FileMove(), source, destination, moving(source_node_ids=["tree"]))

    [item] = done.items
    assert (item.arrived, item.failed, item.removed, item.outcome) == (2, 1, 2, "failed")
    # The folder that still holds the failed file stays; the empty one goes.
    assert tree_of(left / "tree") == ["deep", "deep/b.txt"]
    assert done.problems[0].path == "tree/deep/b.txt"
    assert FileMove().told(done) == "Moved 2 of 3 files to incoming; 1 failed"


async def test_a_move_of_plain_files_also_removes_only_at_the_end(
    sides: Sides, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    monkeypatch.setattr(files, "PIECE_BYTES", 4)
    (left / "large.bin").write_bytes(b"0123456789" * 10)
    prepared = await planned(
        FileMove(), source, destination, moving(source_node_ids=["report.csv", "large.bin"])
    )

    halfway = await _stopped_at(FileMove(), source, destination, prepared, "large.bin")

    # The first file arrived, and its source is still whole: nothing is torn
    # between two connections.
    assert halfway == ["done", "stopped"]
    assert (left / "report.csv").exists()
    assert (right / "incoming" / "report.csv").exists()


async def test_stopping_a_folder_move_leaves_the_source_whole(
    sides: Sides, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    monkeypatch.setattr(files, "PIECE_BYTES", 4)
    (left / "tree" / "deep" / "large.bin").write_bytes(b"0123456789" * 10)
    before = tree_of(left / "tree")
    prepared = await planned(FileMove(), source, destination, moving(source_node_ids=["tree"]))

    halfway = await _stopped_at(
        FileMove(), source, destination, prepared, "tree/deep/large.bin"
    )

    assert halfway == ["stopped"]
    assert tree_of(left / "tree") == before
    assert not (right / "incoming" / "tree" / "deep" / "large.bin").exists()
    assert [path for path in tree_of(right / "incoming") if ".dataplayer-" in path] == []


def test_nothing_is_left_behind_by_a_published_or_a_failed_file(sides: Sides) -> None:
    # The staged file lies beside its target and goes with the block.
    _, destination, _, right = sides
    target = destination.place("incoming/new.txt")
    with destination.incoming(target) as arriving:
        arriving.write(b"piece")
        arriving.publish(target)
    with destination.incoming(target) as arriving:
        arriving.write(b"never published")

    assert tree_of(right / "incoming") == ["new.txt"]


def test_a_folder_is_removed_only_while_it_is_empty(sides: Sides) -> None:
    source, _, left, _ = sides

    with pytest.raises(OSError):
        source.remove_empty(source.place("tree/deep"))
    source.remove_empty(source.place("tree/deep/empty"))

    assert (left / "tree" / "deep" / "b.txt").exists()
    assert not (left / "tree" / "deep" / "empty").exists()
