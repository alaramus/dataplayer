import os
import uuid
from pathlib import Path

import pytest

from app.seed_storage import SAMPLE_ROWS, remove_orphan_homes, write_samples


def test_samples_cover_every_content_kind(tmp_path: Path) -> None:
    """A table, plain text and something unreadable: the three outcomes."""
    write_samples(tmp_path)

    names = {path.name for path in tmp_path.rglob("*")}
    assert {"sample.csv", "sample.tsv", "notes.txt", "logo.png", "reports"} <= names


def test_the_sample_table_spans_more_than_one_page(tmp_path: Path) -> None:
    write_samples(tmp_path)

    lines = (tmp_path / "sample.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == SAMPLE_ROWS + 1


def test_writing_twice_leaves_the_same_content(tmp_path: Path) -> None:
    write_samples(tmp_path)
    first = (tmp_path / "sample.csv").read_text(encoding="utf-8")

    write_samples(tmp_path)

    assert (tmp_path / "sample.csv").read_text(encoding="utf-8") == first


LEFTOVER = "a,b\n1,2\n"


def make_home(root: Path, user_id: uuid.UUID) -> Path:
    directory = root / str(user_id)
    directory.mkdir(parents=True)
    (directory / "leftover.csv").write_text(LEFTOVER, encoding="utf-8")
    return directory


def test_a_home_without_a_user_is_removed(tmp_path: Path) -> None:
    """What the test suite leaves behind: the user is gone, the files are not."""
    orphan = make_home(tmp_path, uuid.uuid4())

    removed = remove_orphan_homes(tmp_path, keep=set())

    assert removed == [orphan]
    assert not orphan.exists()


def test_a_home_with_a_user_is_left_alone(tmp_path: Path) -> None:
    user_id = uuid.uuid4()
    live = make_home(tmp_path, user_id)

    removed = remove_orphan_homes(tmp_path, keep={user_id})

    assert removed == []
    assert (live / "leftover.csv").read_text(encoding="utf-8") == LEFTOVER


def test_only_the_orphans_go(tmp_path: Path) -> None:
    user_id = uuid.uuid4()
    live = make_home(tmp_path, user_id)
    orphan = make_home(tmp_path, uuid.uuid4())

    removed = remove_orphan_homes(tmp_path, keep={user_id})

    assert removed == [orphan]
    assert live.exists()


def test_a_name_that_is_not_a_user_id_is_not_touched(tmp_path: Path) -> None:
    """The rule recognises homes, and refuses to guess about anything else."""
    stranger = tmp_path / "not-a-uuid"
    stranger.mkdir()
    loose = tmp_path / "README.txt"
    loose.write_text("kept\n", encoding="utf-8")

    removed = remove_orphan_homes(tmp_path, keep=set())

    assert removed == []
    assert stranger.exists()
    assert loose.exists()


@pytest.mark.skipif(os.name != "posix", reason="symlinks need privileges on Windows")
def test_a_symlink_is_never_followed(tmp_path: Path) -> None:
    """Recursing through a link would delete a directory outside the root."""
    outside = tmp_path / "outside-the-root"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep me\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / str(uuid.uuid4())).symlink_to(outside)

    removed = remove_orphan_homes(root, keep=set())

    assert removed == []
    assert (outside / "precious.txt").exists()


def test_a_root_that_does_not_exist_is_not_an_error(tmp_path: Path) -> None:
    assert remove_orphan_homes(tmp_path / "missing", keep=set()) == []
