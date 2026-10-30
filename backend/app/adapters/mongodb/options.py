"""How to reach a MongoDB server, and who is asking (D283).

The same flat union MySQL has, for the same reason (D16). The database is
optional: it says where the catalog opens, and one connection reaches every
database its user may see.
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


def _auth_method_field(method: str) -> Any:
    return Field(default=method, title=N_("Authentication"), json_schema_extra=layout())


class _MongodbBase(BaseModel):
    host: str = Field(
        default="localhost",
        title=N_("Host"),
        min_length=1,
        json_schema_extra=layout(row="address"),
    )
    port: int = Field(
        default=27017,
        title=N_("Port"),
        ge=1,
        le=65535,
        json_schema_extra=layout(row="address"),
    )
    tls: bool = Field(
        default=False,
        title=N_("TLS"),
        description=N_("Encrypted, with the server's certificate verified"),
        json_schema_extra=layout(),
    )
    # The SSH connection this server is reached through, if any (D282).
    ssh_tunnel: str = ssh_tunnel_field()


class MongodbUserPassword(_MongodbBase):
    model_config = ConfigDict(title=N_("User & Password"))

    auth_method: Literal["user_password"] = _auth_method_field("user_password")
    database: str = _database_field()
    user: str = Field(title=N_("User"), min_length=1, json_schema_extra=layout())
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())
    auth_source: str = Field(
        default="admin",
        title=N_("Authentication database"),
        description=N_("Where the user is defined; admin unless it was made in another database"),
        min_length=1,
        json_schema_extra=layout(),
    )


class MongodbNoPassword(_MongodbBase):
    """A server started without access control, as a fresh one is."""

    model_config = ConfigDict(title=N_("No password"))

    auth_method: Literal["no_password"] = _auth_method_field("no_password")
    database: str = _database_field()


MongodbOptions = Annotated[
    MongodbUserPassword | MongodbNoPassword,
    Field(discriminator="auth_method"),
]
