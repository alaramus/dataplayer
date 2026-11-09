"""How to reach a RabbitMQ broker, and who is asking (D325).

One user and password for both doors: AMQP, which moves messages, and the
management API, which says what there is. RabbitMQ keeps one user list for
both, so a second set of fields would only ever be filled with the same.
"""

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.adapters.layout import layout
from app.core.translation import N_, say


def checked_management_url(text: str) -> str:
    """`http(s)://host[:port][/prefix]`, with nothing after the prefix."""
    url = text.strip().rstrip("/")
    if url == "":
        return ""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError(say("The management address starts with http:// or https://"))
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError(
            say("The management address carries no user, query or fragment")
        )
    try:
        parts.port  # noqa: B018 - read for the error a bad port raises
    except ValueError:
        raise ValueError(say("A port is between 1 and 65535")) from None
    return url


class RabbitmqOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        default="localhost",
        title=N_("Host"),
        min_length=1,
        json_schema_extra=layout(),
    )
    port: int = Field(
        default=5672,
        ge=1,
        le=65535,
        title=N_("AMQP port"),
        description=N_("5672, or 5671 with TLS"),
        json_schema_extra=layout(),
    )
    management_url: str = Field(
        default="",
        title=N_("Management address"),
        description=N_(
            "Where the management API answers; empty for http://<host>:15672, "
            "or https with TLS"
        ),
        json_schema_extra=layout(),
    )
    user: str = Field(
        default="guest", title=N_("User"), min_length=1, json_schema_extra=layout()
    )
    password: SecretStr = Field(
        default=SecretStr(""), title=N_("Password"), json_schema_extra=layout()
    )
    # Empty is every virtual host the user may see (D326).
    vhost: str = Field(
        default="",
        title=N_("Virtual host"),
        description=N_("Empty for every virtual host the user may see"),
        max_length=255,
        json_schema_extra=layout(),
    )
    tls: bool = Field(
        default=False,
        title=N_("TLS"),
        description=N_("Encrypted, with the broker's certificate verified"),
        json_schema_extra=layout(),
    )
    # Not secret: a CA certificate is what everybody is meant to have.
    ca_certificate: str = Field(
        default="",
        title=N_("CA certificate"),
        description=N_("PEM, for TLS; empty to trust the system's authorities"),
        json_schema_extra=layout(multiline=True),
    )

    @field_validator("host")
    @classmethod
    def _plain_host(cls, text: str) -> str:
        host = text.strip()
        # An IPv6 address is written in brackets, colons and all.
        bracketed = host.startswith("[") and host.endswith("]")
        if host == "" or (not bracketed and any(mark in host for mark in "/@ :?#")):
            raise ValueError(say("A host is a name or an address, nothing more"))
        return host

    @field_validator("management_url")
    @classmethod
    def _management(cls, text: str) -> str:
        return checked_management_url(text)

    def management(self) -> str:
        """The management API's root, the default filled in."""
        if self.management_url:
            return self.management_url
        scheme = "https" if self.tls else "http"
        return f"{scheme}://{self.host}:15672"
