"""How to reach a MySQL or MariaDB server, and how to prove who is asking.

The same flat union PostgreSQL has, for the same reason (D16): a server that
wants a password and one that does not are different sets of fields. Every
variant names a user, because MySQL always signs one in.

The database is optional, unlike PostgreSQL's. A MySQL database is a schema
(D229): one connection reaches every database its user may see, so naming one
says where the catalog opens rather than what it is confined to.
"""

from collections.abc import Mapping
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import ConfigDict, Field, SecretStr, model_validator

from app.adapters.cloud import CloudAccess
from app.adapters.cloud.signin import (
    SignIn,
    aws_account_field,
    cloudsql_sign_in,
    gcp_account_field,
    password_key_field,
    rds_sign_in,
    region_field,
    secret_name_field,
    store_account_field,
    stored_sign_in,
    stored_user_field,
    user_key_field,
)
from app.adapters.layout import layout
from app.adapters.tls import TlsOptionsWithFallback
from app.adapters.tunnels import ssh_tunnel_field
from app.core.translation import N_, say


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


class _MysqlBase(TlsOptionsWithFallback):
    # TLS on a page of its own, encrypted when the server offers it by default
    # as before there was a choice (D446).
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

    # Whether the password travels in the clear, as RDS IAM wants it (D453).
    cleartext: ClassVar[bool] = False

    async def sign_in(self, cloud: CloudAccess | None) -> SignIn:
        return SignIn(user=self.user, password=self.password.get_secret_value())


class MysqlNoPassword(_MysqlBase):
    """A user created without a password, as a fresh container's root can be."""

    model_config = ConfigDict(title=N_("No password"))

    auth_method: Literal["no_password"] = _auth_method_field("no_password")
    database: str = _database_field()
    user: str = _user_field()

    cleartext: ClassVar[bool] = False

    async def sign_in(self, cloud: CloudAccess | None) -> SignIn:
        return SignIn(user=self.user, password=None)


class MysqlAwsIam(_MysqlBase):
    """RDS or Aurora IAM: a token issued for every new connection, sent with
    the cleartext plugin, which is why TLS that verifies is required (D453)."""

    model_config = ConfigDict(title=N_("AWS IAM (RDS)"))

    auth_method: Literal["aws_iam"] = _auth_method_field("aws_iam")
    database: str = _database_field()
    user: str = _user_field()
    account: str = aws_account_field()
    region: str = region_field()

    cleartext: ClassVar[bool] = True

    @model_validator(mode="after")
    def _verified(self) -> Self:
        if self.tls_mode not in ("verify_ca", "verify_full"):
            raise ValueError(
                say("The token is sent in the clear; choose Verify CA or Verify full on the TLS page")
            )
        return self

    async def sign_in(self, cloud: CloudAccess | None) -> SignIn:
        return await rds_sign_in(cloud, self.account, self.region, self.host, self.port, self.user)


class MysqlGcpIam(_MysqlBase):
    """Cloud SQL's IAM database sign-in: the access token is the password,
    sent with the cleartext plugin as Cloud SQL asks, so TLS that verifies is
    required (D455)."""

    model_config = ConfigDict(title=N_("Google Cloud IAM (Cloud SQL)"))

    auth_method: Literal["gcp_iam"] = _auth_method_field("gcp_iam")
    database: str = _database_field()
    user: str = Field(
        title=N_("User"),
        min_length=1,
        description=N_("A service account's name before the @, or a person's name before it"),
        json_schema_extra=layout(),
    )
    account: str = gcp_account_field()

    cleartext: ClassVar[bool] = True

    @model_validator(mode="after")
    def _verified(self) -> Self:
        if self.tls_mode not in ("verify_ca", "verify_full"):
            raise ValueError(
                say("The token is sent in the clear; choose Verify CA or Verify full on the TLS page")
            )
        return self

    async def sign_in(self, cloud: CloudAccess | None) -> SignIn:
        return await cloudsql_sign_in(cloud, self.account, self.user)


class MysqlSecretStore(_MysqlBase):
    """A password kept in a secret store, read at every new connection (D454)."""

    model_config = ConfigDict(title=N_("Secret store"))

    auth_method: Literal["secret_store"] = _auth_method_field("secret_store")
    database: str = _database_field()
    account: str = store_account_field()
    secret_name: str = secret_name_field()
    password_key: str = password_key_field()
    user_key: str = user_key_field()
    user: str = stored_user_field()

    cleartext: ClassVar[bool] = False

    async def sign_in(self, cloud: CloudAccess | None) -> SignIn:
        return await stored_sign_in(
            cloud, self.account, self.secret_name, self.password_key, self.user_key, self.user
        )


MysqlOptions = Annotated[
    MysqlUserPassword | MysqlNoPassword | MysqlAwsIam | MysqlGcpIam | MysqlSecretStore,
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
