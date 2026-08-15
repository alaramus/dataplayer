import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_SIZE = 12


def _key() -> bytes:
    return base64.urlsafe_b64decode(settings.CONNECTOR_SECRET_KEY)


def encrypt(plaintext: bytes) -> bytes:
    """Encrypt data. Returns the nonce concatenated with the ciphertext."""
    nonce = os.urandom(NONCE_SIZE)
    return nonce + AESGCM(_key()).encrypt(nonce, plaintext, None)


def decrypt(payload: bytes) -> bytes:
    """Decrypt data produced by encrypt().

    Raises cryptography.exceptions.InvalidTag when the payload was tampered
    with or was encrypted under a different key.
    """
    nonce, ciphertext = payload[:NONCE_SIZE], payload[NONCE_SIZE:]
    return AESGCM(_key()).decrypt(nonce, ciphertext, None)
