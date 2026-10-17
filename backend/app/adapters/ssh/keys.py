"""What an SSH key is, asked of the one library that reads them.

`asyncssh` is imported by this package and by nothing else, the rule `psycopg`
already follows: the store of keys (D146) asks here what a key is rather than
parsing one itself, and an upgrade of the library has one place to change.

Every refusal here is a sentence of this repository's. The library's own
messages are about its parser, and one of them quotes the start of the text it
could not read — which, for a private key, is the key.
"""

from dataclasses import dataclass
from typing import Literal

import asyncssh

from app.adapters.credentials import SigningKey
from app.core.translation import say

# What a key made here can be. ED25519 unless the server will not take it,
# which is Coolify's rule and OpenSSH's own default; RSA for the old servers
# that still refuse anything else.
KeyType = Literal["ed25519", "rsa"]

_ALGORITHM_OF: dict[KeyType, str] = {"ed25519": "ssh-ed25519", "rsa": "ssh-rsa"}
_RSA_BITS = 4096

# What a key made here says about itself in `authorized_keys`, so a person
# reading that file on the server can tell which line this application added.
COMMENT = "dataplayer"


class KeyNeedsPassphrase(ValueError):
    """The key is encrypted, and nothing was given to open it with."""


@dataclass(frozen=True)
class KeyFacts:
    """What may be said about a key without saying the key.

    The public half and its fingerprint are what a person copies to a server
    and compares against it; neither opens anything.
    """

    algorithm: str
    public_key: str
    fingerprint: str


@dataclass(frozen=True)
class PreparedKey:
    """A private key in the form it is kept in, and its public facts.

    `private_key` is OpenSSH text, encrypted under the passphrase when one was
    given, so a copy of it at rest opens nothing without that passphrase too.
    """

    private_key: str
    facts: KeyFacts

    def __repr__(self) -> str:
        return f"PreparedKey({self.facts.algorithm}, {self.facts.fingerprint})"


def generate(key_type: KeyType, passphrase: str | None) -> PreparedKey:
    """A new key pair, made on this server so its private half never left it."""
    if key_type == "rsa":
        key = asyncssh.generate_private_key(
            _ALGORITHM_OF[key_type], comment=COMMENT, key_size=_RSA_BITS
        )
    else:
        key = asyncssh.generate_private_key(_ALGORITHM_OF[key_type], comment=COMMENT)
    return _prepared(key, passphrase)


def imported(private_key: str, passphrase: str | None) -> PreparedKey:
    """A key somebody pasted, checked and put into the form it is kept in.

    The passphrase is what the key is locked with from now on. For a key that
    arrives encrypted it must be the one that opens it; a key that arrives in
    the clear is encrypted under it, so choosing to be asked for a passphrase
    protects a key that had none.
    """
    return _prepared(_opened(private_key, passphrase), passphrase)


def facts_of(private_key: str, passphrase: str | None) -> KeyFacts:
    """The public facts of a stored key, which also proves the passphrase opens it."""
    return _facts(_opened(private_key, passphrase))


def is_encrypted(private_key: str) -> bool:
    """Whether the key cannot be read without a passphrase."""
    try:
        asyncssh.import_private_key(private_key)
    except asyncssh.KeyImportError as failure:
        return "passphrase" in str(failure).lower()
    return False


def client_key(signing: SigningKey) -> asyncssh.SSHKey:
    """The key as the library signs with it."""
    return _opened(signing.private_key, signing.passphrase)


def host_key_facts(public_key: str) -> KeyFacts:
    """What a server's key is, from the line it was pinned as (D145)."""
    try:
        key = asyncssh.import_public_key(public_key)
    except (asyncssh.KeyImportError, ValueError):
        raise ValueError(say("This is not a server key this application can read")) from None
    return _facts(key)


def public_line(key: asyncssh.SSHKey) -> str:
    """One key as the single line `known_hosts` and `authorized_keys` hold."""
    return key.export_public_key("openssh").decode().strip()


def _opened(private_key: str, passphrase: str | None) -> asyncssh.SSHKey:
    try:
        return asyncssh.import_private_key(private_key, passphrase or None)
    except asyncssh.KeyEncryptionError:
        raise ValueError(say("That passphrase does not open this key")) from None
    except asyncssh.KeyImportError as failure:
        if "passphrase" in str(failure).lower():
            raise KeyNeedsPassphrase(
                say("This key is protected by a passphrase; enter it")
            ) from None
        raise ValueError(say("This is not a private key this application can read")) from None


def _prepared(key: asyncssh.SSHKey, passphrase: str | None) -> PreparedKey:
    exported = key.export_private_key("openssh", passphrase or None).decode()
    return PreparedKey(private_key=exported, facts=_facts(key))


def _facts(key: asyncssh.SSHKey) -> KeyFacts:
    return KeyFacts(
        algorithm=key.get_algorithm(),
        public_key=public_line(key),
        fingerprint=key.get_fingerprint("sha256"),
    )
