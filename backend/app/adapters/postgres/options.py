"""How to reach a PostgreSQL server, and how to prove who is asking.

A flat discriminated union rather than one model with optional fields: what a
user must fill in depends on the way the server authenticates them, and a form
built from optional fields would have to decide for itself which of them
matter, and ends up asking every field whether it should be showing.

Flat rather than nested. Putting the varying fields in a sub-object would make
`config` two levels deep, and with it the secret split, which cuts by
top-level name (`connectors/service.py`). This way exactly one key is added.

Order is a statement this file makes, and it is the only one that can. Fields
of a base class always come first, so the base holds the address and nothing
else: the choice of method belongs directly under it, and everything that
follows follows the choice. That is also why `database` and `user` are
declared by each variant through the factories below rather than inherited —
the same field, stated where it belongs, not a second definition of it.

The `title` on each variant is not decoration: it becomes the title of the
entry in `$defs`, which is the wording of the item in the pick list. Without
it the user would be offered class names.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.adapters.layout import layout


def _database_field() -> Any:
    return Field(title="Database", min_length=1, json_schema_extra=layout())


def _user_field() -> Any:
    return Field(title="User", min_length=1, json_schema_extra=layout())


def _auth_method_field(method: str) -> Any:
    return Field(default=method, title="Authentication", json_schema_extra=layout())


class _PostgresBase(BaseModel):
    """Where the server is, whichever way one authenticates to it.

    Inherited rather than repeated so that the form can tell the address is
    the same field in both variants and draw it once — see `readSchema` on the
    client.
    """

    # A default rather than an empty box: a database on the same machine is
    # the commonest case there is, and a value that is usually right is worth
    # more than a field that always has to be filled in.
    host: str = Field(
        default="localhost",
        title="Host",
        min_length=1,
        json_schema_extra=layout(row="address"),
    )
    port: int = Field(
        default=5432,
        title="Port",
        ge=1,
        le=65535,
        json_schema_extra=layout(row="address"),
    )


class PostgresUserPassword(_PostgresBase):
    model_config = ConfigDict(title="User & Password")

    auth_method: Literal["user_password"] = _auth_method_field("user_password")
    database: str = _database_field()
    user: str = _user_field()
    password: SecretStr = Field(title="Password", json_schema_extra=layout())


class PostgresNoAuth(_PostgresBase):
    """A server that asks for no password: `trust` or `peer` in pg_hba.conf.

    Not a hypothetical variant added to make the list longer — the difference
    reaches the driver, which then sends no password at all rather than an
    empty one.
    """

    model_config = ConfigDict(title="No auth")

    auth_method: Literal["no_auth"] = _auth_method_field("no_auth")
    database: str = _database_field()
    user: str = _user_field()


PostgresOptions = Annotated[
    PostgresUserPassword | PostgresNoAuth,
    Field(discriminator="auth_method"),
]
