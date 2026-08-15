import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_SIZE = 12


def _key() -> bytes:
    return base64.urlsafe_b64decode(settings.CONNECTOR_SECRET_KEY)


def encrypt(plaintext: bytes) -> bytes:
    """Зашифровать данные. Возвращает nonce, склеенный с шифротекстом."""
    nonce = os.urandom(NONCE_SIZE)
    return nonce + AESGCM(_key()).encrypt(nonce, plaintext, None)


def decrypt(payload: bytes) -> bytes:
    """Расшифровать данные, полученные из encrypt().

    Бросает cryptography.exceptions.InvalidTag, если данные повреждены или
    зашифрованы другим ключом.
    """
    nonce, ciphertext = payload[:NONCE_SIZE], payload[NONCE_SIZE:]
    return AESGCM(_key()).decrypt(nonce, ciphertext, None)
