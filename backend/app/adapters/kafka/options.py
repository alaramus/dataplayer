"""How to reach a Kafka cluster, and who is asking (D304).

The flat union MySQL and ZooKeeper have, for the same reason (D16): no
authentication and a SASL user are different sets of fields, and each SASL
mechanism is a choice of its own rather than a field beside the password.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.adapters.layout import layout
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


class _KafkaBase(BaseModel):
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
    tls: bool = Field(
        default=False,
        title=N_("TLS"),
        description=N_("Encrypted, with the brokers' certificates verified"),
        json_schema_extra=layout(),
    )
    # Not secret: a CA certificate is what everybody is meant to have.
    ca_certificate: str = Field(
        default="",
        title=N_("CA certificate"),
        description=N_("PEM, for TLS; empty to trust the system's authorities"),
        json_schema_extra=layout(multiline=True),
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


KafkaSasl = KafkaPlain | KafkaScram256 | KafkaScram512

KafkaOptions = Annotated[
    KafkaNoAuth | KafkaPlain | KafkaScram256 | KafkaScram512,
    Field(discriminator="auth_method"),
]

# librdkafka's name for each mechanism.
MECHANISMS: dict[str, str] = {
    "plain": "PLAIN",
    "scram-sha-256": "SCRAM-SHA-256",
    "scram-sha-512": "SCRAM-SHA-512",
}
