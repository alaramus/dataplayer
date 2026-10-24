"""What copies a SQLite file out and puts it back (D87, D260).

The program is a script for Python's `sqlite3`, so the tests run it with the
Python running them rather than in its container: the same script, the same
online backup, without a container runtime.
"""

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.adapters.protocol import BackupProgram, SupportsBackup
from app.adapters.sqlite.adapter import SqliteAdapter
from app.adapters.sqlite.backup import IMAGE
from app.adapters.sqlite.options import SqliteOptions
from tests.adapters.sqlite_fixture import FILE, build


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


@pytest.fixture
def adapter(home: Path) -> SqliteAdapter:
    return SqliteAdapter(SqliteOptions(path=FILE), home)


def _run(program: BackupProgram) -> list[str]:
    assert program.argv[0] == "python"
    done = subprocess.run(  # noqa: S603 — the program this source names, run with this Python
        [sys.executable, *program.argv[1:]], capture_output=True, text=True, check=True, timeout=60
    )
    return done.stdout.splitlines()


def _labels(path: Path) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(path)
    try:
        return connection.execute("SELECT id, name FROM labels ORDER BY id").fetchall()
    finally:
        connection.close()


async def test_a_file_is_copied_out_checked_and_put_back(adapter: SqliteAdapter, home: Path) -> None:
    assert isinstance(adapter, SupportsBackup)
    backup = home / "backups" / "shop.dump"
    backup.parent.mkdir()

    out = await adapter.backup_program(into=str(backup))
    _run(out)
    connection = sqlite3.connect(home / FILE)
    connection.execute("UPDATE labels SET name = 'blue' WHERE id = 1")
    connection.commit()
    connection.close()
    inventory = _run(await adapter.restore_inventory_program(from_file=str(backup)))
    adapter.validate_restore_inventory(inventory)
    back = await adapter.restore_program(from_file=str(backup))
    _run(back)

    assert out.image == IMAGE
    assert out.writes_storage is False
    # A restore writes the file, which is in the storage.
    assert back.writes_storage is True
    assert adapter.restore_archive_reason(backup.read_bytes()[:64]) is None
    assert inventory[0] == "ok"
    assert _labels(home / FILE) == [(1, "red"), (2, "green")]


async def test_what_is_not_a_whole_sqlite_file_is_refused(adapter: SqliteAdapter) -> None:
    assert adapter.restore_archive_reason(b"-- MySQL dump 10.13") == "This file is not a SQLite backup"
    with pytest.raises(ValueError, match="damaged"):
        adapter.validate_restore_inventory(["*** in database main ***", "Page 3: btreeInitPage() returns error code 11"])
    with pytest.raises(ValueError, match="damaged"):
        adapter.validate_restore_inventory([])


async def test_a_file_that_is_not_there_is_not_offered(home: Path) -> None:
    missing = SqliteAdapter(SqliteOptions(path="data/none.db"), home)

    offer = await missing.backup_availability()

    assert offer.available is False
    assert offer.reason == "The database file does not exist"
    with pytest.raises(ValueError, match="does not exist"):
        await missing.backup_program(into="/data/users/x/backups/none.dump")
