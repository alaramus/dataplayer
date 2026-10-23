import uuid
from pathlib import Path

import pytest

from app.adapters.mysql.backup import MysqlBackup
from app.adapters.postgres.backup import PostgresBackup
from app.core.config import settings
from app.jobs.runner import JobFailed
from app.services.restore_files import (
    RESTORE_PREFIX,
    remove_stranded_snapshots,
    snapshot,
)


def _postgres(head: bytes) -> str | None:
    """What PostgreSQL says of a file's first bytes, without a server to ask."""
    return PostgresBackup.restore_archive_reason(None, head)  # type: ignore[arg-type]  # reads only its argument


def _mysql(head: bytes) -> str | None:
    return MysqlBackup.restore_archive_reason(None, head)  # type: ignore[arg-type]  # reads only its argument


def test_restore_snapshot_is_private_and_survives_source_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "USER_STORAGE_ROOT", tmp_path)
    owner = uuid.uuid4()
    folder = tmp_path / str(owner) / "backups"
    folder.mkdir(parents=True)
    source = folder / "source.dump"
    source.write_bytes(b"PGDMPoriginal")
    staged = snapshot(owner, "source.dump", _postgres)
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
            snapshot(owner, filename, _postgres)
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


def test_which_files_are_backups_is_the_source_s_to_say(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A MySQL dump is text, and PostgreSQL's signature is not asked of it."""
    monkeypatch.setattr(settings, "USER_STORAGE_ROOT", tmp_path)
    owner = uuid.uuid4()
    folder = tmp_path / str(owner) / "backups"
    folder.mkdir(parents=True)
    (folder / "shop.dump").write_text(
        "/*M!999999\\- enable the sandbox mode */ \n-- MariaDB dump 10.19-11.4.13-MariaDB\n"
    )

    staged = snapshot(owner, "shop.dump", _mysql)
    staged.unlink()
    with pytest.raises(JobFailed, match="PostgreSQL custom archive"):
        snapshot(owner, "shop.dump", _postgres)
    (folder / "pg.dump").write_bytes(b"PGDMP")
    with pytest.raises(JobFailed, match="not a MySQL or MariaDB backup"):
        snapshot(owner, "pg.dump", _mysql)
