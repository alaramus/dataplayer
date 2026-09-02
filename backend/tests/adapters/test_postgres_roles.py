"""Making a database user, from the report that lists the ones there are."""

from collections.abc import AsyncGenerator, Callable
from uuid import uuid4

import pytest
from psycopg import sql
from pydantic import SecretStr

from app.adapters.actions import ActionRefused, Previews
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import (
    EXTENSIONS_REPORT_ID,
    ROLES_REPORT_ID,
    SECTION_ID,
)
from app.adapters.protocol import AdapterError
from tests.utils.database import working_postgres_options

# Everything the statement has to survive: the quote that would close the
# literal, the backslash that would escape the quote back open, and the
# double quote that belongs to identifiers rather than to values.
AWKWARD_PASSWORD = "p'a\\ss\"word; --"


def _adapter() -> PostgresAdapter:
    return PostgresAdapter(PostgresUserPassword(**working_postgres_options()))


def _session() -> PostgresSession:
    return PostgresSession(PostgresUserPassword(**working_postgres_options()))


async def _remove(name: str) -> None:
    """Take a role away again, privileges first.

    A role that was granted CONNECT cannot be dropped while the grant stands:
    the database depends on it. `DROP OWNED BY` is what revokes that, and it
    refuses a role that is not there, so its existence is asked first.
    """
    session = _session()
    rows = await session.query(
        "SELECT 1 AS found FROM pg_catalog.pg_roles WHERE rolname = %s", (name,)
    )
    if not rows:
        return
    identifier = sql.Identifier(name)
    await session.schema_change(
        sql.SQL("DROP OWNED BY {}").format(identifier).as_string()
    )
    await session.schema_change(sql.SQL("DROP ROLE {}").format(identifier).as_string())


@pytest.fixture
async def naming() -> AsyncGenerator[Callable[..., str]]:
    """Names for roles a test makes, each dropped however the test ends.

    A role is the server's rather than the database's, so one left behind by a
    test is left behind for everything else on that server.
    """
    made: list[str] = []

    def remember(name: str | None = None) -> str:
        chosen = name if name is not None else f"dp_role_{uuid4().hex[:8]}"
        made.append(chosen)
        return chosen

    yield remember
    for name in made:
        await _remove(name)


async def _available(adapter: PostgresAdapter, node_id: str) -> list[str]:
    return [action.name for action in await adapter.available(node_id)]


async def _exists(name: str) -> bool:
    rows = await _session().query(
        "SELECT 1 AS found FROM pg_catalog.pg_roles WHERE rolname = %s", (name,)
    )
    return bool(rows)


async def _granted_connect(name: str) -> bool:
    """Whether this database names the role in its own privileges.

    Not `has_database_privilege`, which is true for every role while PUBLIC
    holds CONNECT and so would say yes to a grant that never happened.
    """
    rows = await _session().query(
        """
        SELECT 1 AS found
        FROM pg_catalog.pg_database d,
             aclexplode(d.datacl) a
        JOIN pg_catalog.pg_roles r ON r.oid = a.grantee
        WHERE d.datname = current_database()
          AND r.rolname = %s
          AND a.privilege_type = 'CONNECT'
        """,
        (name,),
    )
    return bool(rows)


async def test_the_command_is_offered_on_the_roles_report() -> None:
    assert await _available(_adapter(), ROLES_REPORT_ID) == ["create_role"]


async def test_no_other_report_offers_it() -> None:
    """`applies_to` says "a report"; which report is a question of state."""
    adapter = _adapter()

    assert "create_role" not in await _available(adapter, EXTENSIONS_REPORT_ID)
    assert await _available(adapter, f"{SECTION_ID}.processes") == []
    assert await _available(adapter, SECTION_ID) == []


async def test_making_a_role_is_asked_of_the_owner_of_the_connection() -> None:
    """D79: a role is the server's, and no grant this application hands out
    is a reason to be able to make one."""
    assert _adapter().action("create_role").requires == "own"


async def test_a_role_is_made_and_signs_in_with_the_password_it_was_given(
    naming: Callable[..., str],
) -> None:
    """The one proof that the literal is quoted as psycopg says and not as a
    statement full of punctuation would be."""
    name = naming()

    result = await _adapter().action("create_role").perform(
        ROLES_REPORT_ID, {"name": name, "password": AWKWARD_PASSWORD}
    )

    assert name in result.message
    # Nothing in the catalog changed, so nothing is asked to re-read.
    assert result.reload_node_ids == []
    assert await _granted_connect(name) is True
    theirs = PostgresSession(
        PostgresUserPassword(
            **{
                **working_postgres_options(),
                "user": name,
                "password": SecretStr(AWKWARD_PASSWORD),
            }
        )
    )
    assert await theirs.query("SELECT current_user AS who") == [{"who": name}]


