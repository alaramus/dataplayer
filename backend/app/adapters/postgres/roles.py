"""Making a database user, which is the one thing here that is not about data.

A role is the server's, not the database's: one made through this connection
can sign in through every other connection to the same server, and no grant
this application hands out is a reason to be able to do that. So it is the one
action that asks for `own` (D79).

Two rules shape the rest. A password cannot be bound — PostgreSQL takes no
parameters in DDL — so it travels as a `psycopg.sql.Literal`, which is the
driver's own quoting of a value rather than this repository's. And the
statement therefore carries a secret, which is why nothing here rehearses it
and why every refusal is this module's own sentence, chosen by SQLSTATE.
"""

from collections.abc import Mapping
from typing import ClassVar

from psycopg import sql
from pydantic import BaseModel, Field, SecretStr, field_validator

from app.adapters.actions import (
    ActionRefused,
    ActionResult,
    ActsOn,
    JsonAction,
)
from app.adapters.catalog import NodeKind
from app.adapters.postgres.catalog import PostgresCatalog
from app.adapters.postgres.names import name_check
from app.adapters.postgres.session import PostgresSession
from app.adapters.postgres.system_reports import ROLES_REPORT_ID
from app.core.access import Access

# PostgreSQL keeps this prefix for the roles it ships with, and refuses one of
# its own with 42939. Refused here as well as there, so that the answer is
# about the name rather than about a statement that was attempted with a
# password in it.
RESERVED_PREFIX = "pg_"

ROLE_REFUSALS: Mapping[str, str] = {
    # insufficient_privilege: CREATE ROLE needs CREATEROLE or a superuser, and
    # this application connects as whoever the connector says.
    "42501": "This connection may not create roles on this server",
    # duplicate_object: the name was free when it was checked and is not now.
    "42710": "A role with that name already exists",
    # reserved_name.
    "42939": "That role name is reserved by PostgreSQL",
    # invalid_password: a server may hold a password policy of its own, and
    # what it objected to is not repeated here.
    "28P01": "The server refused that password",
}

# What a password may be. The same bounds the application's own accounts use:
# a rule about passwords stated twice with different numbers is two rules.
PASSWORD_MIN = 8
PASSWORD_MAX = 128


class CreateRoleParams(BaseModel):
    name: str = Field(title="Name")
    password: SecretStr = Field(
        title="Password", min_length=PASSWORD_MIN, max_length=PASSWORD_MAX
    )
    # The database is this connection's own and is never named by the client,
    # so the choice is whether to grant, not what to grant it on. Usually a
    # formality — PUBLIC holds CONNECT until somebody revokes it — and exactly
    # what matters on a server where somebody has.
    may_connect: bool = Field(
        default=True,
        title="May connect to this database",
        description="Grants CONNECT on the database this connection is on",
    )

    _check = field_validator("name")(name_check("role"))


class CreateRole(JsonAction[CreateRoleParams]):
    """Create a role that can sign in, and grant it nothing else.

    Deliberately not a surface for administering a server. It makes a login
    role and, at most, lets it connect to the database being looked at:
    CREATEDB, CREATEROLE, SUPERUSER, membership and object privileges are all
    ways of handing out more than the person filling in the form holds, and
    none of them is offered. What the new role may read is granted with SQL,
    by somebody who has left read-only on purpose (D66).

    No preview, and that is a decision rather than an omission: a rehearsal is
    the statement run and rolled back, and its worth is that the server's own
    words come back with it (D46). Those words are not worth having when the
    statement carries a password.
    """

    name: ClassVar[str] = "create_role"
    title: ClassVar[str] = "New role"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"report"})
    acts_on: ClassVar[ActsOn] = "node"
    requires: ClassVar[Access] = "own"
    bulk: ClassVar[bool] = False
    params_model = CreateRoleParams

    def __init__(self, session: PostgresSession, catalog: PostgresCatalog) -> None:
        self._session = session

    async def run(self, node_id: str | None, params: CreateRoleParams) -> ActionResult:
        if node_id != ROLES_REPORT_ID:
            raise ActionRefused(
                "not_applicable", "Roles are made from the Roles report"
            )
        if params.name.lower().startswith(RESERVED_PREFIX):
            raise ActionRefused(
                "not_applicable",
                f'PostgreSQL keeps names beginning with "{RESERVED_PREFIX}" '
                "for roles of its own",
            )
        if await self._taken(params.name):
            # A taken name is a conflict rather than a fault, the shape a taken
            # folder name and an installed extension already answer with.
            raise ActionRefused(
                "conflict", f'A role called "{params.name}" already exists'
            )
        database = await self._database()
        async with self._session.transaction(refusals=ROLE_REFUSALS) as transaction:
            await transaction.schema_change(_create_statement(params))
            if params.may_connect:
                await transaction.schema_change(
                    _grant_connect_statement(params.name, database)
                )
        return ActionResult(
            message=(
                f"Role {params.name} created"
                + (f", and may connect to {database}" if params.may_connect else "")
            ),
            # Nothing in the catalog changed: a role is not a node, and the
            # report that lists them re-reads when it is read. Naming a branch
            # here to make a grid refresh would be a lie about what happened.
            reload_node_ids=[],
        )

    async def _taken(self, typed: str) -> bool:
        rows = await self._session.query(
            "SELECT 1 AS found FROM pg_catalog.pg_roles WHERE rolname = %s",
            (typed,),
        )
        return bool(rows)

    async def _database(self) -> str:
        """The name of the database this connection is on, from the server.

        Asked rather than read off the connection options: the identifier that
        reaches a statement is one the server itself spelled, which is the
        rule the extension commands follow for the same reason.
        """
        rows = await self._session.query("SELECT current_database() AS name")
        return str(rows[0]["name"])


def _create_statement(params: CreateRoleParams) -> str:
    """`CREATE ROLE`, with the password as a literal because DDL takes none.

    `sql.Literal` is psycopg's own quoting of a Python value, the same code
    that quotes a bound parameter; what is different here is only that the
    quoting happens before the statement is sent instead of by the server.
    Writing the quoting by hand is the one thing that must not happen.

    The password is sent as the person typed it rather than as a verifier
    computed here, so the server stores it the way its own
    `password_encryption` says. A verifier would keep the cleartext out of the
    server's log — see the deviation recorded with D79 — and would also decide
    on the server's behalf which authentication method the new role can use.
    """
    return (
        sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}")
        .format(
            sql.Identifier(params.name),
            sql.Literal(params.password.get_secret_value()),
        )
        .as_string()
    )


def _grant_connect_statement(role: str, database: str) -> str:
    return (
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}")
        .format(sql.Identifier(database), sql.Identifier(role))
        .as_string()
    )
