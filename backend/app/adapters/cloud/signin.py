"""The user and password a database is signed in to with, issued or kept (D453, D454).

Driver-free. A source declares its cloud variants with the field factories
below, each where it belongs in its own flat union (D16), and every variant
answers `sign_in(cloud)` with a `SignIn` at every new connection: the stored
password, an RDS token, a secret read from a store. A driver asks the variant
rather than branching on which one it is.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import Field

from app.adapters.cloud import (
    AccountKind,
    CloudAccess,
    IssuedSecret,
    account_field,
    issue,
)
from app.adapters.cloud.requests import (
    CloudCredentials,
    CloudSqlToken,
    ElastiCacheToken,
    EntraToken,
    MskToken,
    RdsAuthToken,
    StoredSecret,
    VaultDatabaseCredentials,
)
from app.adapters.layout import layout
from app.adapters.protocol import AdapterError
from app.core.translation import N_, say

# What Azure Database for PostgreSQL and for MySQL, and Azure Cache for Redis,
# take a Microsoft Entra token for.
AZURE_DATABASE_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"
AZURE_REDIS_SCOPE = "https://redis.azure.com/.default"

# Every kind a secret can be kept in (D454).
STORE_KINDS: tuple[AccountKind, ...] = ("aws", "gcp", "azure", "vault")


@dataclass(frozen=True)
class SignIn:
    """Who to sign in as and with what; no password for a server that asks none."""

    user: str
    password: str | None

    def __repr__(self) -> str:
        return f"SignIn({self.user!r}, <hidden>)"


def aws_account_field() -> Any:
    return account_field("aws", title=N_("AWS account"), description=N_("One of your cloud accounts"))


def gcp_account_field() -> Any:
    return account_field("gcp", title=N_("Google Cloud account"), description=N_("One of your cloud accounts"))


def azure_account_field() -> Any:
    return account_field("azure", title=N_("Azure account"), description=N_("One of your cloud accounts"))


def vault_account_field() -> Any:
    return account_field("vault", title=N_("Vault account"), description=N_("One of your cloud accounts"))


def vault_user_field() -> Any:
    """Empty and hidden: Vault names the user with every lease, and an address
    shown or a program's arguments name none until it does."""
    extra = layout()
    extra["x-ui-hidden"] = True
    return Field(default="", max_length=0, title=N_("User"), json_schema_extra=extra)


def vault_mount_field() -> Any:
    return Field(
        default="database",
        min_length=1,
        max_length=255,
        pattern=r"^[\w-]+(/[\w-]+)*$",
        title=N_("Mount"),
        description=N_("Where Vault's database secrets engine is enabled"),
        json_schema_extra=layout(row="vault role"),
    )


def vault_role_field() -> Any:
    return Field(
        min_length=1,
        max_length=255,
        pattern=r"^[\w.-]+$",
        title=N_("Role"),
        json_schema_extra=layout(row="vault role"),
    )


def region_field() -> Any:
    return Field(
        default="",
        max_length=64,
        pattern=r"^[a-z0-9-]*$",
        title=N_("Region"),
        description=N_("Empty is the account's region"),
        json_schema_extra=layout(),
    )


def store_account_field() -> Any:
    return account_field(
        *STORE_KINDS,
        title=N_("Secret store"),
        description=N_("The cloud account the secret is kept in"),
    )


def secret_name_field() -> Any:
    return Field(
        min_length=1,
        max_length=2048,
        title=N_("Secret"),
        description=N_("Its name, ARN or path in the store"),
        json_schema_extra=layout(),
    )


def password_key_field() -> Any:
    return Field(
        default="password",
        min_length=1,
        max_length=255,
        title=N_("Password key"),
        description=N_("Read when the secret is JSON"),
        json_schema_extra=layout(row="secret keys"),
    )


def user_key_field() -> Any:
    return Field(
        default="username",
        min_length=1,
        max_length=255,
        title=N_("User key"),
        json_schema_extra=layout(row="secret keys"),
    )


def stored_user_field() -> Any:
    return Field(
        default="",
        max_length=255,
        title=N_("User"),
        description=N_("Empty is the user kept in the secret"),
        json_schema_extra=layout(),
    )


async def rds_sign_in(
    cloud: CloudAccess | None, account: str, region: str, host: str, port: int, user: str
) -> SignIn:
    """An RDS or Aurora IAM token for this host and user, valid fifteen minutes.

    Signed for the form's host, not where a tunnel dials: RDS checks the
    name it was signed for, and through a tunnel that is still the server's.
    """
    secret = await issue(cloud, account, ("aws",), RdsAuthToken(host, port, user, region))
    return SignIn(user=user, password=secret.value)


async def cloudsql_sign_in(cloud: CloudAccess | None, account: str, user: str) -> SignIn:
    """Cloud SQL's IAM database sign-in: the account's access token is the
    password, the user the IAM principal as the instance names it (D455)."""
    secret = await issue(cloud, account, ("gcp",), CloudSqlToken())
    return SignIn(user=user, password=secret.value)


async def entra_sign_in(cloud: CloudAccess | None, account: str, user: str, scope: str) -> SignIn:
    """A Microsoft Entra token for the resource's scope as the password."""
    secret = await issue(cloud, account, ("azure",), EntraToken(scope))
    return SignIn(user=user, password=secret.value)


async def elasticache_sign_in(
    cloud: CloudAccess | None,
    account: str,
    region: str,
    cache_name: str,
    user: str,
    serverless: bool,
    service: str,
) -> SignIn:
    """An ElastiCache or MemoryDB IAM token for one cache and user, valid
    fifteen minutes; the connection it opens is closed by the cache after
    twelve hours, and a Redis client here lives for one operation."""
    secret = await issue(
        cloud, account, ("aws",), ElastiCacheToken(cache_name, user, region, serverless, service)
    )
    return SignIn(user=user, password=secret.value)


async def msk_token(cloud: CloudAccess | None, account: str, region: str) -> IssuedSecret:
    """An MSK IAM token for SASL/OAUTHBEARER, valid fifteen minutes."""
    return await issue(cloud, account, ("aws",), MskToken(region))


async def aws_credentials(cloud: CloudAccess | None, account: str, region: str) -> IssuedSecret:
    """The account's own keys, for a driver that signs with them itself:
    the access key in `user`, its secret in `value`, a session token beside."""
    return await issue(cloud, account, ("aws",), CloudCredentials(region))


async def vault_dynamic_sign_in(cloud: CloudAccess | None, account: str, mount: str, role: str) -> SignIn:
    """A user and password Vault made for this server under the role; the
    same pair serves every connection until a minute before its lease ends."""
    secret = await issue(cloud, account, ("vault",), VaultDatabaseCredentials(mount, role))
    if not secret.user:
        raise AdapterError("config", say("This Vault role does not make database credentials"))
    return SignIn(user=secret.user, password=secret.value)


async def stored_sign_in(
    cloud: CloudAccess | None,
    account: str,
    name: str,
    password_key: str,
    user_key: str,
    user: str,
) -> SignIn:
    """The password a store keeps, and the user typed or kept beside it."""
    secret = await issue(cloud, account, STORE_KINDS, StoredSecret(name, password_key, user_key))
    found = user or secret.user
    if not found:
        raise AdapterError(
            "config", say("Name the user, or keep it in the secret under {key}", key=user_key)
        )
    return SignIn(user=found, password=secret.value)
