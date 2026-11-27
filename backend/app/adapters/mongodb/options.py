"""How to reach a MongoDB server, and who is asking (D283).

The same flat union MySQL has, for the same reason (D16). The database is
optional: it says where the catalog opens, and one connection reaches every
database its user may see.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, SecretStr

from app.adapters.cloud import CloudAccess
from app.adapters.cloud.signin import (
    aws_account_field,
    aws_credentials,
    password_key_field,
    region_field,
    secret_name_field,
    store_account_field,
    stored_sign_in,
    stored_user_field,
    user_key_field,
)
from app.adapters.layout import layout
from app.adapters.tls import TlsOptionsRds
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


def _auth_source_field() -> Any:
    return Field(
        default="admin",
        title=N_("Authentication database"),
        description=N_("Where the user is defined; admin unless it was made in another database"),
        min_length=1,
        json_schema_extra=layout(),
    )


@dataclass(frozen=True)
class MongodbSignIn:
    """Who signs in, with what and how, asked at every new client (D449).

    Blank for a server without access control. `mechanism` is pymongo's word,
    absent for the server's default; `session_token` goes with MONGODB-AWS's
    temporary keys.
    """

    user: str = ""
    password: str = ""
    auth_source: str = ""
    mechanism: str = ""
    session_token: str = ""

    def __repr__(self) -> str:
        return f"MongodbSignIn({self.user!r}, <hidden>)"


class _MongodbBase(TlsOptionsRds):
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
    # The SSH connection this server is reached through, if any (D282).
    ssh_tunnel: str = ssh_tunnel_field()


class MongodbUserPassword(_MongodbBase):
    model_config = ConfigDict(title=N_("User & Password"))

    auth_method: Literal["user_password"] = _auth_method_field("user_password")
    database: str = _database_field()
    user: str = Field(title=N_("User"), min_length=1, json_schema_extra=layout())
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())
    auth_source: str = _auth_source_field()

    async def sign_in(self, cloud: CloudAccess | None) -> MongodbSignIn:
        return MongodbSignIn(self.user, self.password.get_secret_value(), self.auth_source)


class MongodbNoPassword(_MongodbBase):
    """A server started without access control, as a fresh one is."""

    model_config = ConfigDict(title=N_("No password"))

    auth_method: Literal["no_password"] = _auth_method_field("no_password")
    database: str = _database_field()

    async def sign_in(self, cloud: CloudAccess | None) -> MongodbSignIn:
        return MongodbSignIn()


class MongodbAwsIam(_MongodbBase):
    """MONGODB-AWS: the account's keys sign the request, the user is the IAM
    principal in `$external`. Atlas and self-run servers; not DocumentDB (D453)."""

    model_config = ConfigDict(title=N_("AWS IAM (MONGODB-AWS)"))

    auth_method: Literal["aws_iam"] = _auth_method_field("aws_iam")
    database: str = _database_field()
    account: str = aws_account_field()
    region: str = region_field()

    async def sign_in(self, cloud: CloudAccess | None) -> MongodbSignIn:
        keys = await aws_credentials(cloud, self.account, self.region)
        return MongodbSignIn(
            user=keys.user or "",
            password=keys.value,
            auth_source="$external",
            mechanism="MONGODB-AWS",
            session_token=keys.session_token or "",
        )


class MongodbSecretStore(_MongodbBase):
    """A password kept in a secret store, read at every new client (D454)."""

    model_config = ConfigDict(title=N_("Secret store"))

    auth_method: Literal["secret_store"] = _auth_method_field("secret_store")
    database: str = _database_field()
    account: str = store_account_field()
    secret_name: str = secret_name_field()
    password_key: str = password_key_field()
    user_key: str = user_key_field()
    user: str = stored_user_field()
    auth_source: str = _auth_source_field()

    async def sign_in(self, cloud: CloudAccess | None) -> MongodbSignIn:
        found = await stored_sign_in(
            cloud, self.account, self.secret_name, self.password_key, self.user_key, self.user
        )
        return MongodbSignIn(found.user, found.password or "", self.auth_source)


MongodbOptions = Annotated[
    MongodbUserPassword | MongodbNoPassword | MongodbAwsIam | MongodbSecretStore,
    Field(discriminator="auth_method"),
]


def container_options(env: Mapping[str, str]) -> dict[str, Any]:
    """A container of the official image as a connection (D417): the root
    user it made, defined in `admin`, when it made one."""
    database = env.get("MONGO_INITDB_DATABASE") or ""
    user = env.get("MONGO_INITDB_ROOT_USERNAME")
    if not user:
        return {"auth_method": "no_password", "database": database}
    password = env.get("MONGO_INITDB_ROOT_PASSWORD")
    return {
        "auth_method": "user_password",
        "user": user,
        "database": database,
        "auth_source": "admin",
        **({"password": password} if password else {}),
    }
