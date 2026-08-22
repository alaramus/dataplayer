import os
import uuid
from pathlib import Path

import pytest

from app.users import storage


@pytest.fixture(autouse=True)
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(storage.settings, "USER_STORAGE_ROOT", tmp_path)
    return tmp_path


def test_home_dir_is_named_by_user_id(storage_root: Path) -> None:
    user_id = uuid.uuid4()

    assert storage.home_dir(user_id) == storage_root / str(user_id)


def test_create_home_creates_the_directory() -> None:
    user_id = uuid.uuid4()

    home = storage.create_home(user_id)

    assert home.is_dir()


def test_create_home_keeps_existing_content() -> None:
    """A second call must not disturb what is already in the directory."""
    user_id = uuid.uuid4()
    home = storage.create_home(user_id)
    (home / "notes.txt").write_text("kept")

    storage.create_home(user_id)

    assert (home / "notes.txt").read_text() == "kept"


@pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX-only")
def test_create_home_is_private_to_its_owner() -> None:
    home = storage.create_home(uuid.uuid4())

    assert home.stat().st_mode & 0o777 == 0o700


def test_remove_home_takes_the_directory_and_its_contents() -> None:
    user_id = uuid.uuid4()
    home = storage.create_home(user_id)
    (home / "reports").mkdir()
    (home / "reports" / "q3.csv").write_text("quarter,revenue")

    storage.remove_home(user_id)

    assert not home.exists()


def test_remove_home_is_idempotent() -> None:
    """A user whose directory was never created is not an error."""
    user_id = uuid.uuid4()

    storage.remove_home(user_id)
    storage.remove_home(user_id)

    assert not storage.home_dir(user_id).exists()


def test_remove_home_leaves_another_user_alone(storage_root: Path) -> None:
    neighbour = storage.create_home(uuid.uuid4())

    storage.remove_home(uuid.uuid4())

    assert neighbour.is_dir()
    assert storage_root.is_dir()


@pytest.mark.skipif(os.name != "posix", reason="symlinks need privileges on Windows")
def test_remove_home_does_not_follow_a_symlink(
    tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Deleting through a link would reach outside the root."""
    outside = tmp_path_factory.mktemp("outside-the-root")
    (outside / "precious.txt").write_text("keep me")
    user_id = uuid.uuid4()
    storage.home_dir(user_id).symlink_to(outside)

    storage.remove_home(user_id)

    assert (outside / "precious.txt").exists()
