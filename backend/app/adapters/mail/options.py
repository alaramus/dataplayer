"""How to reach a mailbox: IMAP to read it, SMTP to send from it (D368)."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.adapters.layout import layout
from app.adapters.mailbox import Address
from app.core.translation import N_

# TLS from the first byte, an upgrade before signing in, or neither.
Security = Literal["tls", "starttls", "none"]


class _MailBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: Address = Field(
        title=N_("Email address"),
        description=N_("What a letter you send is from"),
        json_schema_extra=layout(),
    )
    display_name: str = Field(
        default="",
        max_length=200,
        title=N_("Your name"),
        description=N_("Shown beside the address in letters you send; may be empty"),
        json_schema_extra=layout(),
    )
    user: str = Field(
        default="",
        max_length=320,
        title=N_("Login"),
        description=N_("Empty to sign in with the email address"),
        json_schema_extra=layout(),
    )
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())
    imap_host: str = Field(
        title=N_("IMAP server"), min_length=1, max_length=255, json_schema_extra=layout(row="imap")
    )
    imap_port: int = Field(
        default=993, title=N_("IMAP port"), ge=1, le=65535, json_schema_extra=layout(row="imap")
    )
    # Its own line: three fields in one row left the server's name no room.
    imap_security: Security = Field(
        default="tls", title=N_("IMAP security"), json_schema_extra=layout()
    )
    smtp_host: str = Field(
        title=N_("SMTP server"), min_length=1, max_length=255, json_schema_extra=layout(row="smtp")
    )
    smtp_port: int = Field(
        default=465, title=N_("SMTP port"), ge=1, le=65535, json_schema_extra=layout(row="smtp")
    )
    smtp_security: Security = Field(
        default="tls", title=N_("SMTP security"), json_schema_extra=layout()
    )
    save_sent: bool = Field(
        default=True,
        title=N_("Keep a copy in Sent"),
        description=N_("Off for a server that keeps one itself, as Gmail does"),
        json_schema_extra=layout(),
    )

    def imap_login(self) -> str:
        return self.user or self.address

    def smtp_login(self) -> str:
        return self.imap_login()

    def smtp_secret(self) -> str:
        return self.password.get_secret_value()


def _smtp_auth_field(value: str) -> Any:
    return Field(default=value, title=N_("SMTP sign-in"), json_schema_extra=layout())


class MailSameLogin(_MailBase):
    """SMTP signed in to with the login and password above, as most are."""

    model_config = ConfigDict(title=N_("Same as IMAP"))

    smtp_auth: Literal["same"] = _smtp_auth_field("same")


class MailSeparateLogin(_MailBase):
    """A server that signs SMTP in apart from IMAP.

    Two models rather than an optional password, for the reason Redis has two
    (D16): a `SecretStr | None` is not seen as a secret by the schema split.
    """

    model_config = ConfigDict(title=N_("Its own login"))

    smtp_auth: Literal["separate"] = _smtp_auth_field("separate")
    smtp_user: str = Field(
        title=N_("SMTP login"), min_length=1, max_length=320, json_schema_extra=layout()
    )
    smtp_password: SecretStr = Field(title=N_("SMTP password"), json_schema_extra=layout())

    def smtp_login(self) -> str:
        return self.smtp_user

    def smtp_secret(self) -> str:
        return self.smtp_password.get_secret_value()


MailOptions = Annotated[MailSameLogin | MailSeparateLogin, Field(discriminator="smtp_auth")]
