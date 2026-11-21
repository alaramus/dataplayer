"""How to reach a MySQL or MariaDB server, and how to prove who is asking.

The same flat union PostgreSQL has, for the same reason (D16): a server that
wants a password and one that does not are different sets of fields. Every
variant names a user, because MySQL always signs one in.

The database is optional, unlike PostgreSQL's. A MySQL database is a schema
(D229): one connection reaches every database its user may see, so naming one
says where the catalog opens rather than what it is confined to.
"""

from collections.abc import Mapping
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
    return Field(title=N_("User"), min_length=1, json_schema_extra=layout())


def _auth_method_field(method: str) -> Any:
    return Field(default=method, title=N_("Authentication"), json_schema_extra=layout())


class _MysqlBase(BaseModel):
    host: str = Field(
        default="localhost",
        title=N_("Host"),
        min_length=1,
        json_schema_extra=layout(row="address"),
    )
    port: int = Field(
        default=3306,
        title=N_("Port"),
        ge=1,
        le=65535,
        json_schema_extra=layout(row="address"),
    )
    # The SSH connection this server is reached through, if any (D282).
    ssh_tunnel: str = ssh_tunnel_field()


class MysqlUserPassword(_MysqlBase):
    model_config = ConfigDict(title=N_("User & Password"))

    auth_method: Literal["user_password"] = _auth_method_field("user_password")
    database: str = _database_field()
    user: str = _user_field()
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())


class MysqlNoPassword(_MysqlBase):
    """A user created without a password, as a fresh container's root can be."""

    model_config = ConfigDict(title=N_("No password"))

    auth_method: Literal["no_password"] = _auth_method_field("no_password")
    database: str = _database_field()
    user: str = _user_field()


MysqlOptions = Annotated[
    MysqlUserPassword | MysqlNoPassword,
    Field(discriminator="auth_method"),
]


def container_options(env: Mapping[str, str]) -> dict[str, Any]:
    """A container of the MySQL or MariaDB image as a connection (D417): the
    user it made with its database when there is one, root otherwise."""
    database = env.get("MYSQL_DATABASE") or env.get("MARIADB_DATABASE") or ""
    user = env.get("MYSQL_USER") or env.get("MARIADB_USER")
    password = env.get("MYSQL_PASSWORD") or env.get("MARIADB_PASSWORD")
    if not (user and password):
        user = "root"
        password = env.get("MYSQL_ROOT_PASSWORD") or env.get("MARIADB_ROOT_PASSWORD")
    empty = env.get("MYSQL_ALLOW_EMPTY_PASSWORD") or env.get("MARIADB_ALLOW_EMPTY_ROOT_PASSWORD")
    if user == "root" and not password and empty:
        return {"auth_method": "no_password", "user": user, "database": database}
    return {
        "auth_method": "user_password",
        "user": user,
        "database": database,
        **({"password": password} if password else {}),
    }