async def test_a_role_can_be_made_without_letting_it_connect_here(
    naming: Callable[..., str],
) -> None:
    name = naming()

    await _adapter().action("create_role").perform(
        ROLES_REPORT_ID,
        {"name": name, "password": "a-long-enough-password", "may_connect": False},
    )

    assert await _exists(name) is True
    assert await _granted_connect(name) is False


async def test_a_name_that_is_taken_is_a_conflict(naming: Callable[..., str]) -> None:
    name = naming()
    action = _adapter().action("create_role")
    await action.perform(
        ROLES_REPORT_ID, {"name": name, "password": "a-long-enough-password"}
    )

    with pytest.raises(ActionRefused, match="already exists") as refusal:
        await action.perform(
            ROLES_REPORT_ID, {"name": name, "password": "another-long-password"}
        )

    assert refusal.value.reason == "conflict"


async def test_a_name_the_server_reserves_is_refused() -> None:
    """Refused here as well as by the server: the answer is about the name,
    and nothing is attempted with a password in it."""
    with pytest.raises(ActionRefused, match="pg_") as refusal:
        await _adapter().action("create_role").perform(
            ROLES_REPORT_ID,
            {"name": "pg_something", "password": "a-long-enough-password"},
        )

    assert refusal.value.reason == "not_applicable"
    assert await _exists("pg_something") is False


async def test_a_name_full_of_punctuation_becomes_one_role_and_nothing_else(
    naming: Callable[..., str],
) -> None:
    """The identifier is composed, so a name that reads like a statement is a
    name."""
    name = naming('x"; DROP SCHEMA public CASCADE; --')

    await _adapter().action("create_role").perform(
        ROLES_REPORT_ID, {"name": name, "password": "a-long-enough-password"}
    )

    assert await _exists(name) is True
    schemas = await _session().query(
        "SELECT nspname AS name FROM pg_catalog.pg_namespace WHERE nspname = 'public'"
    )
    assert schemas == [{"name": "public"}]


async def test_the_command_refuses_a_node_that_is_not_that_report() -> None:
    with pytest.raises(ActionRefused, match="Roles report"):
        await _adapter().action("create_role").perform(
            EXTENSIONS_REPORT_ID,
            {"name": "dp_role_elsewhere", "password": "a-long-enough-password"},
        )


async def test_a_password_the_form_will_not_take_is_refused_before_any_statement() -> (
    None
):
    action = _adapter().action("create_role")

    with pytest.raises(ValueError):
        await action.perform(ROLES_REPORT_ID, {"name": "dp_role_short", "password": "1"})

    assert await _exists("dp_role_short") is False


async def test_nothing_is_previewed() -> None:
    """A rehearsal's worth is that the server's own words come back with it
    (D46), and those are not worth having about a statement carrying a
    password."""
    assert not isinstance(_adapter().action("create_role"), Previews)


async def test_the_form_says_the_password_is_write_only() -> None:
    schema = _adapter().action("create_role").params_schema()

    password = schema["properties"]["password"]
    assert password["format"] == "password"
    assert password["writeOnly"] is True
    assert password["minLength"] == 8


async def test_a_refusal_from_the_server_carries_neither_password_nor_driver_text(
    naming: Callable[..., str],
) -> None:
    """The refusal path, walked with a real password in the statement.

    A role that may sign in and nothing else is exactly what this action
    makes, so it is also the connection that must not be able to make
    another one — and what comes back is this repository's sentence for
    42501, not the server's account of it.
    """
    maker = naming()
    await _adapter().action("create_role").perform(
        ROLES_REPORT_ID, {"name": maker, "password": AWKWARD_PASSWORD}
    )
    as_them = PostgresAdapter(
        PostgresUserPassword(
            **{
                **working_postgres_options(),
                "user": maker,
                "password": SecretStr(AWKWARD_PASSWORD),
            }
        )
    )
    wanted = naming()

    with pytest.raises((ValueError, AdapterError)) as refused:
        await as_them.action("create_role").perform(
            ROLES_REPORT_ID, {"name": wanted, "password": AWKWARD_PASSWORD}
        )

    said = str(refused.value)
    assert AWKWARD_PASSWORD not in said
    assert "permission denied" not in said.lower()
    assert await _exists(wanted) is False
