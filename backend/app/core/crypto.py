import base64
import os
from typing import Literal

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_SIZE = 12

# Which key protects a piece of data, named rather than passed as bytes: a
# caller that has to fetch a key to encrypt something can also fetch the wrong
# one, and the two here protect different things (D63). There is no default,
# for the reason an access level has none: what a caller is protecting is
# exactly the thing it must not be able to leave unsaid.
Purpose = Literal["connector", "query_content"]


def _key(purpose: Purpose) -> bytes:
    encoded = (
        settings.CONNECTOR_SECRET_KEY
        if purpose == "connector"
        else settings.QUERY_CONTENT_KEY
    )
    return base64.urlsafe_b64decode(encoded)


def encrypt(plaintext: bytes, *, purpose: Purpose) -> bytes:
    """Encrypt data. Returns the nonce concatenated with the ciphertext."""
    nonce = os.urandom(NONCE_SIZE)
    return nonce + AESGCM(_key(purpose)).encrypt(nonce, plaintext, None)


def decrypt(payload: bytes, *, purpose: Purpose) -> bytes:
    """Decrypt data produced by encrypt() under the same purpose.

    Raises cryptography.exceptions.InvalidTag when the payload was tampered
    with or was encrypted under a different key.
    """
    nonce, ciphertext = payload[:NONCE_SIZE], payload[NONCE_SIZE:]
    return AESGCM(_key(purpose)).decrypt(nonce, ciphertext, None)
