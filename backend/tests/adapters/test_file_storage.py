"""The local disk as a storage: the containment rule, and what it reads and writes (D8, D150)."""

import os
from pathlib import Path, PurePosixPath

import pytest

from app.adapters.explorer.storage import ROOT, Storage, VersionChanged
from app.adapters.file.storage import LocalStorage


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "q3.csv").write_bytes(b"a,b\n1,2\n")
    return tmp_path


def test_it_is_a_storage(root: Path) -> None:
    assert isinstance(LocalStorage(root), Storage)


def test_no_node_id_means_the_root(root: Path) -> None:
    storage = LocalStorage(root)

    assert storage.place(None) == ROOT
    assert storage.path_of(ROOT) == root.resolve()


def test_a_node_id_is_a_place_inside_the_root(root: Path) -> None:
    storage = LocalStorage(root)

    place = storage.place("reports/q3.csv")

    assert place == PurePosixPath("reports/q3.csv")
    assert storage.path_of(place) == (root / "reports" / "q3.csv").resolve()


@pytest.mark.parametrize(
    "node_id",
    ["..", "../secrets", "reports/../../secrets", "/etc/passwd", "C:/Windows"],
)
def test_a_path_leaving_the_root_is_refused(root: Path, node_id: str) -> None:
    with pytest.raises(ValueError):
        LocalStorage(root).place(node_id)


def test_the_refusal_does_not_name_the_server_path(root: Path) -> None:
    """Error text is what the user sees; the server layout is not theirs."""
    with pytest.raises(ValueError) as raised:
        LocalStorage(root).place("../secrets")

    assert str(root) not in str(raised.value)


@pytest.mark.skipif(os.name != "posix", reason="symlinks need privileges on Windows")
def test_a_symlink_out_of_the_root_is_refused(root: Path, tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (root / "escape").symlink_to(outside)
    storage = LocalStorage(root)

    with pytest.raises(ValueError):
        storage.place("escape")
    assert "escape" not in [entry.name for entry in storage.entries(ROOT)]


def test_check_reports_a_readable_root(root: Path) -> None:
    assert LocalStorage(root).check().ok is True


def test_check_reports_a_missing_root(tmp_path: Path) -> None:
    result = LocalStorage(tmp_path / "not-there").check()

    assert result.ok is False
    assert result.error_kind == "config"


def test_a_folder_lists_its_entries_with_their_facts(root: Path) -> None:
    storage = LocalStorage(root)

    [folder] = storage.entries(ROOT)
    [file] = storage.entries(folder.place)

    assert (folder.name, folder.is_directory) == ("reports", True)
    assert (file.place, file.is_directory, file.size_bytes) == (
        PurePosixPath("reports/q3.csv"),
        False,
        len("a,b\n1,2\n"),
    )
    assert storage.has_entries(folder.place) is True
    assert storage.entry(PurePosixPath("reports/missing.csv")) is None


def test_a_published_file_claims_its_name_and_never_overwrites(root: Path) -> None:
    storage = LocalStorage(root)
    place = PurePosixPath("reports/q4.csv")

    with storage.staged(place) as staged:
        staged.write_text("new")
        storage.publish(staged, place)
    with storage.staged(place) as staged, pytest.raises(FileExistsError):
        staged.write_text("second")
        storage.publish(staged, place)

    assert storage.path_of(place).read_text() == "new"
    # Nothing staged is left beside it, published or not.
    assert sorted(entry.name for entry in storage.entries(place.parent)) == [
        "q3.csv",
        "q4.csv",
    ]


def test_a_replacement_is_refused_once_the_file_has_changed(root: Path) -> None:
    storage = LocalStorage(root)
    place = PurePosixPath("reports/q3.csv")
    version = storage.version(place)

    with storage.staged(place) as staged:
        staged.write_text("a,b\n3,4\n")
        storage.publish(staged, place, replace=True, expected_version=version)
    with storage.staged(place) as staged, pytest.raises(VersionChanged):
        staged.write_text("a,b\n5,6\n")
        storage.publish(staged, place, replace=True, expected_version=version)

    assert storage.path_of(place).read_text() == "a,b\n3,4\n"
    assert storage.version(place) != version


def test_a_renamed_node_does_not_take_a_name_already_there(root: Path) -> None:
    storage = LocalStorage(root)
    storage.make_directory(PurePosixPath("archive"))

    with pytest.raises(FileExistsError):
        storage.rename(PurePosixPath("reports"), PurePosixPath("archive"))
    storage.rename(PurePosixPath("reports"), PurePosixPath("archive/reports"))

    assert storage.entry(PurePosixPath("archive/reports/q3.csv")) is not None
