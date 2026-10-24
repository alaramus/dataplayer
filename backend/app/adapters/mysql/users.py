"""Making a MySQL account, the one action here that is not about data (D243).

An account is the server's, not a database's: one made through this
connection can sign in through every other connection to the same server. So
it asks for `own`, as PostgreSQL's New role does (D79), and makes an account
that can sign in and do nothing else, or at most read the connection's own
database.

An account is a name and the host it may connect from. Both, and the
password, are bound: MySQL takes them as quoted strings, and the driver's
quoting is the one that is right. The statement carries a secret, so every
refusal is this module's own sentence, chosen by the server's error number.
"""

from collections.abc import Callable, Mapping
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator

from app.adapters.actions import (
    ActionRefused,
    ActionResult,
    ActsOn,
    JsonAction,
    OfferedIn,
)
from app.adapters.catalog import NodeKind
from app.adapters.mysql.catalog import MysqlCatalog
from app.adapters.mysql.reports import SECTION_ID
from app.adapters.mysql.session import MysqlSession
from app.adapters.mysql.sql import SQL, Identifier
from app.core.access import Access
from app.core.translation import N_, say

USERS_REPORT_ID = f"{SECTION_ID}/users"

# The same bounds the application's own accounts and PostgreSQL's roles use.
PASSWORD_MIN = 8
PASSWORD_MAX = 128
# MySQL keeps 32 characters of a user name and MariaDB 80; the shorter is the
# one both take, and a longer name is refused by the server anyway.
NAME_LIMIT = 32
HOST_LIMIT = 255

USER_REFUSALS: Mapping[int, str] = {
    1227: N_("This connection may not create accounts on this server"),
    1044: N_("This connection may not create accounts on this server"),
    1045: N_("This connection may not create accounts on this server"),
    1142: N_("This connection may not grant access to that database"),
    1396: N_("An account with that name and host already exists"),
    1470: N_("That name or host is longer than this server allows"),
    1819: N_("The server refused that password"),
}


def _account_part(limit: int) -> Callable[[str], str]:
    def check(value: str) -> str:
        if value == "" or value != value.strip() or len(value) > limit:
            raise ValueError(
                say(
                    "1 to {limit} characters, not starting or ending with spaces",
                    limit=limit,
                )
            )
        return value

    return check


class CreateUserParams(BaseModel):
    name: str = Field(title=N_("Name"))
    host: str = Field(
        default="%",
        title=N_("Host"),
        description=N_("Where the account may connect from; % is anywhere"),
    )
    password: SecretStr = Field(title=N_("Password"), min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    may_read: bool = Field(
        default=False,
        title=N_("May read this connection's database"),
        description=N_("Grants SELECT on the database this connection names, and nothing else"),
    )

    _name = field_validator("name")(_account_part(NAME_LIMIT))
    _host = field_validator("host")(_account_part(HOST_LIMIT))


class CreateUser(JsonAction[CreateUserParams]):
    """Create an account that can sign in, granted nothing or one database's rows to read.

    Not a surface for administering a server: global privileges, roles and
    GRANT OPTION are ways of handing out more than the person filling in the
    form may hold, and none is offered. Anything more is granted in SQL.
    """

    name: ClassVar[str] = "create_user"
    title: ClassVar[str] = N_("New user")
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"report"})
    acts_on: ClassVar[ActsOn] = "node"
    offered_in: ClassVar[OfferedIn] = "rows"
    icon: ClassVar[str] = "person_add"
    requires: ClassVar[Access] = "own"
    bulk: ClassVar[bool] = False
    params_model = CreateUserParams

    def __init__(self, session: MysqlSession, catalog: MysqlCatalog) -> None:
        self._session = session

    async def run(self, node_id: str | None, params: CreateUserParams) -> ActionResult:
        if node_id != USERS_REPORT_ID:
            raise ActionRefused("not_applicable", say("Accounts are made from the Users report"))
        database = self._session.database()
        if params.may_read and not database:
            raise ActionRefused(
                "not_applicable", say("This connection names no database to grant reading of")
            )
        account = (params.name, params.host)
        try:
            async with self._session.altering(refusals=USER_REFUSALS) as work:
                await work.execute(
                    "CREATE USER %s@%s IDENTIFIED BY %s",
                    (*account, params.password.get_secret_value()),
                )
                if params.may_read:
                    try:
                        await work.execute(
                            SQL("GRANT SELECT ON {}.* TO %s@%s").format(Identifier(database)).text(),
                            account,
                        )
                    except BaseException:
                        # An account that was meant to read and cannot is not
                        # the account that was asked for.
                        await work.execute("DROP USER IF EXISTS %s@%s", account)
                        raise
        except ValueError as refused:
            kind: Literal["conflict", "not_applicable"] = (
                "conflict" if str(refused) == say(USER_REFUSALS[1396]) else "not_applicable"
            )
            raise ActionRefused(kind, str(refused)) from None
        label = f"{params.name}@{params.host}"
        return ActionResult(
            message=(
                say("User {name} created, and may read {database}", name=label, database=database)
                if params.may_read
                else say("User {name} created", name=label)
            ),
            # An account is not a node, and the report re-reads when it is read.
            reload_node_ids=[],
        )
