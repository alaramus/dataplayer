"""How to reach an SSH server, and how to prove who is asking.

Two ways of signing in, as a discriminated union for the reason PostgreSQL has
one (D16): a password and a key are different fields. A key is named by id
rather than pasted here — it is its owner's, kept apart from the connections
that use it, and handed to the driver when it signs in (D146).

The server's own key is part of the connection too: pinned once, from what
the server presented and a person confirmed, and required to match on every
connection after (D145).
"""

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.adapters.layout import layout
from app.adapters.options import KEY_REFERENCE, SERVER_KEY
from app.core.translation import N_


def _auth_method_field(value: str) -> Any:
    return Field(default=value, title=N_("Authentication"), json_schema_extra=layout())


class _SshBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        min_length=1, max_length=255, title=N_("Host"), json_schema_extra=layout(row="address")
    )
    port: int = Field(
        default=22, ge=1, le=65535, title=N_("Port"), json_schema_extra=layout(row="address")
    )
    username: str = Field(
        min_length=1, max_length=255, title=N_("User"), json_schema_extra=layout()
    )
    # Where the catalog stands, and as far up as it goes. Not a wall: the
    # server's own permissions are what decide what this user may read, and
    # a person who wants the whole disk writes `/` (D144).
    path: str = Field(
        default="",
        max_length=1024,
        title=N_("Folder"),
        description=N_("Where browsing starts; empty is the user's home folder"),
        json_schema_extra=layout(),
    )
    # The server's public key as one `known_hosts` line, pinned from what the
    # server presented and a person confirmed. Empty until then, and nothing
    # connects while it is: a password is not sent to a server nobody has
    # recognised (D145).
    host_key: str = Field(
        default="",
        max_length=16_384,
        title=N_("Server key"),
        description=N_("What this server proves itself with; fetch it and compare"),
        json_schema_extra=layout(purpose=SERVER_KEY),
    )


class SshKeyAuth(_SshBase):
    model_config = ConfigDict(title=N_("Key"))

    auth_method: Literal["key"] = _auth_method_field("key")
    key_id: uuid.UUID = Field(
        title=N_("Key"),
        description=N_("One of your SSH keys; its public half goes to the server"),
        json_schema_extra=layout(purpose=KEY_REFERENCE),
    )


class SshPassword(_SshBase):
    model_config = ConfigDict(title=N_("Password"))

    auth_method: Literal["password"] = _auth_method_field("password")
    password: SecretStr = Field(title=N_("Password"), json_schema_extra=layout())


# A key first: it is what the server this was written against should be using,
# and the order of a union is the order of the choice on the form.
SshOptions = Annotated[SshKeyAuth | SshPassword, Field(discriminator="auth_method")]
