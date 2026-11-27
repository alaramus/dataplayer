"""How to reach a Redis server.

Two ways, as a discriminated union, for the reason PostgreSQL has one (D16):
a server that wants a password and one that does not are different sets of
fields, and a single model with an optional password is a form that asks for
something half of its users must leave empty — and a `SecretStr | None` that
D4's schema split would not recognise as a secret at all.
"""

from collections.abc import Mapping
from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, SecretStr, model_validator

from app.adapters.cloud import CloudAccess
from app.adapters.cloud.signin import (
    SignIn,
    aws_account_field,
    elasticache_sign_in,
    region_field,
)
from app.adapters.layout import layout
from app.adapters.tls import TlsOptions
from app.adapters.tunnels import ssh_tunnel_field
from app.core.translation import N_, say


def _auth_method_field(value: str) -> Any:
    return Field(default=value, title=N_("Authentication"), json_schema_extra=layout())


class _RedisBase(TlsOptions):
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
    # The SSH connection this server is reached through, if any (D282).
    ssh_tunnel: str = ssh_tunnel_field()
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
    # Redis 6's ACL: a named user, or the default one when left empty.
    user: str = Field(
        default="",
        max_length=255,
        title=N_("User"),
        description=N_("An ACL user; empty for the default user"),
        json_schema_extra=layout(),
    )
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())

    async def sign_in(self, cloud: CloudAccess | None) -> SignIn:
        return SignIn(user=self.user, password=self.password.get_secret_value())


class RedisNoAuth(_RedisBase):
    """A server that asks for nothing, which is the default configuration."""

    model_config = ConfigDict(title=N_("No auth"))

    auth_method: Literal["no_auth"] = _auth_method_field("no_auth")

    async def sign_in(self, cloud: CloudAccess | None) -> SignIn:
        return SignIn(user="", password=None)


class RedisAwsIam(_RedisBase):
    """ElastiCache or MemoryDB with IAM: a token issued for every connection,
    signed for the cache and a user made with IAM authentication (D453)."""

    model_config = ConfigDict(title=N_("AWS IAM (ElastiCache, MemoryDB)"))

    auth_method: Literal["aws_iam"] = _auth_method_field("aws_iam")
    user: str = Field(
        min_length=1,
        max_length=255,
        title=N_("User"),
        description=N_("A user made with IAM authentication; its name is its ID"),
        json_schema_extra=layout(),
    )
    cache_name: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^[a-zA-Z0-9-]+$",
        title=N_("Cache"),
        description=N_("The replication group, serverless cache or cluster name, not its address"),
        json_schema_extra=layout(),
    )
    service: Literal["elasticache", "memorydb"] = Field(
        default="elasticache",
        title=N_("Service"),
        json_schema_extra=layout(row="service"),
    )
    serverless: bool = Field(
        default=False,
        title=N_("Serverless cache"),
        json_schema_extra=layout(row="service"),
    )
    account: str = aws_account_field()
    region: str = region_field()

    @model_validator(mode="after")
    def _encrypted(self) -> Self:
        # ElastiCache takes IAM sign-in only with encryption in transit.
        if self.tls_mode == "disabled":
            raise ValueError(say("IAM sign-in needs TLS; choose a mode on the TLS page"))
        return self

    async def sign_in(self, cloud: CloudAccess | None) -> SignIn:
        return await elasticache_sign_in(
            cloud,
            self.account,
            self.region,
            self.cache_name,
            self.user,
            self.serverless,
            self.service,
        )


RedisOptions = Annotated[
    RedisPassword | RedisNoAuth | RedisAwsIam, Field(discriminator="auth_method")
]


def container_options(env: Mapping[str, str]) -> dict[str, Any]:
    """A Redis container as a connection (D417). The official image takes its
    password on the command line rather than from the environment, so only
    `REDIS_PASSWORD` — Bitnami's and others' — is read."""
    password = env.get("REDIS_PASSWORD")
    if password:
        return {"auth_method": "password", "password": password}
    return {"auth_method": "no_auth"}
