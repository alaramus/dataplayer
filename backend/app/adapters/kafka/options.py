"""How to reach a Kafka cluster, and who is asking (D304).

The flat union MySQL and ZooKeeper have, for the same reason (D16): no
authentication and a SASL user are different sets of fields, and each SASL
mechanism is a choice of its own rather than a field beside the password.
"""

from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, SecretStr, field_validator, model_validator

from app.adapters.cloud import CloudAccess, IssuedSecret
from app.adapters.cloud.signin import aws_account_field, msk_token, region_field
from app.adapters.layout import layout
from app.adapters.tls import TlsOptions
from app.core.translation import N_, say


def _auth_method_field(method: str) -> Any:
    return Field(default=method, title=N_("Authentication"), json_schema_extra=layout())


def checked_servers(text: str) -> str:
    """`host:port` pairs separated by commas, as librdkafka takes them."""
    servers: list[str] = []
    for part in text.split(","):
        server = part.strip()
        if server == "":
            continue
        host, colon, port = server.rpartition(":")
        if colon == "" or host in {"", "[]"} or not port.isdigit():
            raise ValueError(say("Each broker is written as host:port"))
        if not 1 <= int(port) <= 65535:
            raise ValueError(say("A port is between 1 and 65535"))
        if "/" in server or " " in server:
            raise ValueError(say("Each broker is written as host:port"))
        servers.append(server)
    if not servers:
        raise ValueError(say("Name at least one broker"))
    return ",".join(servers)


class _KafkaBase(TlsOptions):
    model_config = ConfigDict(extra="forbid")

    # The first broker that answers tells the client where every other one is,
    # so one is enough and several only spare a broker that is down (D304).
    bootstrap_servers: str = Field(
        default="localhost:9092",
        title=N_("Brokers"),
        description=N_("host:port of one or more brokers, separated by commas"),
        min_length=1,
        json_schema_extra=layout(),
    )

    @field_validator("bootstrap_servers")
    @classmethod
    def _servers_are_pairs(cls, text: str) -> str:
        return checked_servers(text)


class KafkaNoAuth(_KafkaBase):
    """A cluster that asks nobody who they are, as a development one usually does."""

    model_config = ConfigDict(title=N_("None"))

    auth_method: Literal["none"] = _auth_method_field("none")


class _KafkaSasl(_KafkaBase):
    user: str = Field(title=N_("User"), min_length=1, json_schema_extra=layout())
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())


class KafkaPlain(_KafkaSasl):
    """SASL PLAIN: the password itself crosses, so it belongs over TLS."""

    model_config = ConfigDict(title=N_("SASL PLAIN"))

    auth_method: Literal["plain"] = _auth_method_field("plain")


class KafkaScram256(_KafkaSasl):
    model_config = ConfigDict(title=N_("SASL SCRAM-SHA-256"))

    auth_method: Literal["scram-sha-256"] = _auth_method_field("scram-sha-256")


class KafkaScram512(_KafkaSasl):
    model_config = ConfigDict(title=N_("SASL SCRAM-SHA-512"))

    auth_method: Literal["scram-sha-512"] = _auth_method_field("scram-sha-512")


class KafkaAwsMskIam(_KafkaBase):
    """Amazon MSK with IAM: SASL/OAUTHBEARER with a token signed by the
    account, issued per run and renewed by the client (D453). TLS only, as
    MSK's IAM listener is."""

    model_config = ConfigDict(title=N_("AWS IAM (MSK)"))

    auth_method: Literal["aws_msk_iam"] = _auth_method_field("aws_msk_iam")
    account: str = aws_account_field()
    region: str = region_field()

    @model_validator(mode="after")
    def _encrypted(self) -> Self:
        if self.tls_mode == "disabled":
            raise ValueError(say("IAM sign-in needs TLS; choose a mode on the TLS page"))
        return self

    async def token(self, cloud: CloudAccess | None) -> IssuedSecret:
        return await msk_token(cloud, self.account, self.region)


class KafkaOauthOidc(_KafkaBase):
    """SASL/OAUTHBEARER with OIDC's client credentials: librdkafka asks the
    token endpoint itself and renews the token before it expires (D456)."""

    model_config = ConfigDict(title=N_("SASL OAUTHBEARER (OIDC)"))

    auth_method: Literal["oauthbearer_oidc"] = _auth_method_field("oauthbearer_oidc")
    token_endpoint: str = Field(
        min_length=1,
        max_length=2048,
        title=N_("Token endpoint"),
        examples=["https://login.example.com/oauth2/token"],
        json_schema_extra=layout(),
    )
    client_id: str = Field(min_length=1, max_length=512, title=N_("Client ID"), json_schema_extra=layout())
    client_secret: SecretStr = Field(
        min_length=1, max_length=4096, title=N_("Client secret"), json_schema_extra=layout()
    )
    scope: str = Field(
        default="",
        max_length=1024,
        title=N_("Scope"),
        description=N_("Empty asks for the client's default scope"),
        json_schema_extra=layout(),
    )

    @field_validator("token_endpoint")
    @classmethod
    def _an_endpoint(cls, value: str) -> str:
        value = value.strip()
        try:
            parts = urlsplit(value)
        except ValueError:
            parts = None
        if (
            parts is None
            or parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
        ):
            raise ValueError(say("The token endpoint must be an http or https address"))
        return value


KafkaSasl = KafkaPlain | KafkaScram256 | KafkaScram512

KafkaOptions = Annotated[
    KafkaNoAuth | KafkaPlain | KafkaScram256 | KafkaScram512 | KafkaAwsMskIam | KafkaOauthOidc,
    Field(discriminator="auth_method"),
]

# librdkafka's name for each mechanism.
MECHANISMS: dict[str, str] = {
    "plain": "PLAIN",
    "scram-sha-256": "SCRAM-SHA-256",
    "scram-sha-512": "SCRAM-SHA-512",
}
