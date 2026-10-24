"""What program copies a MySQL database out and puts it back (D87, D240).

The programs themselves run in containers a job starts; what is tested here is
what the source says to run, against the real servers that decide the image.
"""

from collections.abc import AsyncIterator

import pytest

from app.adapters.mysql.adapter import MysqlAdapter
from app.adapters.protocol import SupportsBackup
from tests.adapters.mysql_fixture import DATABASE, TARGETS, Target, build, tear_down

MYSQL_HEAD = [
    "-- MySQL dump 10.13  Distrib 8.4.11, for Linux (x86_64)",
    "--",
    "-- Host: mysql    Database: shop",
]
MARIADB_HEAD = [
    "/*M!999999\\- enable the sandbox mode */ ",
    "-- MariaDB dump 10.19-11.4.13-MariaDB, for debian-linux-gnu (x86_64)",
    "--",
]


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour, scope="module")
async def target(request: pytest.FixtureRequest) -> AsyncIterator[Target]:
    chosen: Target = request.param
    chosen.server.require()
    await build(chosen)
    yield chosen
    await tear_down(chosen)


def _adapter(target: Target, **override: object) -> MysqlAdapter:
    return target.adapter(**{"database": DATABASE, **override})


async def test_a_database_is_dumped_by_its_own_family_and_release(target: Target) -> None:
    source = _adapter(target)
    assert isinstance(source, SupportsBackup)

    program = await source.backup_program(into="/storage/owner/backups/shop.dump")

    family = "mariadb" if target.flavour == "mariadb" else "mysql"
    assert program.image.startswith(f"{family}:")
    assert program.image.count(".") == 1
    assert program.argv[0] == ("mariadb-dump" if family == "mariadb" else "mysqldump")
    assert "--single-transaction" in program.argv
    assert "--result-file=/storage/owner/backups/shop.dump" in program.argv
    assert program.argv[-1] == DATABASE
    assert ("--set-gtid-purged=OFF" in program.argv) is (family == "mysql")


async def test_the_password_travels_in_the_environment_only(target: Target) -> None:
    source = _adapter(target)
    password = target.options().password.get_secret_value()

    for program in (
        await source.backup_program(into="/x.dump"),
        await source.restore_program(from_file="/x.dump"),
    ):
        assert program.environment == {"MYSQL_PWD": password}
        assert not any(password in argument for argument in program.argv)


async def test_a_restore_reads_the_file_into_the_connection_s_database(target: Target) -> None:
    program = await _adapter(target).restore_program(from_file="/storage/a.dump")

    assert f"--database={DATABASE}" in program.argv
    assert program.argv[-1] == "--execute=source /storage/a.dump"


async def test_a_connection_without_a_database_is_not_offered(target: Target) -> None:
    source = _adapter(target, database="")

    offer = await source.backup_availability()

    assert not offer.available and offer.reason
    with pytest.raises(ValueError):
        await source.backup_program(into="/x.dump")


async def test_a_database_named_like_an_option_is_not_offered(target: Target) -> None:
    offer = await _adapter(target, database="-e").backup_availability()

    assert not offer.available


async def test_only_a_dump_of_this_family_is_restored(target: Target) -> None:
    source = _adapter(target)
    await source.restore_inventory_program(from_file="/x.dump")
    own, other = (MARIADB_HEAD, MYSQL_HEAD) if target.flavour == "mariadb" else (MYSQL_HEAD, MARIADB_HEAD)

    source.validate_restore_inventory(own)
    with pytest.raises(ValueError, match="is restored into"):
        source.validate_restore_inventory(other)
    with pytest.raises(ValueError, match="not a MySQL or MariaDB backup"):
        source.validate_restore_inventory(["PGDMP", "something else"])
    with pytest.raises(ValueError):
        source.validate_restore_inventory([])


async def test_the_archive_is_read_by_its_first_lines(target: Target) -> None:
    program = await _adapter(target).restore_inventory_program(from_file="/storage/a.dump")

    assert program.argv == ("head", "-n", "5", "/storage/a.dump")
    assert "MYSQL_PWD" not in program.environment
