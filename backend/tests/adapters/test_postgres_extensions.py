"""Installing and removing an extension, on the rows of the report that lists them.

It was a pair of actions with a form that asked for a name, next to a table
that already had every name in it. It is now a pair of row commands (D70), the
way the Processes report has had them: tick the rows, run the command.
"""

from collections.abc import AsyncGenerator

import pytest

from app.adapters.fetch import FetchRequest, ScalarFilter
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.system_reports import EXTENSIONS_REPORT_ID, SECTION_ID
from app.adapters.row_commands import UnknownRowCommand
from tests.utils.database import working_postgres_options

# Shipped with every PostgreSQL server and installed by nothing here, so it can
# be put on and taken off again without disturbing anything.
SPARE = "pg_trgm"


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


@pytest.fixture(autouse=True)
async def without_the_spare_extension() -> AsyncGenerator[None]:
    """Leave the server exactly as it was found, whichever way a test ends."""
    yield
    await _adapter().run_row_command(EXTENSIONS_REPORT_ID, "drop_extension", [SPARE])


def _offered(adapter: PostgresAdapter, node_id: str) -> list[str]:
    return [command.name for command in adapter.row_commands(node_id)]


def test_the_commands_are_offered_on_the_rows_of_the_extensions_report() -> None:
    adapter = _adapter()

    assert _offered(adapter, EXTENSIONS_REPORT_ID) == [
        "install_extension",
        "drop_extension",
    ]
    # Each names the column that identifies a row, which is what lets the grid
    # turn a selection into a request without knowing what an extension is.
    assert all(
        command.identified_by == "name"
        for command in adapter.row_commands(EXTENSIONS_REPORT_ID)
    )


def test_they_say_they_change_more_than_the_page() -> None:
    """An extension arrives with schemas and types of its own, and the catalog
    column holds its rows itself (D66)."""
    adapter = _adapter()

    assert all(
        command.changes_structure
        for command in adapter.row_commands(EXTENSIONS_REPORT_ID)
    )
    assert all(
        not command.changes_structure
        for command in adapter.row_commands(f"{SECTION_ID}.processes")
    )


def test_no_other_node_offers_them() -> None:
    adapter = _adapter()

    assert _offered(adapter, f"{SECTION_ID}.roles") == []
    assert _offered(adapter, SECTION_ID) == []
    assert _offered(adapter, "public.connector") == []


async def test_a_command_this_node_does_not_offer_does_not_resolve() -> None:
    with pytest.raises(UnknownRowCommand):
        await _adapter().run_row_command(
            f"{SECTION_ID}.roles", "install_extension", [SPARE]
        )


async def test_an_extension_is_installed_and_removed_again() -> None:
    adapter = _adapter()

    installed = await adapter.run_row_command(
        EXTENSIONS_REPORT_ID, "install_extension", [SPARE]
    )

    assert installed.done == 1
    assert installed.refused == []
    assert await _installed(adapter, SPARE) is True

    removed = await adapter.run_row_command(
        EXTENSIONS_REPORT_ID, "drop_extension", [SPARE]
    )

    assert removed.done == 1
    assert await _installed(adapter, SPARE) is False


async def test_a_name_this_server_does_not_offer_changes_nothing() -> None:
    """The text of a row selects a row; it never reaches the statement.

    A refusal per key rather than one failure for the request: the grid sends
    what was ticked, and a person who ticked four rows wants to read which of
    the four the server would not do.
    """
    adapter = _adapter()

    answer = await adapter.run_row_command(
        EXTENSIONS_REPORT_ID,
        "install_extension",
        ['x"; DROP SCHEMA public CASCADE; --', SPARE],
    )

    assert answer.done == 1
    assert len(answer.refused) == 1
    assert "not offered" in answer.refused[0]
    # The schema the injection named is still there, which is the point.
    assert await _installed(adapter, SPARE) is True


async def test_removing_something_that_is_not_installed_is_refused() -> None:
    answer = await _adapter().run_row_command(
        EXTENSIONS_REPORT_ID, "drop_extension", [SPARE]
    )

    assert answer.done == 0
    assert answer.refused == [f'"{SPARE}" is not installed']


async def test_installing_one_that_is_already_installed_is_refused() -> None:
    adapter = _adapter()
    await adapter.run_row_command(EXTENSIONS_REPORT_ID, "install_extension", [SPARE])

    answer = await adapter.run_row_command(
        EXTENSIONS_REPORT_ID, "install_extension", [SPARE]
    )

    assert answer.done == 0
    assert "not offered" in answer.refused[0]


async def test_more_than_the_ceiling_is_refused_before_anything_runs() -> None:
    from app.adapters.postgres.row_commands import MAX_EXTENSIONS

    with pytest.raises(ValueError, match="at a time"):
        await _adapter().run_row_command(
            EXTENSIONS_REPORT_ID,
            "install_extension",
            [SPARE] * (MAX_EXTENSIONS + 1),
        )


async def _installed(adapter: PostgresAdapter, name: str) -> bool:
    result = await adapter.fetch(
        FetchRequest(
            node_id=EXTENSIONS_REPORT_ID,
            limit=5,
            filters=[ScalarFilter(column="name", op="eq", value=name)],
        )
    )
    installed_at = [column.name for column in result.columns].index("installed")
    return result.rows[0][installed_at] == "true"
