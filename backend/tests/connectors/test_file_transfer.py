"""File copies across independent explorer storages."""

from pathlib import Path

import pytest

from app.adapters.actions import ActionRefused
from app.adapters.file.storage import LocalStorage
from app.connectors import file_transfer
from app.connectors.file_transfer import (
    FileCopyRequest,
    copy_files,
    inspect_copy,
    inspect_move,
    move_files,
)


@pytest.fixture
def sides(tmp_path: Path) -> tuple[LocalStorage, LocalStorage, Path, Path]:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "report.csv").write_bytes(b"id,name\n1,Ada\n")
    (right / "incoming").mkdir()
    return LocalStorage(left), LocalStorage(right), left, right


def request(**changes: object) -> FileCopyRequest:
    return FileCopyRequest.model_validate(
        {
            "source_connector_id": "source",
            "source_node_ids": ["report.csv"],
            "destination_node_id": "incoming",
            **changes,
        }
    )


def test_copy_preserves_source_and_publishes_complete_file(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, right = sides
    assert inspect_copy(source, destination, request()).available

    result = copy_files(source, destination, request())

    assert result.copied == 1
    assert result.reload_node_ids == ["incoming"]
    assert (right / "incoming" / "report.csv").read_bytes() == (
        left / "report.csv"
    ).read_bytes()


def test_a_taken_name_requires_an_explicit_choice(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, _, right = sides
    target = right / "incoming" / "report.csv"
    target.write_bytes(b"previous")

    offer = inspect_copy(source, destination, request())
    assert not offer.available
    assert offer.name_conflict
    with pytest.raises(ActionRefused, match="already there"):
        copy_files(source, destination, request())
    assert target.read_bytes() == b"previous"

    copy_files(source, destination, request(conflict="rename"))
    assert (right / "incoming" / "report (1).csv").read_bytes() == b"id,name\n1,Ada\n"


def test_folder_or_missing_file_is_unavailable(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, _ = sides
    (left / "folder").mkdir()
    assert not inspect_copy(source, destination, request(source_node_ids=["folder"])).available
    assert not inspect_copy(source, destination, request(source_node_ids=["gone"])).available


def test_copy_works_in_the_reverse_direction(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, right = sides
    (right / "incoming" / "reply.txt").write_bytes(b"answer")

    result = copy_files(
        destination,
        source,
        request(source_node_ids=["incoming/reply.txt"], destination_node_id=None),
    )

    assert result.copied == 1
    assert (left / "reply.txt").read_bytes() == b"answer"


def test_a_batch_with_duplicate_names_is_rejected_before_writing(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, right = sides
    (left / "other").mkdir()
    (left / "other" / "report.csv").write_bytes(b"different")
    choice = request(source_node_ids=["report.csv", "other/report.csv"])

    assert not inspect_copy(source, destination, choice).available
    with pytest.raises(ActionRefused):
        copy_files(source, destination, choice)
    assert list((right / "incoming").iterdir()) == []


def test_size_ceiling_refuses_before_publication(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, destination, _, right = sides
    monkeypatch.setattr(file_transfer, "MAX_TRANSFER_BYTES", 4)

    assert not inspect_copy(source, destination, request()).available
    with pytest.raises(ActionRefused):
        copy_files(source, destination, request())
    assert list((right / "incoming").iterdir()) == []


def test_move_publishes_then_removes_the_source(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, right = sides
    assert inspect_move(source, destination, request()).available

    result = move_files(source, destination, request())

    assert result.moved == 1
    assert result.reload_node_ids == ["incoming"]
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
        move_files(source, destination, request())
    assert (left / "report.csv").exists()
    assert (right / "incoming" / "report.csv").exists()


def test_move_conflict_can_keep_both_but_cannot_replace(
    sides: tuple[LocalStorage, LocalStorage, Path, Path],
) -> None:
    source, destination, left, right = sides
    target = right / "incoming" / "report.csv"
    target.write_bytes(b"old")

    assert inspect_move(source, destination, request()).name_conflict
    assert not inspect_move(
        source, destination, request(conflict="replace")
    ).available
    with pytest.raises(ActionRefused):
        move_files(source, destination, request(conflict="replace"))
    assert target.read_bytes() == b"old"
    assert (left / "report.csv").exists()

    move_files(source, destination, request(conflict="rename"))
    assert not (left / "report.csv").exists()
    assert (right / "incoming" / "report (1).csv").exists()
