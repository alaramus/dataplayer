"""The key an agent reports under (D128).

Issued by the server: a UDP packet carries no other proof of who may write.
Stored twice — hashed, because every packet is looked up by it, and encrypted,
because its owner needs it again to configure an agent.
"""

import hashlib
import secrets

from app.core import crypto

KEY_BYTES = 24


def issue() -> str:
    # URL-safe so it survives an environment variable and a command line.
    return secrets.token_urlsafe(KEY_BYTES)


def fingerprint(key: str) -> str:
    """The lookup form of a key. A plain hash suffices for a random token."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def seal(key: str) -> bytes:
    return crypto.encrypt(key.encode("utf-8"), purpose="connector")


def unseal(sealed: bytes) -> str:
    return crypto.decrypt(sealed, purpose="connector").decode("utf-8")
