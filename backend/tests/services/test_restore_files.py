import uuid
from pathlib import Path

import pytest

from app.core.config import settings
from app.jobs.runner import JobFailed
from app.services.restore_files import RESTORE_PREFIX, remove_stranded_snapshots, snapshot


def test_restore_snapshot_is_private_and_survives_source_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "USER_STORAGE_ROOT", tmp_path)
    owner = uuid.uuid4()
    folder = tmp_path / str(owner) / "backups"
    folder.mkdir(parents=True)
    source = folder / "source.dump"
    source.write_bytes(b"PGDMPoriginal")
    staged = snapshot(owner, "source.dump")
    try:
        source.write_bytes(b"PGDMPchanged")
        assert staged.parent == tmp_path
        assert staged.read_bytes() == b"PGDMPoriginal"
        assert not staged.is_relative_to(folder.parent)
    finally:
        staged.unlink()


def test_plain_sql_and_path_escape_are_refused_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "USER_STORAGE_ROOT", tmp_path)
    owner = uuid.uuid4()
    folder = tmp_path / str(owner) / "backups"
    folder.mkdir(parents=True)
    (folder / "plain.sql").write_text("CREATE EXTENSION timescaledb;")
    for filename in ["plain.sql", "../plain.sql", "C:plain.sql"]:
        with pytest.raises(JobFailed):
            snapshot(owner, filename)
    assert list(tmp_path.glob(f"{RESTORE_PREFIX}*")) == []


def test_restart_cleanup_does_not_remove_personal_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "USER_STORAGE_ROOT", tmp_path)
    staged = tmp_path / f"{RESTORE_PREFIX}old.dump"
    staged.write_bytes(b"PGDMP")
    personal = tmp_path / str(uuid.uuid4())
    personal.mkdir()
    backup = personal / f"{RESTORE_PREFIX}old.dump"
    backup.write_bytes(b"PGDMP")
    remove_stranded_snapshots()
    assert not staged.exists()
    assert backup.exists()
