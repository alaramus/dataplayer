"""Acting on the backends the Processes report lists.

Against a real server, because the whole subject is what the server does with
a pid: a rule about what `pg_cancel_backend` returns for a pid that has gone
would be this project guessing at PostgreSQL.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import suppress

import psycopg
import pytest

from app.adapters.fetch import FetchRequest
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.system_reports import PROCESSES_REPORT_ID
from app.adapters.row_commands import SupportsRowCommands, UnknownRowCommand
from tests.utils.database import working_postgres_options


def adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


@pytest.fixture
async def idle_backend() -> AsyncGenerator[int]:
    """A connection of our own, so a test can act on something real.

    Its own connection rather than one from the pool: the pool is what every
    other test in this file is reading through, and terminating one of those
    would break whatever else is holding it.
    """
    options = working_postgres_options()
    connection = await psycopg.AsyncConnection.connect(
        host=options["host"],
        port=options["port"],
        dbname=options["database"],
        user=options["user"],
        password=options["password"],
    )
    cursor = await connection.execute("SELECT pg_backend_pid()")
    row = await cursor.fetchone()
    assert row is not None
    try:
        yield int(row[0])
    finally:
        # Not `async with`: leaving that block commits, and committing on a
        # connection the server has already dropped raises. Being dropped is
        # what this fixture exists to have happen to it.
        with suppress(psycopg.Error, OSError):
            await connection.close()


def test_the_processes_report_is_the_only_node_with_commands() -> None:
    source = adapter()

    offered = source.row_commands(PROCESSES_REPORT_ID)

    assert [command.name for command in offered] == [
        "cancel_query",
        "terminate_backend",
    ]
    assert source.row_commands("public.customers") == []
    assert source.row_commands("pg_dataplayer.settings") == []


def test_a_command_names_the_column_that_identifies_a_row() -> None:
    source = adapter()

    for command in source.row_commands(PROCESSES_REPORT_ID):
        assert command.identified_by == "pid"
        assert command.destructive is True
        # Stopping somebody else's work is not what "may write rows" is for.
        assert command.requires == "structure"


async def test_the_column_a_command_names_is_one_the_report_has() -> None:
    """The declaration and the page cannot disagree about the key."""
    source = adapter()

    page = await source.fetch(FetchRequest(node_id=PROCESSES_REPORT_ID, limit=1))

    names = {column.name for column in page.columns}
    for command in source.row_commands(PROCESSES_REPORT_ID):
        assert command.identified_by in names


async def test_the_report_asks_to_be_read_again_and_others_do_not() -> None:
    source = adapter()

    processes = await source.fetch(FetchRequest(node_id=PROCESSES_REPORT_ID, limit=1))
    settings = await source.fetch(
        FetchRequest(node_id="pg_dataplayer.settings", limit=1)
    )

    assert processes.refresh_seconds == 5
    assert settings.refresh_seconds is None


async def test_a_report_withdraws_what_would_take_its_page_away() -> None:
    """A report is a picture of the server, not data somebody is keeping."""
    source = adapter()

    processes = await source.fetch(FetchRequest(node_id=PROCESSES_REPORT_ID, limit=1))
    relation = await source.fetch(FetchRequest(node_id="pg_catalog.pg_class", limit=1))

    assert processes.page_commands == []
    assert set(relation.page_commands) == {
        "download",
        "chart",
        "share",
        "create_relation",
        "query",
    }


async def test_terminating_closes_the_connection_it_named(idle_backend: int) -> None:
    source = adapter()
    assert isinstance(source, SupportsRowCommands)

    result = await source.run_row_command(
        PROCESSES_REPORT_ID, "terminate_backend", [str(idle_backend)]
    )

    assert result.done == 1
    assert result.refused == []
    assert result.message == "1 process closed"
    # The server takes a moment to reap it; what matters is that it goes.
    for _ in range(50):
        page = await source.fetch(
            FetchRequest(node_id=PROCESSES_REPORT_ID, limit=1000)
        )
        pids = {row[0] for row in page.rows}
        if str(idle_backend) not in pids:
            break
        await asyncio.sleep(0.1)
    else:
        pytest.fail("the terminated backend is still listed")


async def test_cancelling_a_backend_that_has_gone_is_reported_not_raised() -> None:
    source = adapter()

    # A pid above the server's ceiling names nothing and never will.
    result = await source.run_row_command(
        PROCESSES_REPORT_ID, "cancel_query", ["2147483647"]
    )

    assert result.done == 0
    assert result.refused == ["2147483647 is no longer running"]
    assert result.message == "0 of 1 process asked to stop"


async def test_a_key_that_is_not_a_process_id_is_refused_alone() -> None:
    """One bad key does not stop the rest: the others are still acted on."""
    source = adapter()

    result = await source.run_row_command(
        PROCESSES_REPORT_ID, "cancel_query", ["not-a-pid", "2147483647"]
    )

    assert result.done == 0
    assert "not-a-pid is not a process id" in result.refused
    assert "2147483647 is no longer running" in result.refused


async def test_a_command_the_node_does_not_offer_does_not_resolve() -> None:
    source = adapter()

    with pytest.raises(UnknownRowCommand):
        await source.run_row_command(
            "public.customers", "terminate_backend", ["1"]
        )


async def test_more_keys_than_the_ceiling_are_refused() -> None:
    source = adapter()

    with pytest.raises(ValueError, match="At most"):
        await source.run_row_command(
            PROCESSES_REPORT_ID, "cancel_query", [str(pid) for pid in range(501)]
        )
