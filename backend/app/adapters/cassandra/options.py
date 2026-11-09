"""How to reach a Cassandra or ScyllaDB node over CQL, and who is asking.

The same flat union MySQL has, for the same reason (D16). The keyspace is
optional: a keyspace is a schema to the catalog, and one connection reaches
every keyspace its role may see (D340).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.adapters.layout import layout
from app.adapters.tunnels import ssh_tunnel_field
from app.core.translation import N_

# The driver's consistency levels a person may choose, by their CQL names.
# Closed, so a client never writes one; the session maps each to the driver.
Consistency = Literal[
    "ONE",
    "LOCAL_ONE",
    "QUORUM",
    "LOCAL_QUORUM",
    "EACH_QUORUM",
    "ALL",
]


def _keyspace_field() -> Any:
    return Field(
        default="",
        title=N_("Keyspace"),
        description=N_(
            "Where the catalog opens; every keyspace the role may see is in the catalog"
        ),
        json_schema_extra=layout(),
    )


def _user_field() -> Any:
    return Field(
        default="cassandra", title=N_("User"), min_length=1, json_schema_extra=layout()
    )


def _auth_method_field(method: str) -> Any:
    return Field(default=method, title=N_("Authentication"), json_schema_extra=layout())


class _CassandraBase(BaseModel):
    host: str = Field(
        default="localhost",
        title=N_("Host"),
        min_length=1,
        json_schema_extra=layout(row="address"),
    )
    port: int = Field(
        default=9042,
        title=N_("Port"),
        description=N_(
            "The native protocol's port, 9042 unless the server says otherwise"
        ),
        ge=1,
        le=65535,
        json_schema_extra=layout(row="address"),
    )
    secure: bool = Field(
        default=False,
        title=N_("TLS"),
        description=N_("TLS, with the server's certificate verified"),
        json_schema_extra=layout(),
    )
    consistency: Consistency = Field(
        default="LOCAL_ONE",
        title=N_("Consistency"),
        description=N_("How many replicas answer a read and acknowledge a write"),
        json_schema_extra=layout(),
    )
    # The SSH connection this node is reached through, if any (D282).
    ssh_tunnel: str = ssh_tunnel_field()


class CassandraUserPassword(_CassandraBase):
    model_config = ConfigDict(title=N_("User & Password"))

    auth_method: Literal["user_password"] = _auth_method_field("user_password")
    keyspace: str = _keyspace_field()
    user: str = _user_field()
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())


class CassandraNoPassword(_CassandraBase):
    """A server that checks no password, as a fresh Cassandra does."""

    model_config = ConfigDict(title=N_("No password"))

    auth_method: Literal["no_password"] = _auth_method_field("no_password")
    keyspace: str = _keyspace_field()


CassandraOptions = Annotated[
    CassandraUserPassword | CassandraNoPassword,
    Field(discriminator="auth_method"),
]
