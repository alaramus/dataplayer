"""Making, renaming, handing over and removing a tablespace (D210)."""

from collections.abc import AsyncGenerator, Callable
from uuid import uuid4

import pytest
from psycopg import sql

from app.adapters.actions import ActionRefused, OffersFieldHints
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import ROLES_REPORT_ID, TABLESPACES_REPORT_ID
from tests.utils.database import working_postgres_options


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


def _session() -> PostgresSession:
    return PostgresSession(PostgresUserPassword(**working_postgres_options()))


async def _superuser() -> bool:
    rows = await _session().query("SELECT rolsuper AS yes FROM pg_catalog.pg_roles WHERE rolname = current_user")
    return bool(rows and rows[0]["yes"])


@pytest.fixture
async def directory() -> AsyncGenerator[Callable[[], str]]:
    """Paths on the database server for tablespaces a test makes.

    A test makes the directory itself with `_mkdir`, the way the Timescale matrix makes one, through the server's shell,
    which only a superuser may use; the product never does this (D210). Every
    tablespace in them is dropped however the test ends.
    """
    if not await _superuser():
        pytest.skip("Making a directory on the database server needs a superuser connection")
    paths: list[str] = []

    def path() -> str:
        paths.append(f"/tmp/dp_space_{uuid4().hex[:8]}")
        return paths[-1]

    yield path
    session = _session()
    for made in paths:
        for row in await session.query(
            "SELECT spcname AS name FROM pg_catalog.pg_tablespace WHERE pg_catalog.pg_tablespace_location(oid) = %s",
            (made,),
        ):
            await session.schema_change(
                sql.SQL("DROP TABLESPACE {}").format(sql.Identifier(str(row["name"]))).as_string(), alone=True,
            )


async def _mkdir(path: str) -> None:
    await _session().schema_change(
        sql.SQL("COPY (SELECT 1) TO PROGRAM {}").format(sql.Literal(f"mkdir -p {path}")).as_string(),
        alone=True,
    )


async def _location(name: str) -> str | None:
    rows = await _session().query(
        "SELECT pg_catalog.pg_tablespace_location(oid) AS location FROM pg_catalog.pg_tablespace WHERE spcname = %s",
        (name,),
    )
    return str(rows[0]["location"]) if rows else None


async def test_the_report_offers_new_and_the_rows_offer_the_rest() -> None:
    adapter = _adapter()
    assert [action.name for action in await adapter.available(TABLESPACES_REPORT_ID)] == [
        "create_tablespace", "rename_tablespace", "change_tablespace_owner",
    ]
    assert "create_tablespace" not in [action.name for action in await adapter.available(ROLES_REPORT_ID)]
    # New above the rows; renaming and handing over only over one picked row (D209).
    assert adapter.action("create_tablespace").offered_in == "rows"
    assert adapter.action("rename_tablespace").offered_in == "picked"
    assert {action.action for action in adapter.picked_rows_actions(TABLESPACES_REPORT_ID)} == {
        "rename_tablespace", "change_tablespace_owner",
    }
    for name in ("create_tablespace", "rename_tablespace", "change_tablespace_owner"):
        assert adapter.action(name).requires == "own"
    (remove,) = adapter.row_commands(TABLESPACES_REPORT_ID)
    assert (remove.name, remove.requires, remove.destructive) == ("drop_tablespace", "own", True)
    # pg_default and pg_global are PostgreSQL's own.
    assert remove.applies_when is not None and remove.applies_when.equals == "false"


