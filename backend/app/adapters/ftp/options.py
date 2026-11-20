"""How to reach an FTP server, how the line is protected, and who signs in (D386).

Signing in is a discriminated union for the reason Redis's is (D16): a server
that wants a password and an anonymous one are different sets of fields, and
a `SecretStr | None` is not seen as a secret by the schema split (D4).
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.adapters.layout import layout
from app.core.translation import N_, say

# TLS asked for after connecting (AUTH TLS) first: it is what the servers in
# use speak, on the port plain FTP has. Implicit TLS is the older FTPS, whose
# port is 990; no encryption sends the password as it is typed.
Security = Literal["explicit", "implicit", "none"]

DEFAULT_PORT = 21
IMPLICIT_PORT = 990

ANONYMOUS_USER = "anonymous"
# What an anonymous login sends as its password: by custom an address, which
# servers accept whatever it is.
ANONYMOUS_PASSWORD = "anonymous@"


def _auth_method_field(value: str) -> Any:
    return Field(default=value, title=N_("Authentication"), json_schema_extra=layout())


class _FtpBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        min_length=1,
        max_length=255,
        title=N_("Host"),
        json_schema_extra=layout(row="address"),
    )
    port: int = Field(
        default=DEFAULT_PORT,
        ge=1,
        le=65535,
        title=N_("Port"),
        description=N_("21, or 990 for implicit TLS"),
        json_schema_extra=layout(row="address"),
    )
    security: Security = Field(
        default="explicit",
        title=N_("Encryption"),
        json_schema_extra={
            **layout(row="transport"),
            "x-ui-choices": [
                {"value": "explicit", "label": N_("TLS, explicit")},
                {"value": "implicit", "label": N_("TLS, implicit")},
                {"value": "none", "label": N_("No encryption")},
            ],
        },
    )
    verify_tls: bool = Field(
        default=True,
        title=N_("Verify the certificate"),
        description=N_("Off only for a server with a certificate of its own making"),
        json_schema_extra=layout(row="transport"),
    )
    # Where the catalog stands, and not a wall: the server's own permissions
    # decide what this user may read, as on an SSH server (D144).
    path: str = Field(
        default="",
        max_length=1024,
        title=N_("Folder"),
        description=N_(
            "Where browsing starts; empty is the folder the server signs you into"
        ),
        json_schema_extra=layout(),
    )

    @field_validator("host")
    @classmethod
    def _a_host(cls, value: str) -> str:
        value = value.strip()
        if value == "" or any(character in value for character in "/@ \t\r\n"):
            raise ValueError(
                say("The host is a name or an address, without a scheme or a path")
            )
        return value

    @field_validator("path")
    @classmethod
    def _one_line(cls, value: str) -> str:
        """A path the server is sent on its command line: a line break in it
        would be a second command."""
        value = value.strip()
        if "\r" in value or "\n" in value:
            raise ValueError(say("The folder is one line"))
        return value.rstrip("/") if value not in ("", "/") else value


class FtpPassword(_FtpBase):
    model_config = ConfigDict(title=N_("Password"))

    auth_method: Literal["password"] = _auth_method_field("password")
    username: str = Field(
        min_length=1, max_length=255, title=N_("User"), json_schema_extra=layout()
    )
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())

    @field_validator("username")
    @classmethod
    def _user_on_one_line(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError(say("The user is one line"))
        return value

    @property
    def login(self) -> tuple[str, str]:
        return self.username, self.password.get_secret_value()


class FtpAnonymous(_FtpBase):
    """A public server that lets anybody in, as `anonymous`."""

    model_config = ConfigDict(title=N_("Anonymous"))

    auth_method: Literal["anonymous"] = _auth_method_field("anonymous")

    @property
    def login(self) -> tuple[str, str]:
        return ANONYMOUS_USER, ANONYMOUS_PASSWORD


# A password first: it is what a server of one's own asks for.
FtpOptions = Annotated[FtpPassword | FtpAnonymous, Field(discriminator="auth_method")]
