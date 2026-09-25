"""Files copied and moved across independent explorer storages (D161, D163, D168)."""

import asyncio
import shutil
import uuid
from pathlib import Path

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.file.storage import LocalStorage
from app.connectors.paste import files
from app.connectors.paste.files import FileCopy, FileMove, inspect_files
from app.connectors.paste.models import PastePair, PasteRun
from app.connectors.paste.transfer import Transfer, TransferStopped
from tests.utils.paste_sources import Explorer
from tests.utils.transfers import Recorder, planned, transferred


@pytest.fixture
def sides(tmp_path: Path) -> tuple[LocalStorage, LocalStorage, Path, Path]:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "report.csv").write_bytes(b"id,name\n1,Ada\n")
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


def explorers(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> tuple[Explorer, Explorer]:
    return Explorer(sides[0]), Explorer(sides[1])


def outcomes(done: Transfer) -> list[tuple[str, str, str | None]]:
    return [(item.name, item.outcome, item.message) for item in done.items]


def leftovers(folder: Path) -> list[str]:
    return [path.name for path in folder.iterdir() if path.name.startswith(".dataplayer-")]


async def test_copy_preserves_source_and_publishes_complete_file(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides

    done = await transferred(FileCopy(), source, destination, run())

    assert outcomes(done) == [("report.csv", "done", None)]
    assert done.bytes_total == done.bytes_done == 14
    assert done.published == 1
    assert (right / "incoming" / "report.csv").read_bytes() == (
        left / "report.csv"
    ).read_bytes()
    assert FileCopy().told(done) == "Copied 1 file to incoming"


async def test_a_taken_name_requires_an_explicit_choice(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination = explorers(sides)
    _, _, _, right = sides
    target = right / "incoming" / "report.csv"
    target.write_bytes(b"previous")

    problem = inspect_files(sides[0], sides[1], ["report.csv"], "incoming")
    assert problem is not None
    assert problem.reason == "conflict"
    # Refused before anything starts, so Paste can ask what to do.
    with pytest.raises(ActionRefused, match="already there"):
        await FileCopy().plan(source, destination, run())
    assert target.read_bytes() == b"previous"

    kept = await transferred(FileCopy(), source, destination, run(conflict="rename"))
    assert kept.items[0].published_as == "report (1).csv"
    assert (right / "incoming" / "report (1).csv").read_bytes() == b"id,name\n1,Ada\n"


def test_folder_or_missing_file_is_unavailable(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, _ = sides
    (left / "folder").mkdir()
    assert inspect_files(source, destination, ["folder"], "incoming") is not None
    assert inspect_files(source, destination, ["gone"], "incoming") is not None


async def test_a_folder_under_the_same_name_is_not_replaced(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination = explorers(sides)
    (sides[3] / "incoming" / "report.csv").mkdir()

    with pytest.raises(ActionRefused, match="is a folder here"):
        await FileCopy().plan(source, destination, run(conflict="replace"))
    assert (sides[3] / "incoming" / "report.csv").is_dir()


async def test_copy_works_in_the_reverse_direction(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
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
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    (left / "other").mkdir()
    (left / "other" / "report.csv").write_bytes(b"different")
    choice = ["report.csv", "other/report.csv"]

    assert inspect_files(sides[0], sides[1], choice, "incoming") is not None
    with pytest.raises(ActionRefused, match="same name"):
        await FileCopy().plan(source, destination, run(source_node_ids=choice))
    assert list((right / "incoming").iterdir()) == []


async def test_the_ceilings_refuse_before_anything_starts(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    (left / "second.txt").write_bytes(b"x")

    monkeypatch.setattr(files, "MAX_TRANSFER_BYTES", 4)
    with pytest.raises(ActionRefused, match="exceeds 10 GB"):
        await FileCopy().plan(source, destination, run())
    monkeypatch.setattr(files, "MAX_TRANSFER_BYTES", 1024)
    monkeypatch.setattr(files, "MAX_TRANSFER_FILES", 1)
    problem = inspect_files(sides[0], sides[1], ["report.csv", "second.txt"], "incoming")

    assert problem is not None
    assert problem.message == "Paste at most 1 files at a time"
    assert list((right / "incoming").iterdir()) == []


def test_the_ceilings_are_a_thousand_files_and_ten_gigabytes() -> None:
    assert files.MAX_TRANSFER_FILES == 1000
    assert files.MAX_TRANSFER_BYTES == 10 * 1024**3


async def test_move_publishes_then_removes_the_source(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides

    done = await transferred(FileMove(), source, destination, moving())

    assert outcomes(done) == [("report.csv", "done", None)]
    assert not (left / "report.csv").exists()
    assert (right / "incoming" / "report.csv").read_bytes() == b"id,name\n1,Ada\n"
    assert FileMove().told(done) == "Moved 1 file to incoming"


async def test_move_keeps_both_copies_if_source_removal_fails(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides

    def refuse_removal(_place: object) -> None:
        raise PermissionError("cannot remove")

    monkeypatch.setattr(sides[0], "remove", refuse_removal)

    done = await transferred(FileMove(), source, destination, moving())

    assert outcomes(done) == [
        ("report.csv", "kept", "report.csv was copied, but its source could not be removed")
    ]
    assert (left / "report.csv").exists()
    assert (right / "incoming" / "report.csv").exists()
    assert FileMove().told(done) == "Moved 0 of 1 file to incoming; 1 kept its source"


async def test_one_file_failing_is_its_own_outcome(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
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
    assert sorted(path.name for path in (right / "incoming").iterdir()) == [
        "report.csv",
        "third.txt",
    ]
    assert FileCopy().told(prepared) == "Copied 2 of 3 files to incoming; 1 failed"


async def test_a_file_that_changes_while_it_is_copied_leaves_nothing(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
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
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    monkeypatch.setattr(files, "PIECE_BYTES", 4)
    (left / "large.bin").write_bytes(b"0123456789" * 10)
    request = run(source_node_ids=["report.csv", "large.bin"])
    prepared = await planned(FileCopy(), source, destination, request)
    halfway = asyncio.Event()

    async def after_a_piece(done: Transfer) -> None:
        if done.items[1].outcome == "running":
            halfway.set()
            await asyncio.sleep(10)

    recorder = Recorder(on_progress=after_a_piece)
    recorder.transfer = prepared
    task = asyncio.create_task(FileCopy().transfer(source, destination, prepared, recorder))
    await asyncio.wait_for(halfway.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert [item.outcome for item in prepared.items] == ["done", "stopped"]
    assert sorted(path.name for path in (right / "incoming").iterdir()) == ["report.csv"]
    assert FileCopy().told(prepared) == "Copied 1 of 2 files to incoming; 1 stopped"


async def test_a_destination_folder_that_goes_away_ends_the_transfer(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    (left / "second.txt").write_bytes(b"two")
    (left / "third.txt").write_bytes(b"three")
    request = run(source_node_ids=["report.csv", "second.txt", "third.txt"])
    prepared = await planned(FileCopy(), source, destination, request)

    async def remove_the_folder(done: Transfer) -> None:
        if done.published == 1 and (right / "incoming").exists():
            shutil.rmtree(right / "incoming")

    recorder = Recorder(on_change=remove_the_folder)
    recorder.transfer = prepared
    with pytest.raises(TransferStopped) as stopped:
        await FileCopy().transfer(source, destination, prepared, recorder)

    assert stopped.value.message == "The destination folder is no longer there"
    assert [item.outcome for item in prepared.items] == ["done", "failed", "pending"]
    assert FileCopy().told(prepared, stopped.value.message) == (
        "Copied 1 of 3 files to incoming; 1 failed, 1 not attempted. "
        "The destination folder is no longer there"
    )


async def test_the_kinds_say_what_they_do_to_the_source(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
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


async def test_a_move_can_keep_both_but_cannot_replace(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination = explorers(sides)
    _, _, left, right = sides
    target = right / "incoming" / "report.csv"
    target.write_bytes(b"old")
    kind = FileMove()

    with pytest.raises(ActionRefused, match="cannot replace"):
        await kind.plan(source, destination, moving(conflict="replace"))
    assert target.read_bytes() == b"old"
    assert (left / "report.csv").exists()

    done = await transferred(kind, source, destination, moving(conflict="rename"))
    assert outcomes(done) == [("report.csv", "done", None)]
    assert done.items[0].published_as == "report (1).csv"
    assert not (left / "report.csv").exists()
    assert (right / "incoming" / "report (1).csv").exists()


async def test_supply_refuses_a_folder_on_the_clipboard(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, _, left, _ = sides
    (left / "folder").mkdir()

    held = await FileCopy().supply(Explorer(source), ["folder"])
    fine = await FileCopy().supply(Explorer(source), ["report.csv"])

    assert not held.available
    assert held.reason == "Copy files, not folders or links"
    assert fine.available


def test_nothing_is_left_behind_by_a_published_or_a_failed_file(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    # The staged file lies beside its target and goes with the block.
    _, destination, _, right = sides
    target = destination.place("incoming/new.txt")
    with destination.incoming(target) as arriving:
        arriving.write(b"piece")
        arriving.publish(target)
    with destination.incoming(target) as arriving:
        arriving.write(b"never published")

    assert (right / "incoming" / "new.txt").read_bytes() == b"piece"
    assert leftovers(right / "incoming") == []
