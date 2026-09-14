"""The key an agent signs under (D128, D130).

Issued by the server: a UDP datagram carries no other proof of who may write.
Stored twice — hashed, because a datagram names its key by the start of that
hash, and encrypted, because a signature is checked with the key itself and
its owner needs it again to configure an agent.
"""

import hashlib
import secrets

from app.core import crypto

KEY_BYTES = 24
# How much of the fingerprint a DPMA/1 datagram names its key by.
KEY_ID_LENGTH = 16


def issue() -> str:
    # URL-safe so it survives an environment variable and a command line.
    return secrets.token_urlsafe(KEY_BYTES)


def fingerprint(key: str) -> str:
    """The lookup form of a key. A plain hash suffices for a random token."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_id(key: str) -> str:
    return fingerprint(key)[:KEY_ID_LENGTH]


def seal(key: str) -> bytes:
    return crypto.encrypt(key.encode("utf-8"), purpose="connector")


def unseal(sealed: bytes) -> str:
    return crypto.decrypt(sealed, purpose="connector").decode("utf-8")
