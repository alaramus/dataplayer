"""How to reach a PostgreSQL server, and how to prove who is asking.

A flat discriminated union rather than one model with optional fields: what a
user must fill in depends on the way the server authenticates them, and a form
built from optional fields would have to decide for itself which of them
matter — which is how the old application ended up asking every field whether
it should be showing.

Flat rather than nested. Putting the varying fields in a sub-object would make
`config` two levels deep, and with it the secret split, which cuts by
top-level name (`connectors/service.py`). This way exactly one key is added.

The `title` on each variant is not decoration: it becomes the title of the
entry in `$defs`, which is the wording of the item in the pick list. Without
it the user would be offered class names.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.adapters.layout import layout


class _PostgresBase(BaseModel):
    """What is true of the server whichever way one authenticates to it.

    Inherited rather than repeated so that the form can tell that host, port
    and database are the same field in both variants and draw them once —
    see `readSchema` on the client.
    """

    host: str = Field(title="Host", min_length=1, json_schema_extra=layout(row="address"))
    port: int = Field(
        default=5432,
        title="Port",
        ge=1,
        le=65535,
        json_schema_extra=layout(row="address"),
    )
    database: str = Field(title="Database", min_length=1, json_schema_extra=layout())


class PostgresUserPassword(_PostgresBase):
    model_config = ConfigDict(title="User & Password")

    auth_method: Literal["user_password"] = Field(
        default="user_password", title="Authentication", json_schema_extra=layout()
    )
    user: str = Field(title="User", min_length=1, json_schema_extra=layout())
    password: SecretStr = Field(title="Password", json_schema_extra=layout())


class PostgresNoAuth(_PostgresBase):
    """A server that asks for no password: `trust` or `peer` in pg_hba.conf.

    Not a hypothetical variant added to make the list longer — the difference
    reaches the driver, which then sends no password at all rather than an
    empty one.
    """

    model_config = ConfigDict(title="No auth")

    auth_method: Literal["no_auth"] = Field(
        default="no_auth", title="Authentication", json_schema_extra=layout()
    )
    user: str = Field(title="User", min_length=1, json_schema_extra=layout())


PostgresOptions = Annotated[
    PostgresUserPassword | PostgresNoAuth,
    Field(discriminator="auth_method"),
]
