"""Stopping what a connection runs, from the Processes report (D70, D237).

Against real servers, because the subject is what the server does with a
connection id: a rule about what KILL says of one that has gone would be this
project guessing at MySQL.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress

import aiomysql
import pymysql
import pytest

from app.adapters.fetch import FetchRequest
from app.adapters.mysql import ids
from app.adapters.mysql.reports import PROCESSES_REPORT_ID
from app.adapters.row_commands import SupportsRowCommands, UnknownRowCommand
from tests.adapters.mysql_fixture import TARGETS, Target


@pytest.fixture(params=TARGETS, ids=lambda target: target.flavour)
def target(request: pytest.FixtureRequest) -> Target:
    chosen: Target = request.param
    chosen.server.require()
    return chosen


@pytest.fixture
async def own_connection(target: Target) -> AsyncIterator[tuple[aiomysql.Connection, int]]:
    """A connection of the test's own, and its id: what a command acts on.

    Not one of the adapter's pool, which every other read goes through.
    """
    options = target.options()
    connection = await aiomysql.connect(
        host=options.host,
        port=options.port,
        user=options.user,
        password=options.password.get_secret_value(),
        autocommit=True,
    )
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT CONNECTION_ID()")
        (number,) = await cursor.fetchone()
    try:
        yield connection, int(number)
    finally:
        with suppress(pymysql.err.MySQLError, OSError):
            connection.close()


def test_the_processes_report_is_the_only_node_with_commands(target: Target) -> None:
    source = target.adapter()

    offered = source.row_commands(PROCESSES_REPORT_ID)

    assert [command.name for command in offered] == ["kill_query", "kill_connection"]
    assert source.row_commands(ids.relation_id("mysql", "user")) == []
    for command in offered:
        assert command.identified_by == "id"
        assert command.destructive is True
        # Stopping somebody else's work is not what "may write rows" is for.
        assert command.requires == "structure"
        assert command.applies_when is None


async def test_the_column_a_command_names_is_one_the_report_has(target: Target) -> None:
    source = target.adapter()

    page = await source.fetch(FetchRequest(node_id=PROCESSES_REPORT_ID, limit=1))

    names = {column.name for column in page.columns}
    for command in source.row_commands(PROCESSES_REPORT_ID):
        assert command.identified_by in names


async def test_cancelling_stops_the_statement_and_keeps_the_connection(
    target: Target, own_connection: tuple[aiomysql.Connection, int]
) -> None:
    connection, number = own_connection

    async def sleep() -> object:
        """What the statement ended with: MySQL's SLEEP answers 1 when it is
        interrupted, MariaDB's raises that it was."""
        try:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT SLEEP(30)")
                return (await cursor.fetchone())[0]
        except pymysql.err.OperationalError as exc:
            return exc.args[0]

    sleeping = asyncio.create_task(sleep())
    await asyncio.sleep(0.5)
    source = target.adapter()
    assert isinstance(source, SupportsRowCommands)

    result = await source.run_row_command(PROCESSES_REPORT_ID, "kill_query", [str(number)])

    assert result.done == 1
    assert await asyncio.wait_for(sleeping, 5) in (1, 1317)
    async with connection.cursor() as cursor:
        await cursor.execute("SELECT 1")
        assert (await cursor.fetchone())[0] == 1


async def test_terminating_closes_the_connection_it_named(
    target: Target, own_connection: tuple[aiomysql.Connection, int]
) -> None:
    connection, number = own_connection

    result = await target.adapter().run_row_command(
        PROCESSES_REPORT_ID, "kill_connection", [str(number)]
    )

    assert result.done == 1
    assert result.refused == []
    with pytest.raises((pymysql.err.OperationalError, pymysql.err.InterfaceError)):
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT 1")


async def test_a_connection_that_has_gone_is_refused_by_name(target: Target) -> None:
    result = await target.adapter().run_row_command(
        PROCESSES_REPORT_ID, "kill_connection", ["4000000000"]
    )

    assert result.done == 0
    assert result.refused == ["4000000000: it has already ended"]
    assert result.message == "0 of 1 connections closed"


@pytest.mark.parametrize("key", ["1; DROP TABLE x", "-1", "1.5", ""])
async def test_a_key_is_a_whole_number_or_nothing_runs(target: Target, key: str) -> None:
    with pytest.raises(ValueError):
        await target.adapter().run_row_command(PROCESSES_REPORT_ID, "kill_query", [key])


async def test_an_empty_or_huge_choice_is_refused(target: Target) -> None:
    source = target.adapter()

    with pytest.raises(ValueError):
        await source.run_row_command(PROCESSES_REPORT_ID, "kill_query", [])
    with pytest.raises(ValueError):
        await source.run_row_command(
            PROCESSES_REPORT_ID, "kill_query", [str(n) for n in range(1, 502)]
        )


async def test_a_command_is_found_only_where_it_is_offered(target: Target) -> None:
    source = target.adapter()

    with pytest.raises(UnknownRowCommand):
        await source.run_row_command(PROCESSES_REPORT_ID, "drop_everything", ["1"])
    with pytest.raises(UnknownRowCommand):
        await source.run_row_command(ids.relation_id("mysql", "user"), "kill_query", ["1"])
