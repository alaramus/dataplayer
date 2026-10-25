"""A ClickHouse database copied out and put back, and its counters (D278, D279).

The backup program is a Python script with no dependency of its own, so these
tests run it here, against the suite's server, with this interpreter rather
than in the image a job would start it in.
"""

import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import anyio
import pytest
from anyio import to_thread

from app.adapters.clickhouse.adapter import ClickhouseAdapter
from app.adapters.clickhouse.backup import HEADING
from app.adapters.database_ids import relation_id
from app.adapters.fetch import FetchRequest, Sort
from app.adapters.metrics import SupportsMetrics
from app.adapters.protocol import BackupProgram, SupportsBackup
from tests.adapters.clickhouse_fixture import (
    DATABASE,
    ODD,
    adapter,
    build,
    run,
    tear_down,
)
from tests.utils.services import CLICKHOUSE

_DB = f"`{DATABASE}`"


@pytest.fixture
async def server() -> AsyncIterator[None]:
    CLICKHOUSE.require()
    await build()
    yield
    await tear_down()


def _source() -> ClickhouseAdapter:
    return adapter(database=DATABASE)


def _run(program: BackupProgram) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # the script this module tests, with this interpreter
        (sys.executable, *program.argv[1:]),
        env={**program.environment, "SYSTEMROOT": "C:\\Windows"},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


async def _ran(program: BackupProgram) -> subprocess.CompletedProcess[str]:
    return await to_thread.run_sync(_run, program)


async def _rows(source: ClickhouseAdapter, name: str, column: str) -> list[list[str | None]]:
    page = await source.fetch(
        FetchRequest(node_id=relation_id(DATABASE, name), limit=50, sort=[Sort(column=column)])
    )
    return page.rows


async def _everything(source: ClickhouseAdapter) -> list[list[list[str | None]]]:
    return [
        await _rows(source, "items", "id"),
        await _rows(source, "dupes", "b"),
        await _rows(source, "journal", "line"),
        await _rows(source, ODD, "x{p1:Int8}"),
        await _rows(source, "item_ids", "id"),
        await _rows(source, "item_labels", "id"),
    ]


@pytest.mark.usefixtures("server")
async def test_the_password_travels_in_the_environment_only() -> None:
    source = adapter(database=DATABASE)
    assert isinstance(source, SupportsBackup)
    password = source._session.options.password.get_secret_value()  # type: ignore[union-attr]  # the fixture's options carry one

    for program in (
        await source.backup_program(into="/x.backup"),
        await source.restore_program(from_file="/x.backup"),
        await source.restore_inventory_program(from_file="/x.backup"),
    ):
        assert program.image == "python:3.14-slim"
        assert program.environment == {"CLICKHOUSE_PASSWORD": password}
        assert not any(password in argument for argument in program.argv)
        assert program.argv[-2:] == (DATABASE, "/x.backup")


async def test_a_connection_without_a_database_is_not_offered() -> None:
    offer = await adapter(database="").backup_availability()

    assert not offer.available and offer.reason


@pytest.mark.usefixtures("server")
async def test_a_database_comes_back_as_it_was(tmp_path: Path) -> None:
    source = _source()
    before = await _everything(source)
    archive = str(tmp_path / "lab.backup")

    dumped = await _ran(await source.backup_program(into=archive))
    assert dumped.returncode == 0, dumped.stdout + dumped.stderr
    written = await anyio.Path(archive).read_bytes()
    assert written.startswith(HEADING)
    assert source.restore_archive_reason(written[:64]) is None

    inventory = await _ran(await source.restore_inventory_program(from_file=archive))
    assert inventory.returncode == 0, inventory.stdout + inventory.stderr
    source.validate_restore_inventory(inventory.stdout.splitlines())

    await run(
        f"DROP TABLE {_DB}.journal",
        f"DROP TABLE {_DB}.item_labels",
        f"INSERT INTO {_DB}.dupes VALUES (9, 'extra')",
        f"INSERT INTO {_DB}.items (id, amount, made, day, uid, addr) "
        "VALUES (4, 1, now(), today(), generateUUIDv4(), '1.1.1.1')",
    )
    restored = await _ran(await source.restore_program(from_file=archive))
    assert restored.returncode == 0, restored.stdout + restored.stderr

    # The materialized view's rows came back once: from the backup, not again
    # from the table's rows being loaded.
    assert await _everything(source) == before


@pytest.mark.usefixtures("server")
async def test_a_backup_cut_short_or_of_another_database_is_refused(tmp_path: Path) -> None:
    source = _source()
    archive = anyio.Path(tmp_path / "lab.backup")
    dumped = await _ran(await source.backup_program(into=str(archive)))
    assert dumped.returncode == 0, dumped.stdout + dumped.stderr

    whole = await archive.read_bytes()
    await archive.write_bytes(whole[: len(whole) - 40])
    inventory = await _ran(await source.restore_inventory_program(from_file=str(archive)))
    with pytest.raises(ValueError, match="not whole"):
        source.validate_restore_inventory(inventory.stdout.splitlines())

    await archive.write_bytes(whole)
    inventory = await _ran(await source.restore_inventory_program(from_file=str(archive)))
    elsewhere = adapter(database="default")
    await elsewhere.restore_program(from_file=str(archive))
    with pytest.raises(ValueError, match="restored into a connection naming it"):
        elsewhere.validate_restore_inventory(inventory.stdout.splitlines())

    assert source.restore_archive_reason(b"-- MySQL dump 10.13") is not None


@pytest.mark.usefixtures("server")
async def test_a_newer_server_s_backup_is_refused() -> None:
    source = _source()
    await source.restore_program(from_file="/x.backup")

    with pytest.raises(ValueError, match="newer than this server"):
        source.validate_restore_inventory(
            ["backup", '{"server": "99.1.1.1"}', f'{{"database": "{DATABASE}"}}', "whole"]
        )


@pytest.mark.usefixtures("server")
async def test_the_server_s_counters_are_read_and_every_preset_widget_has_a_series() -> None:
    source = _source()
    assert isinstance(source, SupportsMetrics)

    samples = await source.metric_samples()

    read = {(sample.metric, sample.field) for sample in samples}
    assert ("statements", "select") in read
    assert ("sessions", "running_queries") in read
    assert ("database", "size") in read
    size = next(sample for sample in samples if sample.metric == "database")
    assert size.value > 0
    counters = {sample.field for sample in samples if sample.counter}
    assert {"select", "insert", "read", "inserted"} <= counters
    [preset] = ClickhouseAdapter.metric_presets()
    assert {recipe.metric for recipe in preset.recipes} <= {sample.metric for sample in samples}