async def test_a_tablespace_is_made_renamed_handed_over_and_removed(directory: Callable[[], str]) -> None:
    adapter = _adapter()
    path = directory()
    await _mkdir(path)
    name = f"dp_space_{uuid4().hex[:8]}"
    create = adapter.action("create_tablespace")
    assert isinstance(create, OffersFieldHints)
    owners = [choice.value for choice in (await create.field_hints(TABLESPACES_REPORT_ID)).choices["owner"]]
    assert owners[0] == "" and "pg_read_all_data" not in owners

    result = await create.perform(TABLESPACES_REPORT_ID, {"name": name, "location": path, "owner": ""})
    assert result.message == f"Tablespace {name} created at {path}"
    assert await _location(name) == path

    target = await adapter.resolve_picked_rows(TABLESPACES_REPORT_ID, "rename_tablespace", [[name]])
    assert target.params == {"tablespace": name}
    renamed = f"{name}_r"
    await adapter.action("rename_tablespace").perform(
        TABLESPACES_REPORT_ID, {**target.params, "new_name": renamed},
    )
    assert await _location(name) is None and await _location(renamed) == path

    me = str((await _session().query("SELECT current_user AS me"))[0]["me"])
    said = await adapter.action("change_tablespace_owner").perform(
        TABLESPACES_REPORT_ID, {"tablespace": renamed, "owner": me},
    )
    assert said.message == f"Tablespace {renamed} now belongs to {me}"

    # Something stored in it: the server refuses, and nothing is lost.
    table = f"dp_in_space_{uuid4().hex[:8]}"
    session = _session()
    await session.schema_change(
        sql.SQL("CREATE TABLE {} (id integer) TABLESPACE {}").format(
            sql.Identifier(table), sql.Identifier(renamed),
        ).as_string(),
    )
    try:
        refused = await adapter.run_row_command(TABLESPACES_REPORT_ID, "drop_tablespace", [renamed])
        assert refused.done == 0
        assert refused.refused == [f"{renamed}: Something is still stored in it, in this database or another; move it out first"]
    finally:
        await session.schema_change(sql.SQL("DROP TABLE {}").format(sql.Identifier(table)).as_string())
    removed = await adapter.run_row_command(TABLESPACES_REPORT_ID, "drop_tablespace", [renamed])
    assert (removed.message, removed.done) == ("1 tablespace removed", 1)
    assert await _location(renamed) is None


async def test_the_server_says_what_is_wrong_with_a_location(directory: Callable[[], str]) -> None:
    create = _adapter().action("create_tablespace")
    name = f"dp_space_{uuid4().hex[:8]}"
    with pytest.raises(ActionRefused, match="no such directory"):
        await create.perform(TABLESPACES_REPORT_ID, {"name": name, "location": directory()})
    with pytest.raises(ActionRefused, match="absolute path"):
        await create.perform(TABLESPACES_REPORT_ID, {"name": name, "location": "relative/place"})


async def test_what_is_postgresql_own_is_left_alone() -> None:
    adapter = _adapter()
    with pytest.raises(ActionRefused, match="pg_default and pg_global"):
        await adapter.resolve_picked_rows(TABLESPACES_REPORT_ID, "rename_tablespace", [["pg_default"]])
    with pytest.raises(ActionRefused, match="Pick one tablespace"):
        await adapter.resolve_picked_rows(TABLESPACES_REPORT_ID, "rename_tablespace", [["a"], ["b"]])
    with pytest.raises(ActionRefused, match='no tablespace "pg_global"'):
        await adapter.action("rename_tablespace").perform(
            TABLESPACES_REPORT_ID, {"tablespace": "pg_global", "new_name": "mine"},
        )
    with pytest.raises(Exception, match="reserved by PostgreSQL"):
        await adapter.action("create_tablespace").perform(
            TABLESPACES_REPORT_ID, {"name": "pg_mine", "location": "/tmp/x"},
        )
    refused = await adapter.run_row_command(TABLESPACES_REPORT_ID, "drop_tablespace", ["pg_default"])
    assert refused.done == 0 and "can be removed" in refused.refused[0]
    with pytest.raises(ActionRefused, match="from the Tablespaces report"):
        await adapter.action("create_tablespace").perform(ROLES_REPORT_ID, {"name": "x", "location": "/tmp/x"})
