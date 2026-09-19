"""Making an archive out of a selection, and taking one apart again."""

import gzip
import os
import tarfile
import zipfile
from pathlib import Path

import pytest
from anyio import to_thread

from app.adapters.actions import ActionRefused, ActionResult, TakesNodeSet, TakesParams
from app.adapters.explorer.actions import ExplorerActions
from app.adapters.explorer.packing import (
    NotUnpackable,
    is_unpackable,
    pack,
    unpack,
    unpacked_name,
)
from app.adapters.file.storage import LocalStorage


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.csv").write_text("id,name\n1,one\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("first\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def actions(root: Path) -> ExplorerActions:
    return ExplorerActions(LocalStorage(root))


async def _run(
    actions: ExplorerActions, command: str, node_id: str | None, **params: object
) -> ActionResult:
    action = actions.action(command)
    assert isinstance(action, TakesParams)
    return await action.perform(node_id, params)


async def _run_on_set(
    actions: ExplorerActions, command: str, node_ids: list[str], **params: object
) -> ActionResult:
    action = actions.action(command)
    assert isinstance(action, TakesNodeSet)
    return await action.perform_on_set(node_ids, params)


# --- what a name says --------------------------------------------------------


def test_the_tar_family_is_recognised_before_its_compression() -> None:
    # `.tar.gz` is a tar, not one compressed file, and the order of the
    # suffixes is the only thing that decides it.
    assert unpacked_name("reports.tar.gz") == "reports"
    assert unpacked_name("notes.txt.gz") == "notes.txt"
    assert unpacked_name("reports.zip") == "reports"


def test_a_file_that_is_not_an_archive_is_not_unpackable() -> None:
    assert is_unpackable("reports.zip")
    assert is_unpackable("reports.tgz")
    assert not is_unpackable("notes.txt")
    # A name that is nothing but a suffix is a file called `.zip`.
    assert not is_unpackable(".zip")


# --- packing -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("format", "suffix"),
    [("zip", ".zip"), ("tar", ".tar"), ("tar.gz", ".tar.gz"), ("tar.xz", ".tar.xz")],
)
async def test_a_selection_becomes_one_archive_in_the_chosen_format(
    actions: ExplorerActions, root: Path, format: str, suffix: str
) -> None:
    result = await _run_on_set(
        actions,
        "create_archive",
        ["reports", "notes.txt"],
        name="everything",
        format=format,
    )

    made = root / f"everything{suffix}"
    assert made.exists()
    assert result.message == f"everything{suffix} created"
    assert result.reload_node_ids == [None]


async def test_a_zip_holds_the_folder_and_the_file_it_was_given(
    actions: ExplorerActions, root: Path
) -> None:
    await _run_on_set(
        actions, "create_archive", ["reports", "notes.txt"], name="everything"
    )

    with zipfile.ZipFile(root / "everything.zip") as made:
        assert set(made.namelist()) == {
            "reports/",
            "reports/q3.csv",
            "notes.txt",
        }


async def test_a_tar_holds_the_same_names(actions: ExplorerActions, root: Path) -> None:
    await _run_on_set(
        actions,
        "create_archive",
        ["reports", "notes.txt"],
        name="everything",
        format="tar.gz",
    )

    with tarfile.open(root / "everything.tar.gz") as made:
        assert set(made.getnames()) == {"reports", "reports/q3.csv", "notes.txt"}


async def test_the_suffix_is_not_doubled(actions: ExplorerActions, root: Path) -> None:
    await _run_on_set(
        actions, "create_archive", ["notes.txt"], name="everything.zip"
    )

    assert (root / "everything.zip").exists()
    assert not (root / "everything.zip.zip").exists()


async def test_a_taken_name_gets_the_next_free_one(
    actions: ExplorerActions, root: Path
) -> None:
    await _run_on_set(actions, "create_archive", ["notes.txt"], name="everything")
    await _run_on_set(actions, "create_archive", ["notes.txt"], name="everything")

    assert (root / "everything.zip").exists()
    assert (root / "everything.zip (1)").exists()


async def test_a_name_with_a_separator_in_it_is_refused(
    actions: ExplorerActions,
) -> None:
    with pytest.raises(ValueError, match="single plain name"):
        await _run_on_set(
            actions, "create_archive", ["notes.txt"], name="../escape"
        )


@pytest.mark.skipif(os.name != "posix", reason="symlinks need privileges on Windows")
async def test_a_link_named_in_the_selection_is_not_archived(
    actions: ExplorerActions, root: Path
) -> None:
    """Named directly or met in the walk, a link goes the same way.

    Resolving one first would pack the tree it points at, so the same link
    would be archived or refused depending only on how it was reached.
    """
    (root / "gone").symlink_to(root / "reports", target_is_directory=True)

    with pytest.raises(ActionRefused, match="Symbolic links"):
        await _run_on_set(
            actions, "create_archive", ["gone", "notes.txt"], name="everything"
        )

    assert not (root / "everything.zip").exists()


