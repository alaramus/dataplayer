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
it the user would be offered class names. Every title is marked `N_` and
worded by the route that hands the schema out (D226).
"""

from collections.abc import Mapping
from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, SecretStr, model_validator

from app.adapters.cloud import CloudAccess
from app.adapters.cloud.signin import (
    SignIn,
    aws_account_field,
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
    return Field(title=N_("Database"), min_length=1, json_schema_extra=layout())


def _user_field() -> Any:
    return Field(title=N_("User"), min_length=1, json_schema_extra=layout())


def _auth_method_field(method: str) -> Any:
    return Field(default=method, title=N_("Authentication"), json_schema_extra=layout())


class _PostgresBase(TlsOptionsWithFallback):
    """Where the server is, whichever way one authenticates to it.

    Inherited rather than repeated so that the form can tell the address is
    the same field in both variants and draw it once — see `readSchema` on the
    client. TLS is on a page of its own, libpq's `prefer` by default (D446).
    """

    # A default rather than an empty box: a database on the same machine is
    # the commonest case there is, and a value that is usually right is worth
    # more than a field that always has to be filled in.
    host: str = Field(
        default="localhost",
        title=N_("Host"),
        min_length=1,
        json_schema_extra=layout(row="address"),
    )
    port: int = Field(
        default=5432,
        title=N_("Port"),
        ge=1,
        le=65535,
        json_schema_extra=layout(row="address"),
    )
    # The SSH connection this server is reached through, if any (D282).
    ssh_tunnel: str = ssh_tunnel_field()


class PostgresUserPassword(_PostgresBase):
    model_config = ConfigDict(title=N_("User & Password"))

    auth_method: Literal["user_password"] = _auth_method_field("user_password")
    database: str = _database_field()
    user: str = _user_field()
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())

    async def sign_in(self, cloud: CloudAccess | None) -> SignIn:
        return SignIn(user=self.user, password=self.password.get_secret_value())


class PostgresNoAuth(_PostgresBase):
    """A server that asks for no password: `trust` or `peer` in pg_hba.conf.

    Not a hypothetical variant added to make the list longer — the difference
    reaches the driver, which then sends no password at all rather than an
    empty one.
    """

    model_config = ConfigDict(title=N_("No auth"))

    auth_method: Literal["no_auth"] = _auth_method_field("no_auth")
    database: str = _database_field()
    user: str = _user_field()

    async def sign_in(self, cloud: CloudAccess | None) -> SignIn:
        return SignIn(user=self.user, password=None)


class PostgresAwsIam(_PostgresBase):
    """RDS or Aurora IAM: the password is a token issued for every new
    connection, valid fifteen minutes, and TLS is required (D453)."""

    model_config = ConfigDict(title=N_("AWS IAM (RDS)"))

    auth_method: Literal["aws_iam"] = _auth_method_field("aws_iam")
    database: str = _database_field()
    user: str = _user_field()
    account: str = aws_account_field()
    region: str = region_field()

    @model_validator(mode="after")
    def _encrypted(self) -> Self:
        # RDS refuses an IAM token without TLS; `preferred` asks for it first.
        if self.tls_mode == "disabled":
            raise ValueError(say("IAM sign-in needs TLS; choose a mode on the TLS page"))
        return self

    async def sign_in(self, cloud: CloudAccess | None) -> SignIn:
        return await rds_sign_in(cloud, self.account, self.region, self.host, self.port, self.user)


class PostgresSecretStore(_PostgresBase):
    """A password kept in a secret store, read at every new connection (D454)."""

    model_config = ConfigDict(title=N_("Secret store"))

    auth_method: Literal["secret_store"] = _auth_method_field("secret_store")
    database: str = _database_field()
    account: str = store_account_field()
    secret_name: str = secret_name_field()
    password_key: str = password_key_field()
    user_key: str = user_key_field()
    user: str = stored_user_field()

    async def sign_in(self, cloud: CloudAccess | None) -> SignIn:
        return await stored_sign_in(
            cloud, self.account, self.secret_name, self.password_key, self.user_key, self.user
        )


PostgresOptions = Annotated[
    PostgresUserPassword | PostgresNoAuth | PostgresAwsIam | PostgresSecretStore,
    Field(discriminator="auth_method"),
]


def container_options(env: Mapping[str, str]) -> dict[str, Any]:
    """A container of the official image as a connection (D417): its
    `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB`, defaulting as the
    image does."""
    user = env.get("POSTGRES_USER") or "postgres"
    found: dict[str, Any] = {"user": user, "database": env.get("POSTGRES_DB") or user}
    if env.get("POSTGRES_HOST_AUTH_METHOD") == "trust":
        return {**found, "auth_method": "no_auth"}
    password = env.get("POSTGRES_PASSWORD")
    return {**found, "auth_method": "user_password", **({"password": password} if password else {})}
