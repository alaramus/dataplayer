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


def _auth_method_field(value: str) -> Any:
    return Field(default=value, title="Authentication", json_schema_extra=layout())


class _RedisBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        min_length=1, title="Host", json_schema_extra=layout(row="address")
    )
    port: int = Field(
        default=6379, ge=1, le=65535, title="Port", json_schema_extra=layout(row="address")
    )
    # Redis calls them databases and numbers them; there are sixteen by
    # default and they have no names, so this is a number rather than a name.
    database: int = Field(
        default=0, ge=0, le=15, title="Database", json_schema_extra=layout()
    )


class RedisPassword(_RedisBase):
    model_config = ConfigDict(title="Password")

    auth_method: Literal["password"] = _auth_method_field("password")
    password: SecretStr = Field(title="Password", json_schema_extra=layout())


class RedisNoAuth(_RedisBase):
    """A server that asks for nothing, which is the default configuration."""

    model_config = ConfigDict(title="No auth")

    auth_method: Literal["no_auth"] = _auth_method_field("no_auth")


RedisOptions = Annotated[
    RedisPassword | RedisNoAuth, Field(discriminator="auth_method")
]
