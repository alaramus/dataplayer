"""What a source that signs in with a stored key is handed, and nothing more.

A private key is a person's rather than a connection's (D146), so a driver
never reads one from its options: the options name a key, and the server hands
over the key itself through `AdapterContext.keys` at the moment it is needed.
The driver does not learn where keys are kept, and the store does not learn
what a driver does with one.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass(frozen=True)
class SigningKey:
    """A private key ready to sign with, and what opens it when it is locked.

    `private_key` is the key as it was generated or imported — OpenSSH or PEM
    text, possibly encrypted under `passphrase`. Neither field may reach a
    log, a traceback or an answer, so the `repr` says what this is and no more.
    """

    private_key: str
    passphrase: str | None

    def __repr__(self) -> str:
        return "SigningKey(<hidden>)"


@runtime_checkable
class KeyAccess(Protocol):
    """The keys of the person who owns a connection.

    Raises `AdapterError` of kind `locked` when the key asks for a passphrase
    nobody has given it lately (D147), and of kind `config` when the key is
    gone or belongs to somebody else — a connection may name any id, and only
    the owner's keys answer.
    """

    async def signing_key(self, key_id: uuid.UUID) -> SigningKey: ...


class ServerKey(BaseModel):
    """The key a server proves itself with, as a person compares it (D145).

    `public_key` is the one line `known_hosts` would hold; the fingerprint is
    what anybody compares by eye, against `ssh-keygen -lf` on the server.
    """

    public_key: str
    algorithm: str
    fingerprint: str


@runtime_checkable
class PinsServerKey(Protocol):
    """A source that trusts one server key per connection, pinned by a person.

    Both asked of the class: the form asks before the options validate — no
    key is chosen yet, a password is not typed — and neither question needs
    anything but the address and what is pinned.
    """

    @classmethod
    def pinned_server_key(cls, options: Mapping[str, Any]) -> ServerKey | None:
        """The key the form holds, described, or None when it holds none."""
        ...

    @classmethod
    async def presented_server_key(cls, options: Mapping[str, Any]) -> ServerKey:
        """What the server at the form's address presents now.

        Sends nothing but a greeting: the key is exchanged before anybody
        signs in. Raises AdapterError when the server cannot be reached and
        ValueError when the form holds no address yet.
        """
        ...