@pytest.mark.skipif(os.name != "posix", reason="symlinks need privileges on Windows")
async def test_archiving_leaves_nothing_behind_when_it_fails(
    actions: ExplorerActions, root: Path
) -> None:
    """A refused archive is not a file with the name somebody will look for."""
    # The link is met while walking the folder, so the refusal comes once the
    # archive being built already holds what was added before it.
    (root / "reports" / "gone").symlink_to(root / "notes.txt")

    with pytest.raises(ActionRefused):
        await _run_on_set(
            actions, "create_archive", ["reports", "notes.txt"], name="everything"
        )

    assert not (root / "everything.zip").exists()
    left = await to_thread.run_sync(lambda: [entry.name for entry in root.iterdir()])
    assert not any(name.startswith(".dataplayer-packing-") for name in left)


# --- unpacking ---------------------------------------------------------------


async def test_an_archive_is_extracted_into_a_folder_of_its_own(
    actions: ExplorerActions, root: Path
) -> None:
    pack([root / "reports"], root / "bundle.zip", "zip")

    result = await _run(actions, "extract_archive", "bundle.zip")

    assert result.message == "2 files extracted into bundle"
    assert (root / "bundle" / "reports" / "q3.csv").read_text(encoding="utf-8")
    assert result.reload_node_ids == [None]


async def test_an_archive_can_be_extracted_where_it_lies(
    actions: ExplorerActions, root: Path
) -> None:
    pack([root / "notes.txt"], root / "bundle.tar.gz", "tar.gz")
    (root / "notes.txt").unlink()

    await _run(actions, "extract_archive", "bundle.tar.gz", into_folder=False)

    assert (root / "notes.txt").read_text(encoding="utf-8") == "first\n"


async def test_one_compressed_file_extracts_to_the_file(
    actions: ExplorerActions, root: Path
) -> None:
    with gzip.open(root / "notes.txt.gz", "wb") as out:
        out.write(b"compressed\n")

    await _run(actions, "extract_archive", "notes.txt.gz", into_folder=False)

    assert (root / "notes.txt").read_text(encoding="utf-8") == "compressed\n"


async def test_extract_is_offered_only_for_a_file_that_is_an_archive(
    actions: ExplorerActions, root: Path
) -> None:
    pack([root / "notes.txt"], root / "bundle.zip", "zip")

    archive = {action.name for action in await actions.available("bundle.zip")}
    plain = {action.name for action in await actions.available("notes.txt")}
    folder = {action.name for action in await actions.available("reports")}

    assert "extract_archive" in archive
    assert "extract_archive" not in plain
    assert "extract_archive" not in folder
    # Archiving is offered for both kinds, because both can go into one.
    assert "create_archive" in plain
    assert "create_archive" in folder


async def test_an_archive_naming_a_place_outside_itself_is_refused_whole(
    root: Path, tmp_path: Path
) -> None:
    escaping = root / "evil.zip"
    with zipfile.ZipFile(escaping, "w") as made:
        made.writestr("safe.txt", "safe")
        made.writestr("../escaped.txt", "escaped")

    destination = root / "out"
    destination.mkdir()
    with pytest.raises(ActionRefused, match="leaves it"):
        unpack(escaping, destination)

    # Nothing at all, not even the entry that came first and was safe.
    assert list(destination.iterdir()) == []
    assert not (tmp_path.parent / "escaped.txt").exists()


async def test_a_tar_holding_a_link_is_refused(root: Path) -> None:
    (root / "target.txt").write_text("x", encoding="utf-8")
    linked = root / "linked.tar"
    with tarfile.open(linked, "w") as made:
        made.add(root / "target.txt", arcname="target.txt")
        info = tarfile.TarInfo("shortcut")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        made.addfile(info)

    destination = root / "out"
    destination.mkdir()
    with pytest.raises(ActionRefused, match="link"):
        unpack(linked, destination)


async def test_a_file_that_is_not_an_archive_cannot_be_unpacked(root: Path) -> None:
    with pytest.raises(NotUnpackable):
        unpack(root / "notes.txt", root)


async def test_a_failed_extraction_takes_its_folder_with_it(
    actions: ExplorerActions, root: Path
) -> None:
    escaping = root / "evil.zip"
    with zipfile.ZipFile(escaping, "w") as made:
        made.writestr("../escaped.txt", "escaped")

    with pytest.raises(ActionRefused):
        await _run(actions, "extract_archive", "evil.zip")

    assert not (root / "evil").exists()
