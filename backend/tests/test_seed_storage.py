import os
import uuid
from pathlib import Path

import pytest

from app.seed_storage import SAMPLE_ROWS, remove_orphan_homes, write_samples
from app.users import storage


def test_samples_cover_the_native_file_viewers(tmp_path: Path) -> None:
    """Tabular, plain-text and image files all have examples."""
    write_samples(tmp_path)

    names = {path.name for path in tmp_path.rglob("*")}
    assert {"sample.csv", "sample.tsv", "notes.txt", "logo.png", "reports"} <= names


def test_a_sample_file_pairs_with_the_demonstration_schema(tmp_path: Path) -> None:
    """A declared reference needs two ends that match (D106).

    The file's slugs are the ones `postgres_complex_data.sql` inserts, so
    drawing a reference between them and following it lands on a row rather
    than on an empty page.
    """
    write_samples(tmp_path)

    for name in ("accounts.csv", "renewals.csv"):
        rows = (tmp_path / name).read_text(encoding="utf-8").splitlines()
        assert rows[0].split(",")[0] == "slug"
        assert [row.split(",")[0] for row in rows[1:]] == ["northstar-labs", "blue-orbit"]


def test_samples_cover_both_structured_viewers(tmp_path: Path) -> None:
    """A document, one value per line, and invalid source text (D47)."""
    write_samples(tmp_path)

    names = {path.name for path in tmp_path.rglob("*")}
    assert {"people.json", "events.jsonl", "broken.json"} <= names


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


@pytest.fixture(autouse=True)
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A root of this test's own.

    The session-wide root from conftest holds the homes of every user the run
    has created, and these tests delete whatever has no user.
    """
    root = tmp_path / "user-storage"
    root.mkdir()
    monkeypatch.setattr(storage.settings, "USER_STORAGE_ROOT", root)
    return root


def make_home(user_id: uuid.UUID) -> Path:
    home = storage.create_home(user_id)
    (home / "leftover.csv").write_text(LEFTOVER, encoding="utf-8")
    return home


def test_a_home_without_a_user_is_removed() -> None:
    """What the test suite leaves behind: the user is gone, the files are not."""
    user_id = uuid.uuid4()
    home = make_home(user_id)

    removed = remove_orphan_homes(keep=set())

    assert removed == [user_id]
    assert not home.exists()


def test_a_home_with_a_user_is_left_alone() -> None:
    user_id = uuid.uuid4()
    live = make_home(user_id)

    removed = remove_orphan_homes(keep={user_id})

    assert removed == []
    assert (live / "leftover.csv").read_text(encoding="utf-8") == LEFTOVER


def test_only_the_orphans_go() -> None:
    user_id = uuid.uuid4()
    live = make_home(user_id)
    orphan_id = uuid.uuid4()
    orphan = make_home(orphan_id)

    removed = remove_orphan_homes(keep={user_id})

    assert removed == [orphan_id]
    assert not orphan.exists()
    assert live.exists()


def test_a_name_that_is_not_a_user_id_is_not_touched(storage_root: Path) -> None:
    """The rule recognises homes, and refuses to guess about anything else."""
    stranger = storage_root / "not-a-uuid"
    stranger.mkdir()
    loose = storage_root / "README.txt"
    loose.write_text("kept\n", encoding="utf-8")

    removed = remove_orphan_homes(keep=set())

    assert removed == []
    assert stranger.exists()
    assert loose.exists()


@pytest.mark.skipif(os.name != "posix", reason="symlinks need privileges on Windows")
def test_a_symlink_is_never_followed(
    storage_root: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Recursing through a link would delete a directory outside the root."""
    outside = tmp_path_factory.mktemp("outside-the-root")
    (outside / "precious.txt").write_text("keep me\n", encoding="utf-8")
    (storage_root / str(uuid.uuid4())).symlink_to(outside)

    removed = remove_orphan_homes(keep=set())

    assert removed == []
    assert (outside / "precious.txt").exists()


def test_a_root_that_does_not_exist_is_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(storage.settings, "USER_STORAGE_ROOT", tmp_path / "missing")

    assert remove_orphan_homes(keep=set()) == []
