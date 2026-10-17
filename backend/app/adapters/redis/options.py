"""How to reach a Redis server.

Two ways, as a discriminated union, for the reason PostgreSQL has one (D16):
a server that wants a password and one that does not are different sets of
fields, and a single model with an optional password is a form that asks for
something half of its users must leave empty — and a `SecretStr | None` that
D4's schema split would not recognise as a secret at all.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.adapters.layout import layout
from app.core.translation import N_


def _auth_method_field(value: str) -> Any:
    return Field(default=value, title=N_("Authentication"), json_schema_extra=layout())


class _RedisBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A default rather than an empty box, for the reason PostgreSQL has one: a
    # server on the same machine is the commonest case there is.
    host: str = Field(
        default="localhost",
        min_length=1,
        title=N_("Host"),
        json_schema_extra=layout(row="address"),
    )
    port: int = Field(
        default=6379, ge=1, le=65535, title=N_("Port"), json_schema_extra=layout(row="address")
    )
    # Redis calls them databases and numbers them; there are sixteen by
    # default and they have no names, so this is a number rather than a name.
    # Where the catalog opens rather than what it is confined to: the others
    # are one control away, and the description says so (D91).
    database: int = Field(
        default=0,
        ge=0,
        le=15,
        title=N_("Database"),
        description=N_("Where the catalog opens; every database is in the catalog"),
        json_schema_extra=layout(),
    )


class RedisPassword(_RedisBase):
    model_config = ConfigDict(title=N_("Password"))

    auth_method: Literal["password"] = _auth_method_field("password")
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())


class RedisNoAuth(_RedisBase):
    """A server that asks for nothing, which is the default configuration."""

    model_config = ConfigDict(title=N_("No auth"))

    auth_method: Literal["no_auth"] = _auth_method_field("no_auth")


RedisOptions = Annotated[
    RedisPassword | RedisNoAuth, Field(discriminator="auth_method")
]
