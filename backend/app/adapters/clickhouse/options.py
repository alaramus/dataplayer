"""How to reach a ClickHouse server over its HTTP interface, and who is asking.

The same flat union MySQL has, for the same reason (D16). The database is
optional, as MySQL's is: a ClickHouse database is a schema to the catalog, and
one connection reaches every database its user may see (D267).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.adapters.layout import layout
from app.adapters.tunnels import ssh_tunnel_field
from app.core.translation import N_


def _database_field() -> Any:
    return Field(
        default="",
        title=N_("Database"),
        description=N_("Where the catalog opens; every database the user may see is in the catalog"),
        json_schema_extra=layout(),
    )


def _user_field() -> Any:
    return Field(default="default", title=N_("User"), min_length=1, json_schema_extra=layout())


def _auth_method_field(method: str) -> Any:
    return Field(default=method, title=N_("Authentication"), json_schema_extra=layout())


class _ClickhouseBase(BaseModel):
    host: str = Field(
        default="localhost",
        title=N_("Host"),
        min_length=1,
        json_schema_extra=layout(row="address"),
    )
    port: int = Field(
        default=8123,
        title=N_("Port"),
        description=N_("The HTTP interface: 8123, or 8443 with TLS"),
        ge=1,
        le=65535,
        json_schema_extra=layout(row="address"),
    )
    secure: bool = Field(
        default=False,
        title=N_("TLS"),
        description=N_("HTTPS, with the server's certificate verified"),
        json_schema_extra=layout(),
    )
    # The SSH connection this server is reached through, if any (D282).
    ssh_tunnel: str = ssh_tunnel_field()


class ClickhouseUserPassword(_ClickhouseBase):
    model_config = ConfigDict(title=N_("User & Password"))

    auth_method: Literal["user_password"] = _auth_method_field("user_password")
    database: str = _database_field()
    user: str = _user_field()
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())


class ClickhouseNoPassword(_ClickhouseBase):
    """A user without a password, as a fresh server's `default` is."""

    model_config = ConfigDict(title=N_("No password"))

    auth_method: Literal["no_password"] = _auth_method_field("no_password")
    database: str = _database_field()
    user: str = _user_field()


ClickhouseOptions = Annotated[
    ClickhouseUserPassword | ClickhouseNoPassword,
    Field(discriminator="auth_method"),
]
