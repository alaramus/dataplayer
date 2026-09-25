"""Files copied and moved across independent explorer storages (D161, D163)."""

import uuid
from pathlib import Path

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.file.storage import LocalStorage
from app.connectors.paste import files
from app.connectors.paste.files import FileCopy, FileMove, inspect_files, transfer_files
from app.connectors.paste.models import PastePair, PasteRun
from tests.utils.paste_sources import Explorer


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


def test_copy_preserves_source_and_publishes_complete_file(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, right = sides
    assert inspect_files(source, destination, ["report.csv"], "incoming") is None

    copied = transfer_files(source, destination, run(), move=False)

    assert copied == 1
    assert (right / "incoming" / "report.csv").read_bytes() == (
        left / "report.csv"
    ).read_bytes()


def test_a_taken_name_requires_an_explicit_choice(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, _, right = sides
    target = right / "incoming" / "report.csv"
    target.write_bytes(b"previous")

    problem = inspect_files(source, destination, ["report.csv"], "incoming")
    assert problem is not None
    assert problem.reason == "conflict"
    with pytest.raises(ActionRefused, match="already there"):
        transfer_files(source, destination, run(), move=False)
    assert target.read_bytes() == b"previous"

    transfer_files(source, destination, run(conflict="rename"), move=False)
    assert (right / "incoming" / "report (1).csv").read_bytes() == b"id,name\n1,Ada\n"


def test_folder_or_missing_file_is_unavailable(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, _ = sides
    (left / "folder").mkdir()
    assert inspect_files(source, destination, ["folder"], "incoming") is not None
    assert inspect_files(source, destination, ["gone"], "incoming") is not None


def test_a_folder_under_the_same_name_is_not_replaced(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, _, right = sides
    (right / "incoming" / "report.csv").mkdir()

    with pytest.raises(ActionRefused, match="is a folder here"):
        transfer_files(source, destination, run(conflict="replace"), move=False)
    assert (right / "incoming" / "report.csv").is_dir()


def test_copy_works_in_the_reverse_direction(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, right = sides
    (right / "incoming" / "reply.txt").write_bytes(b"answer")

    copied = transfer_files(
        destination,
        source,
        run(source_node_ids=["incoming/reply.txt"], destination_node_id=None),
        move=False,
    )

    assert copied == 1
    assert (left / "reply.txt").read_bytes() == b"answer"


def test_a_batch_with_duplicate_names_is_rejected_before_writing(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, right = sides
    (left / "other").mkdir()
    (left / "other" / "report.csv").write_bytes(b"different")
    choice = ["report.csv", "other/report.csv"]

    assert inspect_files(source, destination, choice, "incoming") is not None
    with pytest.raises(ActionRefused):
        transfer_files(source, destination, run(source_node_ids=choice), move=False)
    assert list((right / "incoming").iterdir()) == []


def test_size_ceiling_refuses_before_publication(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, destination, _, right = sides
    monkeypatch.setattr(files, "MAX_TRANSFER_BYTES", 4)

    assert inspect_files(source, destination, ["report.csv"], "incoming") is not None
    with pytest.raises(ActionRefused):
        transfer_files(source, destination, run(), move=False)
    assert list((right / "incoming").iterdir()) == []


def test_too_many_files_is_a_reason_rather_than_a_rejected_request(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, _ = sides
    names = [f"file-{index}.txt" for index in range(files.MAX_TRANSFER_FILES + 1)]
    for name in names:
        (left / name).write_bytes(b"x")

    problem = inspect_files(source, destination, names, "incoming")

    assert problem is not None
    assert "at most 20 files" in problem.message


def test_move_publishes_then_removes_the_source(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, right = sides

    moved = transfer_files(source, destination, moving(), move=True)

    assert moved == 1
    assert not (left / "report.csv").exists()
    assert (right / "incoming" / "report.csv").read_bytes() == b"id,name\n1,Ada\n"


def test_move_keeps_both_copies_if_source_removal_fails(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, destination, left, right = sides

    def refuse_removal(_place: object) -> None:
        raise PermissionError("cannot remove")

    monkeypatch.setattr(source, "remove", refuse_removal)

    with pytest.raises(ActionRefused, match="source could not be removed"):
        transfer_files(source, destination, moving(), move=True)
    assert (left / "report.csv").exists()
    assert (right / "incoming" / "report.csv").exists()


async def test_the_kinds_say_what_they_do_to_the_source(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, _, _ = sides
    pair = PastePair.model_validate(
        {
            "source_connector_id": str(uuid.uuid4()),
            "source_node_ids": ["report.csv"],
            "destination_node_id": "incoming",
            "mode": "copy",
        }
    )

    copy = await FileCopy().offer(Explorer(source), Explorer(destination), pair)
    move = await FileMove().offer(Explorer(source), Explorer(destination), pair)

    assert copy.available and copy.can_replace and not copy.changes_source
    assert move.available and not move.can_replace and move.changes_source
    assert not copy.converts


async def test_a_move_can_keep_both_but_cannot_replace(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, right = sides
    target = right / "incoming" / "report.csv"
    target.write_bytes(b"old")
    kind = FileMove()

    with pytest.raises(ActionRefused, match="cannot replace"):
        await kind.run(Explorer(source), Explorer(destination), moving(conflict="replace"))
    assert target.read_bytes() == b"old"
    assert (left / "report.csv").exists()

    result = await kind.run(
        Explorer(source), Explorer(destination), moving(conflict="rename")
    )
    assert result.message == "1 file moved"
    assert result.reload_node_ids == ["incoming"]
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
