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
