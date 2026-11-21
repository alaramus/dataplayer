"""What copies a DuckDB file out and puts it back (D87, D401).

The program is a plain Python script, so the tests run it with the Python
running them rather than in its container: the same script, without a
container runtime.
"""

import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from app.adapters.duckdb.adapter import DuckdbAdapter
from app.adapters.duckdb.backup import IMAGE
from app.adapters.duckdb.options import DuckdbOptions
from app.adapters.protocol import BackupProgram, SupportsBackup
from tests.adapters.duckdb_fixture import FILE, build


@pytest.fixture
def home(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


@pytest.fixture
def adapter(home: Path) -> DuckdbAdapter:
    return DuckdbAdapter(DuckdbOptions(path=FILE), home)


def _run(program: BackupProgram, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    assert program.argv[0] == "python"
    return subprocess.run(  # noqa: S603 — the program this source names, run with this Python
        [sys.executable, *program.argv[1:]], capture_output=True, text=True, check=check, timeout=60
    )


def _labels(path: Path) -> list[tuple[object, ...]]:
    connection = duckdb.connect(str(path))
    try:
        return connection.execute("SELECT id, name FROM labels ORDER BY id").fetchall()
    finally:
        connection.close()


async def test_a_file_is_copied_out_checked_and_put_back(adapter: DuckdbAdapter, home: Path) -> None:
    assert isinstance(adapter, SupportsBackup)
    backup = home / "backups" / "shop.duckdb"
    backup.parent.mkdir()

    out = await adapter.backup_program(into=str(backup))
    _run(out)
    connection = duckdb.connect(str(home / FILE))
    connection.execute("INSERT INTO labels VALUES (3, 'blue')")
    connection.close()
    inventory = _run(await adapter.restore_inventory_program(from_file=str(backup))).stdout.splitlines()
    adapter.validate_restore_inventory(inventory)
    back = await adapter.restore_program(from_file=str(backup))
    _run(back)

    assert out.image == IMAGE
    assert out.writes_storage is False and back.writes_storage is True
    assert adapter.restore_archive_reason(backup.read_bytes()[:64]) is None
    assert _labels(home / FILE) == [(1, "red"), (2, "green")]
    assert not (home / "data" / "shop.duckdb.restoring").exists()


async def test_a_file_another_program_writes_is_not_copied(adapter: DuckdbAdapter, home: Path) -> None:
    out = await adapter.backup_program(into=str(home / "copy.duckdb"))
    (home / f"{FILE}.wal").write_bytes(b"pending")

    done = _run(out, check=False)

    assert done.returncode == 3 and "in use" in done.stderr
    assert not (home / "copy.duckdb").exists()


async def test_what_is_not_a_duckdb_file_is_refused(adapter: DuckdbAdapter, home: Path) -> None:
    other = home / "other.db"
    other.write_bytes(b"SQLite format 3\x00" + bytes(100))

    inventory = _run(await adapter.restore_inventory_program(from_file=str(other))).stdout.splitlines()

    assert adapter.restore_archive_reason(other.read_bytes()[:64]) == "This file is not a DuckDB backup"
    with pytest.raises(ValueError, match="not a DuckDB backup"):
        adapter.validate_restore_inventory(inventory)


async def test_a_file_that_is_not_there_is_not_offered(home: Path) -> None:
    missing = DuckdbAdapter(DuckdbOptions(path="data/none.duckdb"), home)

    offer = await missing.backup_availability()

    assert offer.available is False
    with pytest.raises(ValueError):
        await missing.backup_program(into="/data/users/x/backups/none.duckdb")
